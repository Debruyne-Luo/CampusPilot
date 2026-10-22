"""SYNTHETIC replays of truncated answers and literal newlines inside JSON strings.

The release observations retain failure metadata, not the original invalid model content.
These fixtures reproduce those recorded failure shapes through the normal compose boundary.
"""

import asyncio
import json
from typing import Any

import pytest
from campuspilot.agent.evidence import Evidence
from campuspilot.agent.executor import ANSWER_MAX_TOKENS, AgentRunner
from campuspilot.agent.plan import Plan
from campuspilot.agent.understand import Understanding
from campuspilot.chat_runtime import ConversationContext
from campuspilot.dify import ChatUnavailable
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import Completion, ToolCall
from campuspilot.tools import agent_registry
from pydantic import JsonValue
from test_agent_loop import REPO, FakeLLM, answer

SOURCE = "SYNTHETIC-source"
FACTS = "SYNTHETIC 先登记，再由本人缴费。"


def compose(model: FakeLLM) -> dict[str, Any]:
    hit: dict[str, JsonValue] = {
        "source_id": SOURCE, "chunk_id": "SYNTHETIC-chunk",
        "title": "SYNTHETIC 办理指南", "text": FACTS, "grounded": True,
    }
    ev = Evidence(
        hits=[hit], allowed={SOURCE, "SYNTHETIC-chunk"},
        results=[{"tool": "search_knowledge", "result": {"hits": [hit]}}],
    )
    runner = AgentRunner(agent_registry(REPO, KnowledgeStore(())), REPO, model)
    return asyncio.run(runner._compose(
        "SYNTHETIC 事项如何办理？", Understanding(intent="政策问答"),
        ConversationContext(), ev, Plan(), [],
    ))


def test_literal_json_newline_is_recovered_without_changing_the_answer_or_calling_model() -> None:
    text = "SYNTHETIC 先登记。\n再由本人缴费。"
    # Intentionally malformed JSON: a literal newline occurs inside the answer string.
    raw = json.dumps({"answer": text, "source_ids": [SOURCE], "status": "success"})
    raw = raw.replace("\\n", "\n")
    model = FakeLLM(Completion(content=raw, finish_reason="stop"))
    result = compose(model)
    assert result["result_status"] == "success"
    assert result["answer"] == text
    assert result["source_ids"] == [SOURCE]
    assert len(model.calls) == 1


@pytest.mark.parametrize("finish_reason,raw", [
    ("length", '{"answer":"SYNTHETIC 先登记'),
    ("length", answer("SYNTHETIC 未完成", [SOURCE]).content),
    ("stop", '{"answer": invalid JSON}'),
])
def test_format_failure_regenerates_once_without_tools_from_the_same_evidence(
    finish_reason: str, raw: str,
) -> None:
    model = FakeLLM(Completion(content=raw, finish_reason=finish_reason), answer(FACTS, [SOURCE]))
    result = compose(model)
    assert result["result_status"] == "success"
    assert result["answer"] == FACTS
    assert len(model.calls) == 2
    retry = model.calls[1]
    assert retry["tools"] is None and retry["json_mode"] is True
    assert retry["max_tokens"] == ANSWER_MAX_TOKENS
    assert FACTS in str(retry["messages"])
    assert "invalid JSON" not in str(retry["messages"])


@pytest.mark.parametrize("reason,first", [
    ("output_truncated", Completion(content='{', finish_reason="length")),
    ("model_format", Completion(content='{', finish_reason="stop")),
])
def test_recovery_is_bounded_and_preserves_the_initial_failure_reason(
    reason: str, first: Completion,
) -> None:
    model = FakeLLM(first, Completion(content='{', finish_reason="length"), answer(FACTS, [SOURCE]))
    result = compose(model)
    assert result["result_status"] == "limited"
    assert result["degraded_reason"] == reason
    assert len(model.calls) == 2


def test_recovered_answer_still_rejects_an_invented_source() -> None:
    raw = ('{"answer":"SYNTHETIC 先登记。\n再缴费。",'
           '"source_ids":["SYNTHETIC-invented"],"status":"success"}')
    model = FakeLLM(Completion(content=raw, finish_reason="stop"), answer(FACTS, [SOURCE]))
    result = compose(model)
    assert result["result_status"] == "limited"
    assert result["degraded_reason"] == "answer_validation"
    assert len(model.calls) == 1


@pytest.mark.parametrize("raw", [
    '{"answer":"SYNTHETIC \\q","source_ids":["SYNTHETIC-source"],"status":"success"}',
    '{"answer":"SYNTHETIC \u0000","source_ids":["SYNTHETIC-source"],"status":"success"}',
    '{"answer":"SYNTHETIC","source_ids":"SYNTHETIC-source","status":"success"}',
])
def test_format_recovery_does_not_accept_other_invalid_json_or_schema(raw: str) -> None:
    model = FakeLLM(Completion(content=raw, finish_reason="stop"), Completion(content="{"))
    result = compose(model)
    assert result["result_status"] == "limited"
    assert result["degraded_reason"] == "model_format"


def test_retry_cannot_execute_a_tool_even_if_the_model_requests_one() -> None:
    model = FakeLLM(Completion(content="{"), Completion(tool_calls=(
        ToolCall(call_id="SYNTHETIC-call", name="search_place", arguments='{"query":"香樟"}'),
    )))
    result = compose(model)
    assert result["degraded_reason"] == "model_format"
    assert result["places"] == [] and result["plan"] == []
    assert len(model.calls) == 2


def test_transport_failure_does_not_spend_a_format_retry() -> None:
    model = FakeLLM(ChatUnavailable("upstream_limit"), answer(FACTS, [SOURCE]))
    result = compose(model)
    assert result["degraded_reason"] == "upstream_limit"
    assert len(model.calls) == 1
