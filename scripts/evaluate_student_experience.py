"""Bounded local latency and optional real public-question smoke; no student data."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import subprocess
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from campuspilot.agent.executor import AgentRunner
from campuspilot.chat_runtime import ConversationContext
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.evaluation_budget import OnlineBudget, TokenPrice
from campuspilot.experiment_budget import CampaignBudget
from campuspilot.jev_plugin import JevPlugin
from campuspilot.jev_shadow import JevShadowClient
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import ChatCompletionsModel, Completion
from campuspilot.rag import SnapshotStore, canonical, digest
from campuspilot.tools import agent_registry
from campuspilot.web import create_web_app
from campuspilot.web_evidence import DeepSeekToolsProvider, WebEvidenceService
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def identity() -> dict[str, Any]:
    source_hashes = {p.relative_to(ROOT).as_posix(): digest(p.read_bytes())
                     for p in sorted((ROOT / 'backend/src').rglob('*.py'))}
    directory_hashes = {name: digest((ROOT / 'data/cdut' / name).read_bytes())
                        for name in ['services.json', 'places.json', 'knowledge.json']}
    snapshot = SnapshotStore(ROOT / 'data/cdut/rag', 'lexical').acquire()
    return {
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                               text=True).strip(),
        'runtime_source_sha256': digest(canonical(source_hashes)),
        'directory_sha256': directory_hashes,
        'knowledge_version': snapshot.snapshot.version if snapshot else None,
    }


def key_file(path: Path) -> str:
    value_path = str(path).replace('\\', '/')
    if os.name == 'nt' and value_path.startswith('/mnt/'):
        parts = value_path.split('/')
        if len(parts) > 3 and len(parts[2]) == 1 and parts[2].isalpha():
            path = Path(parts[2] + ':/' + '/'.join(parts[3:]))
    if not path.is_absolute() or path.resolve().is_relative_to(ROOT):
        raise ValueError('Credential file must stay outside the repository')
    value = path.read_text(encoding='utf-8-sig').strip()
    if not value or any(c.isspace() for c in value):
        raise ValueError('Invalid credential file')
    return value


class SmokeModel:
    def __init__(self, model: ChatCompletionsModel, budget: OnlineBudget) -> None:
        self.model, self.budget = model, budget
        self.price = TokenPrice(Decimal('.3'), Decimal('1.2'))

    async def complete(
        self, messages: list[dict[str, object]], tools: list[dict[str, object]] | None = None,
        json_mode: bool = False, max_tokens: int | None = None,
    ) -> Completion:
        reservation = self.budget.reserve(self.price.cost(
            len(canonical(messages)) + len(canonical(tools)) + 8192, max_tokens or 1500,
        ), 'student-experience:chat')
        actual = None
        try:
            result = await self.model.complete(messages, tools=tools, json_mode=json_mode,
                                               max_tokens=max_tokens)
            if result.input_tokens + result.output_tokens > 0:
                actual = self.price.cost(result.input_tokens, result.output_tokens)
            return result
        finally:
            self.budget.settle(reservation, actual)


def summarize(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    return {'samples': len(values), 'p50_ms': round(statistics.median(ordered), 2),
            'p95_ms': round(ordered[math.ceil(.95 * len(ordered)) - 1], 2)}


def local() -> dict[str, Any]:
    app = create_web_app(data_dir=ROOT / 'data/cdut', runtime_mode='phase2',
                         agent_loop=True, retrieval_mode='lexical',
                         knowledge_bundle='approved-20261011b')
    headers = {'Origin': 'http://testserver', 'X-CampusPilot-Request': '1'}
    questions = ['校园卡挂失怎么办', '校园卡补办在哪里办', '东区图书馆在哪', '香樟餐厅怎么去',
                 '网络故障报修入口在哪', '学生邮箱激活入口在哪']
    rows = []
    with TestClient(app) as client:
        for i in range(10):
            client.cookies.clear()
            client.post('/api/session', headers=headers)
            for question in questions:
                start = time.perf_counter()
                response = client.post('/api/chat', json={'message': question}, headers=headers)
                elapsed = (time.perf_counter() - start) * 1000
                body = response.json()
                rows.append({'question': question, 'iteration': i, 'latency_ms': elapsed,
                             'http': response.status_code, 'status': body.get('result_status'),
                             'mode': body.get('answer_mode'), 'answer': body.get('answer'),
                             'service_links': body.get('service_links', [])})
    return {'condition': 'in-process HTTP, 10 independent anonymous sessions, real directory '
                         'and approved bundle, no model/network',
            **summarize([r['latency_ms'] for r in rows]), 'observations': rows,
            'all_success': all(r['http'] == 200 and (r['status'] == 'success' or (
                r['status'] == 'limited' and r['mode'] == 'agent_entry' and r['service_links']
            )) for r in rows)}


async def online(config_path: Path, budget_dir: Path) -> dict[str, Any]:
    if not config_path.is_absolute() or config_path.resolve().is_relative_to(ROOT):
        raise ValueError('Credential configuration must stay outside the repository')
    config = json.loads(config_path.read_bytes())
    budget = CampaignBudget(budget_dir)
    model = SmokeModel(ChatCompletionsModel(
        'https://api.deepseek.com', 'deepseek-flash',
        key_file(Path(config['deepseek_key_file'])), max_output_tokens=1500,
    ), budget)
    snapshots = SnapshotStore(ROOT / 'data/cdut/rag', 'lexical', bundled='approved-20261011b')
    repository = DirectoryRepository.load(ROOT / 'data/cdut')
    knowledge = KnowledgeStore.load(ROOT / 'data/cdut/knowledge.json')
    judge = JevPlugin(JevShadowClient(key_file(Path(config['jev_key_file'])),
                                    TokenPrice(Decimal('.042'), Decimal('0'))),
                      budget, 'on', snapshots)
    search = WebEvidenceService(budget, DeepSeekToolsProvider(model.model.api_key))
    agent = AgentRunner(agent_registry(repository, knowledge, snapshots), repository, model,
                        snapshots=snapshots, concise=True, jev=judge)
    observations: list[dict[str, Any]] = []
    for question in ['图书馆本科生能借几本书', '在家怎么访问学校图书馆数据库']:
        start = time.perf_counter()
        body = await agent.run(question, ConversationContext())
        observations.append({'question': question, 'latency_ms': round(
            (time.perf_counter() - start) * 1000, 2), 'body': body})
        if body.get('degraded_reason') in {'upstream_credentials', 'upstream_limit', 'budget'}:
            break
    online_agent = AgentRunner(agent_registry(repository, knowledge, snapshots), repository, model,
                               snapshots=snapshots, concise=True, jev=judge, web_service=search)
    question = '2026年下半年四六级笔试是哪天，报名还开着吗？请查最新通知'
    start = time.perf_counter()
    body = await online_agent.run(question, ConversationContext())
    observations.append({'question': question, 'latency_ms': round(
        (time.perf_counter() - start) * 1000, 2), 'body': body, 'end_to_end_web': True})
    # One real Search/Fetch smoke, separate from model quality and end-to-end latency.
    web = await search.search('2026年下半年全国大学英语四六级报名通知 笔试时间')
    return {'condition': 'real public questions, lexical approved bundle; small smoke only',
            'observations': observations, 'search': {
                'status': web.status, 'latency_ms': web.latency_ms,
                'attempts': web.attempts, 'page_reads': web.page_reads,
                'pages': [{'url': p.url, 'title': p.title, 'text': p.text,
                           'access_method': p.access_method} for p in web.pages],
            }, 'budget_file': str(budget.path),
            'limitation': 'Three model questions and one search do not establish p95 '
            'or release quality'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--budget-dir', type=Path)
    args = parser.parse_args()
    report = {'identity': identity(), 'local': local()}
    if args.config:
        if not args.budget_dir or not args.budget_dir.is_absolute():
            parser.error('Online smoke needs an absolute external --budget-dir')
        report['online'] = asyncio.run(online(args.config, args.budget_dir))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(report))
    print(json.dumps({'local': {k: v for k, v in report['local'].items()
                                if k != 'observations'}, 'online': bool(args.config)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
