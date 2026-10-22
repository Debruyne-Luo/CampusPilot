"""Offline Agent regressions for version pinning, partial answers and execution control."""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from campuspilot.agent.execution import ExecutionBoundary
from campuspilot.agent.executor import AgentRunner
from campuspilot.app.routes_chat import _prefetch_embedding
from campuspilot.app.state import WebState
from campuspilot.chat_runtime import ConversationContext
from campuspilot.contracts import ExecutionContext
from campuspilot.evaluation_budget import SpendBudget
from campuspilot.jev_plugin import JevPlugin
from campuspilot.jev_shadow import ShadowResult
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import Completion, ToolCall
from campuspilot.llm.embedding import CloudflareEmbedder
from campuspilot.rag import RetrievalHit, SnapshotStore
from campuspilot.tools import agent_registry
from campuspilot.web_evidence import WebEvidenceService, WebSearchResult
from pydantic import JsonValue
from test_agent_loop import CARD_EVIDENCE, CARD_ID, DATA, REPO, FakeLLM, answer, understood
from test_jev_plugin import FakeJev
from test_snapshot_fallback import synthetic_snapshot
from test_turn_snapshot import release


class RecordingJev(FakeJev):
    def __init__(self, **options: Any) -> None:
        super().__init__(**options)
        self.evidence: list[tuple[str, str, str]] = []

    async def evaluate(
        self, question: str, candidates: tuple[RetrievalHit, ...], **options: Any
    ) -> ShadowResult:
        self.evidence.extend(
            (h.knowledge_version, h.chunk.text, h.chunk.text_sha256) for h in candidates
        )
        return await super().evaluate(question, candidates, **options)


def test_agent_keeps_initial_version_for_jev_extra_search_and_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("campuspilot.tools.knowledge.campus_today", lambda: date(2026, 10, 14))
    root = tmp_path / "knowledge"
    old, new = synthetic_snapshot("old"), synthetic_snapshot("new")
    release(root, old)
    store = SnapshotStore(root)
    judge = RecordingJev(score={old.chunks[0].chunk_id: 2.0})
    plugin = JevPlugin(judge, Mock(spec=SpendBudget), "on", store)
    rows_seen: list[dict[str, Any]] = []

    def final(messages: list[dict[str, object]]) -> Completion:
        prompt = next(m for m in messages if m["role"] == "user")
        state = json.loads(str(prompt["content"]))
        planned = next(
            r["result"] for r in state["tool_results"] if r["tool"] == "search_knowledge"
        )
        extra = next(json.loads(str(m["content"])) for m in messages if m["role"] == "tool")
        rows_seen.extend([planned, extra])
        for result in (planned, extra):
            assert result["knowledge_version"] == old.version
            assert result["hits"][0]["text"] == old.chunks[0].text
            assert result["hits"][0]["text_sha256"] == old.chunks[0].text_sha256
        return answer(old.chunks[0].text, [old.sources[0].source_id])

    model = FakeLLM(
        understood("政策问答"),
        Completion(tool_calls=(ToolCall(
            call_id="SYNTHETIC-extra", name="search_knowledge",
            arguments='{"query":"graduate guideline"}',
        ),)),
        final,
    )
    agent = AgentRunner(
        agent_registry(REPO, KnowledgeStore.load(DATA / "knowledge.json"), store),
        REPO, model, jev=plugin,
    )
    switched = False

    async def emit(event: str, payload: dict[str, JsonValue]) -> None:
        nonlocal switched
        if event == "tool_end" and payload.get("tool") == "search_knowledge" and not switched:
            switched = True
            await asyncio.to_thread(release, root, new)

    body = asyncio.run(agent.run("SYNTHETIC graduate guideline", ConversationContext(), emit))
    assert switched and len(rows_seen) == 2
    assert body["result_status"] == "success"
    assert str(body["answer"]).split("\n\n")[-1] == old.chunks[0].text
    assert "仅适用于研究生" in str(body["answer"])
    assert body["source_ids"] == [old.sources[0].source_id]
    assert judge.evidence and all(version == old.version for version, _, _ in judge.evidence)
    excerpts = body["excerpts"]
    assert isinstance(excerpts, list) and excerpts
    assert all(isinstance(e, dict) and e["content"] == old.chunks[0].text for e in excerpts)
    acquired = store.acquire()
    assert acquired is not None and acquired.snapshot.version == new.version


@pytest.mark.parametrize("web", [False, True])
@pytest.mark.parametrize("decision", ["insufficient", "clarify"])
def test_partial_service_answer_survives_insufficient_knowledge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, web: bool, decision: str
) -> None:
    monkeypatch.setattr("campuspilot.tools.knowledge.campus_today", lambda: date(2026, 10, 14))
    root = tmp_path / "knowledge"
    snapshot = synthetic_snapshot("SYNTHETIC 校园卡材料费用无关片段")
    release(root, snapshot)
    store = SnapshotStore(root)
    judge = FakeJev(sufficient=0.1, mode="clarify" if decision == "clarify" else "refuse")
    plugin = JevPlugin(judge, Mock(spec=SpendBudget), "on", store)
    service = Mock(spec=WebEvidenceService)
    service.search.return_value = WebSearchResult("empty")
    text = (
        "先确认卡内余额大于20元，带本人身份证，到珙桐或香樟食堂自助服务区办理。"
        "补办费用暂无依据，请核对官方说明。"
    )
    model = FakeLLM(understood(service="校园卡补办"), answer(text, [CARD_EVIDENCE[0]]))
    agent = AgentRunner(
        agent_registry(REPO, KnowledgeStore.load(DATA / "knowledge.json"), store),
        REPO, model, jev=plugin, web_service=service if web else None,
    )
    body = asyncio.run(agent.run("校园卡补办需要什么材料、多少钱、在哪里办", ConversationContext()))
    assert body["result_status"] in {"success", "limited"}
    assert body["services"] and body["checklist"]
    services = body["services"]
    assert isinstance(services, list) and isinstance(services[0], dict)
    assert services[0]["service_id"] == CARD_ID
    assert body["places"] and body["citations"] and body["excerpts"] == []
    if not web or decision == "clarify":
        assert body["answer"] == text and len(model.calls) == 2
    else:
        assert body["answer"] == text + "\n本次联网未找到匹配资料。"
        assert body["source_ids"] == [CARD_EVIDENCE[0]] and len(model.calls) == 2
        assert body["web_search"] == {"status": "empty"}
        service.search.assert_awaited_once()


def test_denied_model_tool_does_not_reuse_previous_tool_result(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "empty")
    boundary = ExecutionBoundary(ExecutionContext(
        session_id="SYNTHETIC", task_id="SYNTHETIC", run_id="SYNTHETIC",
        allowed_tools=frozenset({"search_knowledge"}),
    ))

    def final(messages: list[dict[str, object]]) -> Completion:
        tool = next(m for m in messages if m["role"] == "tool")
        assert json.loads(str(tool["content"])) == {"error": "permission_denied"}
        return answer("SYNTHETIC no evidence", [], "empty")

    model = FakeLLM(
        understood("政策问答"),
        Completion(tool_calls=(ToolCall(
            call_id="SYNTHETIC-denied", name="search_place", arguments='{"query":"香樟"}',
        ),)), final,
    )
    agent = AgentRunner(
        agent_registry(REPO, KnowledgeStore.load(DATA / "knowledge.json"), store),
        REPO, model, execution=boundary,
    )
    body = asyncio.run(agent.run("SYNTHETIC question", ConversationContext()))
    assert body["places"] == [] and body["result_status"] == "empty"


@pytest.mark.parametrize("allowed", [frozenset({"search_web"}), frozenset({"jev_assess"})])
def test_direct_web_and_jev_cannot_bypass_the_execution_boundary(
    tmp_path: Path, allowed: frozenset[str]
) -> None:
    judge = FakeJev(sufficient=0.1)
    plugin = JevPlugin(judge, Mock(spec=SpendBudget), "on")
    service = Mock(spec=WebEvidenceService)
    service.search.return_value = WebSearchResult("empty")
    agent = AgentRunner(
        agent_registry(REPO, KnowledgeStore.load(DATA / "knowledge.json")),
        REPO, None, jev=plugin, web_service=service,
        execution=ExecutionBoundary(ExecutionContext(
            session_id="SYNTHETIC", task_id="SYNTHETIC", run_id="SYNTHETIC",
            allowed_tools=allowed,
        )),
    )
    body = asyncio.run(agent.run("SYNTHETIC question", ConversationContext()))
    assert body["result_status"] == "limited"
    if "jev_assess" not in allowed:
        assert judge.calls == []
    if "search_web" not in allowed:
        service.search.assert_not_awaited()


def test_embedding_prefetch_cannot_bypass_knowledge_permission() -> None:
    state = Mock(spec=WebState)
    state.embedder = Mock(spec=CloudflareEmbedder)
    state.agent = Mock(spec=AgentRunner)
    state.agent.execution = ExecutionBoundary(ExecutionContext(
        session_id="SYNTHETIC", task_id="SYNTHETIC", run_id="SYNTHETIC",
        allowed_tools=frozenset(),
    ))
    asyncio.run(_prefetch_embedding(state, "SYNTHETIC private query"))
    state.embedder.prefetch.assert_not_awaited()
    state.agent.execution = ExecutionBoundary()
    asyncio.run(_prefetch_embedding(state, "SYNTHETIC public query"))
    state.embedder.prefetch.assert_awaited_once_with("SYNTHETIC public query")
