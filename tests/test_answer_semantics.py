"""SYNTHETIC regressions for audience gates and evidence-scoped channel conclusions."""

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from campuspilot.agent.evidence import Evidence
from campuspilot.agent.executor import AgentRunner
from campuspilot.agent.plan import Plan
from campuspilot.agent.understand import Slots, Understanding
from campuspilot.chat_runtime import ConversationContext
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.tools import agent_registry
from pydantic import JsonValue
from test_agent_loop import REPO, FakeLLM, answer, understood


@pytest.mark.parametrize("audience", [
    "SYNTHETIC 研究生,教师,学生",
    "SYNTHETIC 本科生、研究生、教职工",
    "SYNTHETIC 全校师生",
])
def test_broad_service_audience_does_not_turn_document_question_into_identity_question(
    audience: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Mock(spec=DirectoryRepository, wraps=REPO)
    repository.find_service.return_value = SimpleNamespace(audience=audience)
    model = FakeLLM(understood("政策问答", missing=["identity"], service="SYNTHETIC 合成预约"))
    agent = AgentRunner(agent_registry(REPO, KnowledgeStore(())), repository, model)
    monkeypatch.setattr(agent, "matching_services", lambda _: ["SYNTHETIC:service"])

    result: Any = asyncio.run(agent.run(
        "SYNTHETIC 合成预约仅收录的文字如下，能当成完整流程吗？", ConversationContext(),
    ))

    assert result["result_status"] != "needs_clarification"
    assert "身份" not in result["answer"] and "本科生" not in result["answer"]
    assert result["plan"]  # The question reached document retrieval.


def test_a_specific_service_audience_still_gates_personal_handling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Mock(spec=DirectoryRepository, wraps=REPO)
    repository.find_service.return_value = SimpleNamespace(audience="SYNTHETIC 研究生")
    agent = AgentRunner(agent_registry(REPO, KnowledgeStore(())), repository, None)
    monkeypatch.setattr(agent, "matching_services", lambda _: ["SYNTHETIC:service"])
    view = Understanding(intent="办事", slots=Slots(service="SYNTHETIC 合成证明"),
                         missing=("identity",))

    assert agent.needed(view, "SYNTHETIC 合成证明怎么开") == ("identity",)


def compose_channel(text: str, question: str) -> tuple[dict[str, Any], FakeLLM]:
    model = FakeLLM(answer("SYNTHETIC 不能直接线下提交，只能线上办理。", ["SYNTHETIC:source"]))
    agent = AgentRunner(agent_registry(REPO, KnowledgeStore(())), REPO, model, concise=True)
    hit: dict[str, JsonValue] = {"source_id": "SYNTHETIC:source", "chunk_id": "SYNTHETIC:chunk",
           "title": "SYNTHETIC 合成事项指南", "text": text, "grounded": True}
    ev = Evidence(allowed={"SYNTHETIC:source", "SYNTHETIC:chunk"}, hits=[hit],
                  results=[{"tool": "search_knowledge", "result": {"hits": [hit]}}])
    result = asyncio.run(agent._compose(question, Understanding(intent="政策问答"),
                                       ConversationContext(), ev, Plan(), []))
    return result, model


@pytest.mark.parametrize("field", ["办理方式\t线上办理", "办理方式：线上办理"])
def test_online_channel_field_does_not_prove_offline_submission_is_forbidden(field: str) -> None:
    body, model = compose_channel(
        "SYNTHETIC 合成事项\n基本信息\n" + field + "\n办理流程\n提交合成申请，等待审核。",
        "SYNTHETIC 合成事项文字指南显示可以直接线下提交吗？",
    )

    assert "线上办理" in body["answer"]
    assert "不能直接线下" not in body["answer"] and "只能线上" not in body["answer"]
    assert "不能排除" in body["answer"] or "无法确认" in body["answer"]
    assert body["source_ids"] == ["SYNTHETIC:source"]
    assert not model.calls


@pytest.mark.parametrize(("text", "question"), [
    ("SYNTHETIC 办理方式：线上办理。明确不受理线下提交。", "SYNTHETIC 指南允许线下提交吗？"),
    ("SYNTHETIC 线上材料和线下材料均未收录。", "SYNTHETIC 指南允许线下提交吗？"),
    ("SYNTHETIC 办理方式：线上办理。", "SYNTHETIC 指南写的线上提交步骤是什么？"),
    ("SYNTHETIC 办理方式：线上办理。", "SYNTHETIC 指南的现场咨询电话是多少？"),
])
def test_channel_scope_advice_does_not_override_other_evidence_or_question(
    text: str, question: str,
) -> None:
    _, model = compose_channel(text, question)
    assert model.calls
