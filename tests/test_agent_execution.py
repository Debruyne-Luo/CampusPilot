"""Offline authorization and metadata-only audit contracts for the Agent boundary."""

import asyncio
import json
from collections.abc import Awaitable
from typing import Any

import pytest
from campuspilot.agent.execution import ExecutionBoundary
from campuspilot.contracts import ExecutionContext, ToolDescriptor
from campuspilot.tools.base import ToolError, ToolRegistry
from pydantic import BaseModel, Field, JsonValue


class Params(BaseModel):
    query: str = Field(min_length=1)


class FakeTool:
    description = "SYNTHETIC public lookup"
    params_model: type[BaseModel] = Params

    def __init__(self, name: str = "search_place", fault: Exception | None = None) -> None:
        self.name = name
        self.calls = 0
        self.fault = fault

    def run(self, params: Any) -> dict[str, JsonValue]:
        self.calls += 1
        if self.fault is not None:
            raise self.fault
        return {"answer": params.query}


class Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, JsonValue]]] = []

    def __call__(self, event: str, record: dict[str, JsonValue]) -> None:
        self.events.append((event, record))


def context(*allowed: str) -> ExecutionContext:
    return ExecutionContext(
        session_id="SYNTHETIC-session",
        task_id="SYNTHETIC-task",
        run_id="SYNTHETIC-run",
        allowed_tools=frozenset(allowed),
    )


def test_context_denial_precedes_tool_side_effects_and_other_context_can_run() -> None:
    tool, audit = FakeTool(), Audit()
    registry = ToolRegistry((tool,))
    denied = ExecutionBoundary(context(), audit=audit)
    with pytest.raises(ToolError, match="^permission_denied$"):
        denied.call_tool(
            registry,
            tool.name,
            {"query": "SYNTHETIC private input", "allowed_tools": [tool.name]},
        )
    assert tool.calls == 0
    assert [r["outcome"] for _, r in audit.events] == ["denied", "denied"]
    allowed = ExecutionBoundary(context(tool.name), audit=audit)
    assert allowed.call_tool(registry, tool.name, {"query": "SYNTHETIC"}) == {
        "answer": "SYNTHETIC"
    }
    assert tool.calls == 1
    assert [r["outcome"] for _, r in audit.events[-2:]] == ["allowed", "success"]
    assert "private input" not in json.dumps(audit.events)


def test_registry_entry_and_context_allowance_cannot_supply_missing_risk() -> None:
    tool = FakeTool("custom_lookup")
    registry = ToolRegistry((tool,))
    audit = Audit()
    for declarations in ((), (ToolDescriptor(tool_id=tool.name),)):
        boundary = ExecutionBoundary(context(tool.name), descriptors=declarations, audit=audit)
        with pytest.raises(ToolError, match="^permission_denied$"):
            boundary.call_tool(registry, tool.name, {"query": "SYNTHETIC"})
    assert tool.calls == 0
    # The public registry contract stays unchanged for external consumers and test doubles.
    assert registry.call(tool.name, {"query": "SYNTHETIC"}) == {"answer": "SYNTHETIC"}


def test_application_must_declare_and_allow_a_custom_public_capability() -> None:
    tool, audit = FakeTool("custom_lookup"), Audit()
    declarations = (ToolDescriptor(tool_id=tool.name, risk="public_read"),)
    registry = ToolRegistry((tool,))
    with pytest.raises(ToolError, match="^permission_denied$"):
        ExecutionBoundary(descriptors=declarations, audit=audit).call_tool(
            registry, tool.name, {"query": "SYNTHETIC"}
        )
    assert tool.calls == 0
    boundary = ExecutionBoundary(context(tool.name), descriptors=declarations, audit=audit)
    assert boundary.call_tool(registry, tool.name, {"query": "SYNTHETIC"})["answer"] == (
        "SYNTHETIC"
    )


@pytest.mark.parametrize("risk", ["restricted_read", "write", "sensitive", "unknown"])
def test_nonpublic_risk_denied_even_when_allowed(risk: Any) -> None:
    tool = FakeTool()
    boundary = ExecutionBoundary(
        context(tool.name),
        descriptors=(ToolDescriptor(tool_id=tool.name, risk=risk),),
        audit=Audit(),
    )
    with pytest.raises(ToolError, match="^permission_denied$"):
        boundary.call_tool(ToolRegistry((tool,)), tool.name, {"query": "SYNTHETIC"})
    assert tool.calls == 0


def test_unknown_tools_and_invalid_arguments_keep_existing_error_codes() -> None:
    tool, audit = FakeTool(), Audit()
    boundary, registry = ExecutionBoundary(audit=audit), ToolRegistry((tool,))
    with pytest.raises(ToolError, match="^unknown_tool$"):
        boundary.call_tool(registry, "SYNTHETIC-private-tool-name", {})
    with pytest.raises(ToolError, match="^invalid_arguments$"):
        boundary.call_tool(registry, tool.name, {"query": ""})
    assert tool.calls == 0
    encoded = json.dumps(audit.events)
    assert "SYNTHETIC-private-tool-name" not in encoded
    assert audit.events[-1][1] == {
        "capability": "search_place",
        "phase": "result",
        "outcome": "failed",
        "error_type": "ToolError",
        "error_code": "invalid_arguments",
    }


@pytest.mark.parametrize(
    "fault", [RuntimeError("SYNTHETIC-secret"), ToolError("SYNTHETIC-secret")]
)
def test_tool_fault_audits_only_type_and_reraises_original(fault: Exception) -> None:
    tool, audit = FakeTool(fault=fault), Audit()
    with pytest.raises(type(fault)) as caught:
        ExecutionBoundary(audit=audit).call_tool(
            ToolRegistry((tool,)), tool.name, {"query": "SYNTHETIC-private-input"}
        )
    assert caught.value is fault
    assert audit.events[-1][1]["error_type"] == type(fault).__name__
    assert "SYNTHETIC" not in json.dumps(audit.events)


@pytest.mark.parametrize("capability", ["jev_assess", "search_web", "undeclared_lookup"])
def test_async_denial_precedes_even_coroutine_creation(capability: str) -> None:
    calls: list[str] = []

    async def result() -> str:
        return "SYNTHETIC"

    def operation() -> Awaitable[str]:
        calls.append("created")
        return result()

    boundary = ExecutionBoundary(context(), audit=Audit())
    with pytest.raises(ToolError, match="^permission_denied$"):
        asyncio.run(boundary.run(capability, operation))
    assert calls == []


@pytest.mark.parametrize("capability", ["jev_assess", "search_web"])
def test_direct_public_capability_preserves_result_and_records_success(capability: str) -> None:
    result = object()

    async def operation() -> object:
        return result

    audit = Audit()
    boundary = ExecutionBoundary(audit=audit)
    assert asyncio.run(boundary.run(capability, operation)) is result
    assert [r["outcome"] for _, r in audit.events] == ["allowed", "success"]
    assert all(event == "execution" for event, _ in audit.events)


@pytest.mark.parametrize("cancelled", [False, True])
def test_async_failure_and_cancellation_are_audited_then_propagated(cancelled: bool) -> None:
    fault = asyncio.CancelledError("SYNTHETIC-secret") if cancelled else RuntimeError(
        "SYNTHETIC-secret"
    )

    async def operation() -> None:
        raise fault

    audit = Audit()
    with pytest.raises(type(fault)) as caught:
        asyncio.run(ExecutionBoundary(audit=audit).run("search_web", operation))
    assert caught.value is fault
    assert audit.events[-1][1]["outcome"] == ("cancelled" if cancelled else "failed")
    assert audit.events[-1][1]["error_type"] == type(fault).__name__
    assert "SYNTHETIC-secret" not in json.dumps(audit.events)


def test_permission_audit_failure_prevents_execution() -> None:
    tool = FakeTool()

    def unavailable(event: str, record: dict[str, JsonValue]) -> None:
        raise RuntimeError("SYNTHETIC audit unavailable")

    with pytest.raises(RuntimeError, match="audit unavailable"):
        ExecutionBoundary(audit=unavailable).call_tool(
            ToolRegistry((tool,)), tool.name, {"query": "SYNTHETIC"}
        )
    assert tool.calls == 0


def test_default_audit_uses_structured_event_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    def record(event: str, **fields: object) -> None:
        events.append((event, fields))

    monkeypatch.setattr("campuspilot.agent.execution.record_event", record)
    tool = FakeTool()
    clock = iter((1.0, 1.125))
    monkeypatch.setattr("campuspilot.agent.execution.time.monotonic", lambda: next(clock))
    ExecutionBoundary().call_tool(ToolRegistry((tool,)), tool.name, {"query": "SYNTHETIC"})
    assert events[-1] == (
        "execution",
        {
            "capability": "search_place", "phase": "result", "outcome": "success",
            "elapsed_ms": 125.0,
        },
    )


def test_argument_decode_failure_is_recorded_without_untrusted_name() -> None:
    audit = Audit()
    ExecutionBoundary(audit=audit).invalid_arguments("SYNTHETIC-private-prompt")
    assert audit.events[-1] == (
        "execution", {
            "capability": "undeclared", "phase": "result", "outcome": "failed",
            "error_type": "ToolError", "error_code": "invalid_arguments",
        },
    )
