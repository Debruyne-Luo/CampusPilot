"""Read a frozen local bundle and run two metered public questions; never activate it."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
import time
from decimal import Decimal
from pathlib import Path

from campuspilot.agent.executor import AgentRunner
from campuspilot.chat_runtime import ConversationContext
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.evaluation_budget import TokenPrice
from campuspilot.experiment_budget import CampaignBudget
from campuspilot.jev_plugin import JevPlugin
from campuspilot.jev_shadow import JevShadowClient
from campuspilot.knowledge import KnowledgeStore
from campuspilot.knowledge_release import atomic_write, read_candidate, release_reference
from campuspilot.llm.chat_model import ChatCompletionsModel
from campuspilot.llm.embedding import CloudflareEmbedder
from campuspilot.rag import SnapshotStore, canonical
from campuspilot.tools import agent_registry
from evaluate_student_experience import SmokeModel, key_file


async def smoke(candidate: Path, config: Path, cloudflare: Path, budget_dir: Path) -> dict:
    snapshot = read_candidate(candidate)
    if snapshot.pending:
        raise ValueError("Source adoption must precede real-answer checks")
    credentials = json.loads(config.read_bytes())
    cf = json.loads(cloudflare.read_bytes())
    budget = CampaignBudget(budget_dir)
    before = json.loads(budget.path.read_bytes())
    model = SmokeModel(ChatCompletionsModel(
        "https://api.deepseek.com", "deepseek-flash",
        key_file(Path(credentials["deepseek_key_file"])), max_output_tokens=1500,
    ), budget)
    embedder = CloudflareEmbedder(cf["CF_ACCOUNT_ID"], cf["CF_API_TOKEN"], timeout=8, retries=0)
    with tempfile.TemporaryDirectory(prefix="campuspilot-final-smoke-") as temp:
        root = Path(temp)
        copied = root / "versions" / snapshot.version
        shutil.copytree(candidate, copied)
        atomic_write(root / "current.json", canonical(release_reference(copied)))
        snapshots = SnapshotStore(root, "hybrid", embedder=embedder)
        repo = DirectoryRepository.load(candidate / "directory")
        knowledge = KnowledgeStore.load(candidate / "directory/knowledge.json")
        judge = JevPlugin(JevShadowClient(
            key_file(Path(credentials["jev_key_file"])),
            TokenPrice(Decimal(".042"), Decimal("0")),
        ), budget, "on", snapshots)
        agent = AgentRunner(
            agent_registry(repo, knowledge, snapshots, embedder=embedder,
                           roster=candidate / "directory/teachers_roster.json"),
            repo, model, snapshots=snapshots, concise=True, jev=judge,
        )
        rows = []
        for question in ["统一身份认证的安全手机号换了，原手机不能用了怎么办？",
                         "宿舍没电了，购电通过什么入口？"]:
            start = time.perf_counter()
            body = await agent.run(question, ConversationContext())
            rows.append({"question": question, "latency_ms": (time.perf_counter() - start) * 1000,
                         "response": body})
        await agent.drain()
        reader = snapshots.acquire()
        if reader is not None and reader.index is not None:
            reader.index.close()
    after = json.loads(budget.path.read_bytes())
    return {"knowledge_version": snapshot.version, "observations": rows,
            "budget_before": before, "budget_after": after,
            "acceptance": "Two smoke questions do not establish the 54/60 release gate."}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("candidate", "config", "cloudflare", "budget-dir", "output"):
        p.add_argument("--" + key, type=Path, required=True)
    args = p.parse_args()
    result = asyncio.run(smoke(args.candidate, args.config, args.cloudflare, args.budget_dir))
    # Ledger contents are kept private; publish only necessary aggregate counters.
    private = args.output.with_suffix(".private.json")
    private.write_bytes(canonical(result))
    public = {k: v for k, v in result.items() if not k.startswith("budget_")}
    args.output.write_bytes(canonical(public))
    print(json.dumps({"version": result["knowledge_version"], "smoke_questions": 2}))
