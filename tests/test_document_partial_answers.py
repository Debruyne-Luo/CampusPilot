"""Synthetic document-only partial answers survive Jev and failed web enrichment."""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from campuspilot.agent.executor import AgentRunner
from campuspilot.chat_runtime import ConversationContext
from campuspilot.evaluation_budget import SpendBudget
from campuspilot.jev_plugin import JevAssessment, JevPlugin
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import Completion, ToolCall
from campuspilot.rag import SnapshotStore
from campuspilot.tools import agent_registry
from campuspilot.web_evidence import WebEvidenceService, WebPageEvidence, WebSearchResult
from test_agent_loop import DATA, REPO, FakeLLM, answer, understood
from test_jev_plugin import FakeJev
from test_snapshot_fallback import synthetic_snapshot
from test_turn_snapshot import release

QUESTION = "SYNTHETIC graduate guideline 需要什么材料，费用是多少"
LOCAL_TEXT = "SYNTHETIC 合成测试要求提交合成测试表。"
PARTIAL_ANSWER = LOCAL_TEXT + "费用没有资料依据，不能确认。"
WEB_TEXT = "SYNTHETIC UNAPPROVED WEB CONTENT，不得作为已确认校务事实。"
WEB_ID = "web:SYNTHETIC-unapproved"
LOCAL_ID = "SYNTHETIC:source"
CHUNK_ID = "SYNTHETIC:clause"


def assessment(
    decision: str, *, status: str = "ok", ranked: bool = True, search: bool = False
) -> JevAssessment:
    return JevAssessment(
        status=status,
        decision=decision,  # type: ignore[arg-type]
        local="unassessed",
        original_ids=(CHUNK_ID,) if ranked else (),
        ranked_ids=(CHUNK_ID,) if ranked else (),
        search_needed=search,
    )


def runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model: FakeLLM,
    *,
    local: bool = True,
    web: WebSearchResult | None = None,
) -> tuple[AgentRunner, Mock]:
    monkeypatch.setattr("campuspilot.tools.knowledge.campus_today", lambda: date(2026, 10, 14))
    store = SnapshotStore(tmp_path / "knowledge")
    if local:
        release(store.root, synthetic_snapshot(LOCAL_TEXT))
    plugin = JevPlugin(FakeJev(), Mock(spec=SpendBudget), "on", store)
    service = Mock(spec=WebEvidenceService)
    service.search.return_value = web
    agent = AgentRunner(
        agent_registry(REPO, KnowledgeStore.load(DATA / "knowledge.json"), store),
        REPO,
        model,
        jev=plugin,
        web_service=service if web is not None else None,
    )
    return agent, service


@pytest.mark.parametrize("decision", ["clarify", "insufficient"])
def test_document_partial_survives_whole_question_jev_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, decision: str
) -> None:
    model = FakeLLM(
        understood("政策问答", identity="graduate"), answer(PARTIAL_ANSWER, [LOCAL_ID])
    )
    agent, _ = runner(tmp_path, monkeypatch, model)
    judge = AsyncMock(return_value=assessment(decision))
    monkeypatch.setattr(agent, "_judge", judge)

    body: Any = asyncio.run(agent.run(QUESTION, ConversationContext()))

    limitations, generated = body["answer"].split("\n\n", 1)
    assert generated == PARTIAL_ANSWER
    assert "来源适用校区尚未确认" in limitations
    assert "仅适用于2026-2027学年" in limitations
    assert body["result_status"] in {"success", "limited"}
    assert body["source_ids"] == [LOCAL_ID]
    assert body["excerpts"][0]["chunk_id"] == CHUNK_ID
    assert not body["services"] and not body["places"] and not body["checklist"]
    assert len(model.calls) == 2 and judge.await_count == 1


@pytest.mark.parametrize("decision", ["insufficient", "clarify"])
def test_model_extra_document_search_keeps_ranked_partial_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, decision: str
) -> None:
    def final(messages: list[dict[str, object]]) -> Completion:
        extra = next(message for message in messages if message["role"] == "tool")
        result = json.loads(str(extra["content"]))
        assert result["hits"] and result["hits"][0]["chunk_id"] == CHUNK_ID
        assert not result.get("withheld")
        return answer(PARTIAL_ANSWER, [LOCAL_ID])

    model = FakeLLM(
        understood("政策问答", identity="graduate"),
        Completion(tool_calls=(ToolCall(
            call_id="SYNTHETIC-extra-document-search",
            name="search_knowledge",
            arguments=json.dumps({"query": QUESTION, "audience": "graduate"}),
        ),)),
        final,
    )
    agent, _ = runner(tmp_path, monkeypatch, model)
    judge = AsyncMock(side_effect=[assessment("sufficient"), assessment(decision)])
    monkeypatch.setattr(agent, "_judge", judge)

    body: Any = asyncio.run(agent.run(QUESTION, ConversationContext()))

    limitations, generated = body["answer"].split("\n\n", 1)
    assert generated == PARTIAL_ANSWER
    assert "来源适用校区尚未确认" in limitations
    assert "仅适用于2026-2027学年" in limitations
    assert body["source_ids"] == [LOCAL_ID]
    assert len(model.calls) == 3 and judge.await_count == 2


def web_result(case: str) -> WebSearchResult:
    if case in {"timeout", "budget", "empty", "not_configured"}:
        return WebSearchResult(case)  # type: ignore[arg-type]
    third_party = case == "third_party"
    page = WebPageEvidence(
        WEB_ID,
        "SYNTHETIC unapproved fixture, not a real university document",
        "https://synthetic.invalid/fixture" if third_party
        else "https://www.cdut.edu.cn/__SYNTHETIC_unapproved_fixture__",
        WEB_TEXT,
        "third_party" if third_party else "official_university",
        "2026-10-14",
    )
    return WebSearchResult("success", (page,))


@pytest.mark.parametrize(
    "case",
    ["timeout", "budget", "empty", "not_configured", "unsure", "insufficient", "third_party"],
)
def test_unapproved_web_enrichment_preserves_only_local_partial_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    model = FakeLLM(
        understood("政策问答", identity="graduate"), answer(PARTIAL_ANSWER, [LOCAL_ID])
    )
    result = web_result(case)
    agent, service = runner(tmp_path, monkeypatch, model, web=result)
    after = assessment("unknown", status="unsure") if case == "unsure" else assessment(
        "sufficient" if case == "third_party" else "insufficient"
    )
    monkeypatch.setattr(
        agent, "_judge",
        AsyncMock(side_effect=[assessment("insufficient", search=True), after]),
    )

    body: Any = asyncio.run(agent.run(QUESTION, ConversationContext()))

    assert PARTIAL_ANSWER in body["answer"]
    assert "联网" in body["answer"]  # The failed/unapproved enrichment remains visible.
    assert body["result_status"] in {"success", "limited"}
    assert body["web_search"]["status"] == result.status
    assert body["source_ids"] == [LOCAL_ID]
    assert {c["id"] for c in body["citations"]} == {LOCAL_ID}
    assert {e["source_id"] for e in body["excerpts"]} == {LOCAL_ID}
    assert len(model.calls) == 2
    generated_from = json.dumps(model.calls[-1]["messages"], ensure_ascii=False)
    assert WEB_TEXT not in generated_from and WEB_ID not in generated_from
    if result.pages:
        assert body["web_sources"][0]["source_label"] == (
            "第三方辅助信息" if case == "third_party" else "待核对的官方材料"
        )
        assert any(word in body["answer"] for word in ("未", "不", "待核"))
    service.search.assert_awaited_once()


@pytest.mark.parametrize("case", ["timeout", "budget", "empty", "not_configured", "third_party"])
def test_no_local_or_approved_web_evidence_never_fabricates_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    model = FakeLLM(understood("政策问答", identity="graduate"))
    result = web_result(case)
    agent, service = runner(tmp_path, monkeypatch, model, local=False, web=result)
    monkeypatch.setattr(
        agent, "_judge",
        AsyncMock(side_effect=[
            assessment("insufficient", ranked=False, search=True),
            assessment("sufficient", ranked=False),
        ]),
    )

    body: Any = asyncio.run(agent.run(QUESTION, ConversationContext()))

    assert body["result_status"] != "success"
    assert body["source_ids"] == body["excerpts"] == body["citations"] == []
    assert WEB_TEXT not in body["answer"] and LOCAL_TEXT not in body["answer"]
    assert body["web_search"]["status"] == result.status
    assert len(model.calls) == 1
    service.search.assert_awaited_once()


def test_explicit_web_request_is_not_replaced_by_jev_clarification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeLLM(understood("政策问答", identity="graduate"))
    agent, service = runner(
        tmp_path, monkeypatch, model, local=False, web=WebSearchResult("empty")
    )
    monkeypatch.setattr(
        agent, "_judge",
        AsyncMock(side_effect=[
            assessment("clarify", ranked=False, search=False),
            assessment("insufficient", ranked=False),
        ]),
    )

    body: Any = asyncio.run(agent.run("请联网查找：" + QUESTION, ConversationContext()))

    service.search.assert_awaited_once()
    assert body["web_search"]["status"] == "empty"
    assert body["result_status"] != "success"
    assert body["source_ids"] == body["excerpts"] == body["citations"] == []
    assert len(model.calls) == 1


def test_failed_web_local_composition_still_rejects_unknown_citation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unknown_id = "SYNTHETIC:never-retrieved-source"
    model = FakeLLM(
        understood("政策问答", identity="graduate"), answer(PARTIAL_ANSWER, [unknown_id])
    )
    agent, service = runner(tmp_path, monkeypatch, model, web=WebSearchResult("timeout"))
    monkeypatch.setattr(
        agent, "_judge",
        AsyncMock(side_effect=[
            assessment("insufficient", search=True), assessment("unknown", status="unsure"),
        ]),
    )

    body: Any = asyncio.run(agent.run(QUESTION, ConversationContext()))

    assert body["result_status"] != "success"
    assert body["degraded_reason"] == "answer_validation"
    assert PARTIAL_ANSWER not in body["answer"]
    assert unknown_id not in json.dumps(body, ensure_ascii=False)
    assert body["source_ids"] == []
    assert body["web_search"]["status"] == "timeout" and "联网" in body["answer"]
    assert len(model.calls) == 2
    service.search.assert_awaited_once()
