"""Synthetic regressions: useful clarification differs from missing source evidence."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from campuspilot.agent.executor import AgentRunner
from campuspilot.agent.understand import Slots, Understanding
from campuspilot.chat_runtime import ConversationContext
from campuspilot.dify import ChatUnavailable
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.tools import agent_registry
from campuspilot.web_evidence import WebSearchResult
from test_agent_loop import REPO, FakeLLM, understood
from test_document_partial_answers import QUESTION, assessment
from test_document_partial_answers import runner as document_runner


@pytest.mark.parametrize("proposed", [None, "你是什么身份，要办理哪个事项？"])
def test_unknown_task_asks_only_the_missing_task(proposed: str | None) -> None:
    model = FakeLLM(understood(
        "办事", missing=["identity", "service"], clarify_question=proposed,
    ))
    agent = AgentRunner(agent_registry(REPO, KnowledgeStore(())), REPO, model)

    body: Any = asyncio.run(agent.run("这个怎么办", ConversationContext()))

    assert body["result_status"] == "needs_clarification"
    assert "事项" in body["answer"]
    assert all(word not in body["answer"] for word in ("身份", "本科", "研究生", "教职工"))
    assert body["answer"].count("？") == 1
    assert len(model.calls) == 1 and body["plan"] == []


def test_only_actionable_identity_gap_survives_model_suggested_year_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = FakeLLM(understood(
        "办事", missing=["identity", "academic_year"],
        clarify_question="你是本科生还是研究生，办理哪一学年的事项？",
    ))
    repository = Mock(spec=DirectoryRepository, wraps=REPO)
    repository.find_service.return_value = SimpleNamespace(audience="研究生")
    agent = AgentRunner(agent_registry(REPO, KnowledgeStore(())), repository, model)
    monkeypatch.setattr(
        agent, "matching_services", lambda question: ["SYNTHETIC:identity-dependent-service"]
    )

    body: Any = asyncio.run(agent.run("SYNTHETIC 合成测试事项怎么办", ConversationContext()))

    assert body["result_status"] == "needs_clarification"
    assert "研究生" in body["answer"] and "学年" not in body["answer"]
    assert body["answer"].count("？") == 1 and len(model.calls) == 1


def test_jev_clarify_does_not_invent_a_user_condition_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeLLM(understood("政策问答", identity="graduate"))
    agent, _ = document_runner(tmp_path, monkeypatch, model)
    monkeypatch.setattr(
        agent, "_judge", AsyncMock(return_value=assessment("clarify", ranked=False))
    )

    body: Any = asyncio.run(agent.run(QUESTION, ConversationContext()))

    assert body["result_status"] == "empty"
    assert body["source_ids"] == body["citations"] == body["excerpts"] == []
    assert all(word not in body["answer"] for word in ("补充", "身份", "？"))
    assert len(model.calls) == 1


def test_jev_clarify_without_user_gap_searches_available_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeLLM(understood("政策问答", identity="graduate"))
    agent, service = document_runner(
        tmp_path, monkeypatch, model, local=False, web=WebSearchResult("empty")
    )
    monkeypatch.setattr(agent, "_judge", AsyncMock(side_effect=[
        assessment("clarify", ranked=False), assessment("insufficient", ranked=False),
    ]))

    body: Any = asyncio.run(agent.run(QUESTION, ConversationContext()))

    service.search.assert_awaited_once()
    assert body["web_search"]["status"] == "empty"
    assert body["result_status"] != "needs_clarification"
    assert all(word not in body["answer"] for word in ("补充", "身份", "？"))
    assert len(model.calls) == 1


def test_no_published_evidence_does_not_tell_user_to_supply_missing_policy() -> None:
    agent = AgentRunner(agent_registry(REPO, KnowledgeStore(())), REPO, None)

    body: Any = asyncio.run(agent.run("SYNTHETIC 未收录事项费用是多少", ConversationContext()))

    assert body["result_status"] == "empty"
    assert all(word not in body["answer"] for word in ("补充", "身份", "？"))
    assert body["source_ids"] == body["citations"] == []


def test_generation_failure_does_not_blame_question_or_claim_missing_knowledge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeLLM(
        understood("政策问答", identity="graduate"), ChatUnavailable("upstream_timeout")
    )
    agent, _ = document_runner(tmp_path, monkeypatch, model)
    agent.jev = None

    body: Any = asyncio.run(agent.run(QUESTION, ConversationContext()))

    assert body["result_status"] == "limited"
    assert body["degraded_reason"] == "upstream_timeout"
    assert body["citations"] and "来源" in body["answer"]
    assert "补充" not in body["answer"] and "没有足够依据" not in body["answer"]


def test_known_identity_is_not_asked_again_for_an_unrelated_evidence_gap() -> None:
    agent = AgentRunner(agent_registry(REPO, KnowledgeStore(())), REPO, None)
    view = Understanding(
        intent="政策问答", slots=Slots(identity="graduate"), missing=("identity",),
    )

    assert agent.needed(view, "SYNTHETIC 当前资料未收录的费用") == ()
