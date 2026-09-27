import json
import socket
import subprocess
import sys
from dataclasses import replace
from threading import Event

import pytest
from campuspilot.agent import FakeModelProvider
from campuspilot.contracts import (
    ExecutionContext,
    ModelRequest,
    ModelResponse,
    Payload,
    SyntheticEvidence,
    TaskRequest,
    ToolCall,
    ToolDescriptor,
    ToolResult,
    TraceEvent,
)
from campuspilot.demo import build_demo, run_demo
from campuspilot.interfaces import AgentHarness, ModelProvider, SessionStore, Skill, Tool
from campuspilot.mocks import demo_tools
from campuspilot.skills import StaticSkillRegistry, demo_skill
from campuspilot.state import (
    InMemoryExecutionJournal,
    InMemorySessionStore,
    JournalError,
    SessionConflict,
)
from campuspilot.tools import ReadOnlyPermissionPolicy, ToolExecutor
from pydantic import JsonValue, ValidationError


def context() -> ExecutionContext:
    return ExecutionContext(
        session_id="s",
        task_id="t",
        run_id="r",
        allowed_tools=frozenset({"search_service"}),
    )


def call(arguments: dict[str, JsonValue] | None = None) -> ToolCall:
    return ToolCall(
        call_id="c",
        tool_id="search_service",
        arguments=arguments if arguments is not None else {"query": "synthetic service"},
    )


def request(**kwargs: object) -> TaskRequest:
    return TaskRequest.model_validate(
        {
            "session_id": "s",
            "task_id": "t",
            "objective": "synthetic service",
            **kwargs,
        }
    )


def test_demo_offline_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network prohibited")

    monkeypatch.setattr(socket, "socket", no_network)
    first = run_demo()
    assert first.model_dump_json() == run_demo().model_dump_json()
    assert first.result.status == "completed"
    assert first.result.task_outcome == "synthetic_guidance"
    assert first.session.revision == 1
    assert len(first.result.results) == 3
    for result in first.result.results:
        assert result.data is not None and result.data.synthetic
        assert all(
            e.synthetic and e.verification_status == "synthetic" for e in result.data.evidence
        )
    assert [e.sequence for e in first.trace] == list(range(1, 13))
    assert [e.kind for e in first.trace] == [
        "run_started",
        "skill_selected",
        *(["tool_requested", "permission", "tool_result"] * 3),
        "run_finished",
    ]
    assert len([e for e in first.trace if e.evidence_ids]) == 3


def test_cli() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "campuspilot", "demo"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(proc.stdout)["result"]["status"] == "completed"


def test_protocol_implementations() -> None:
    harness, sessions, _ = build_demo()
    port: AgentHarness = harness
    provider: ModelProvider = FakeModelProvider()
    store: SessionStore = sessions
    skill: Skill = demo_skill()
    tool: Tool = demo_tools()[0]
    assert port is harness and store is sessions
    assert (
        provider.respond(
            ModelRequest(
                objective="synthetic service",
                allowed_tools=("search_service",),
                previous_results=(),
            )
        ).tool_id
        == tool.descriptor.tool_id
    )
    assert skill.descriptor.risk == "public_read"


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"query": 3},
        {"query": ""},
        {"query": "synthetic service", "allowed": True},
    ],
)
def test_invalid_input_never_executes(bad: dict[str, JsonValue]) -> None:
    invoked: list[bool] = []

    def spy(arguments: dict[str, JsonValue]) -> Payload | None:
        invoked.append(True)
        return None

    tool = replace(demo_tools()[0], handler=spy)
    journal = InMemoryExecutionJournal()
    executor = ToolExecutor((tool,), ReadOnlyPermissionPolicy(), journal)
    assert executor.execute(call(bad), context()).status == "invalid"
    assert not invoked
    assert journal.events("s")[-1].detail == "invalid_input"


@pytest.mark.parametrize("risk", ["restricted_read", "write", "sensitive", "unknown"])
def test_non_public_risk_denied(risk: str) -> None:
    invoked: list[bool] = []

    def spy(arguments: dict[str, JsonValue]) -> Payload | None:
        invoked.append(True)
        return None

    descriptor = ToolDescriptor.model_validate({"tool_id": "search_service", "risk": risk})
    tool = replace(demo_tools()[0], descriptor=descriptor, handler=spy)
    journal = InMemoryExecutionJournal()
    result = ToolExecutor((tool,), ReadOnlyPermissionPolicy(), journal).execute(call(), context())
    assert result.status == "denied" and not invoked
    assert journal.events("s")[1].detail == "risk_not_allowed"


def test_allowlist_and_unknown_tool() -> None:
    journal = InMemoryExecutionJournal()
    executor = ToolExecutor(demo_tools(), ReadOnlyPermissionPolicy(), journal)
    empty_context = context().model_copy(update={"allowed_tools": frozenset()})
    assert executor.execute(call(), empty_context).error_code == "tool_not_allowed"
    unknown = ToolCall(call_id="x", tool_id="write_record", arguments={})
    assert executor.execute(unknown, context()).error_code == "unknown_tool"


def test_empty_distinct_from_failure_and_no_sensitive_trace() -> None:
    journal = InMemoryExecutionJournal()
    executor = ToolExecutor(demo_tools(), ReadOnlyPermissionPolicy(), journal)
    assert executor.execute(call({"query": "unknown synthetic value"}), context()).status == "empty"

    def broken(arguments: dict[str, JsonValue]) -> Payload | None:
        raise RuntimeError("secret-user-payload")

    failing = ToolExecutor(
        (replace(demo_tools()[0], handler=broken),), ReadOnlyPermissionPolicy(), journal
    )
    assert failing.execute(call(), context()).error_code == "tool_error"
    assert "secret-user-payload" not in str(journal.events("s"))
    assert "unknown synthetic value" not in str(journal.events("s"))


def test_wrong_tool_output_rejected() -> None:
    tools = demo_tools()

    def wrong(arguments: dict[str, JsonValue]) -> Payload | None:
        return tools[1].execute({"office_id": "synthetic:office"})

    executor = ToolExecutor(
        (replace(tools[0], handler=wrong),), ReadOnlyPermissionPolicy(), InMemoryExecutionJournal()
    )
    assert executor.execute(call(), context()).error_code == "invalid_output"


class BrokenJournal(InMemoryExecutionJournal):
    def __init__(self, fail_at: int) -> None:
        super().__init__()
        self.fail_at = fail_at

    def append(
        self,
        context: ExecutionContext,
        kind: str,
        detail: str,
        call_id: str | None = None,
        tool_id: str | None = None,
        evidence_ids: tuple[str, ...] = (),
    ) -> TraceEvent:
        if len(self.events(context.session_id)) + 1 == self.fail_at:
            raise OSError("journal unavailable")
        return super().append(context, kind, detail, call_id, tool_id, evidence_ids)


@pytest.mark.parametrize("fail_at,expected_calls", [(1, 0), (2, 0), (3, 1)])
def test_trace_failure_never_reports_success(fail_at: int, expected_calls: int) -> None:
    calls: list[bool] = []
    base = demo_tools()[0]

    def spy(arguments: dict[str, JsonValue]) -> Payload | None:
        calls.append(True)
        return base.execute(arguments)

    executor = ToolExecutor(
        (replace(base, handler=spy),), ReadOnlyPermissionPolicy(), BrokenJournal(fail_at)
    )
    with pytest.raises(JournalError):
        executor.execute(call(), context())
    assert len(calls) == expected_calls


def test_registry_validation() -> None:
    tools = demo_tools()
    with pytest.raises(ValueError, match="Duplicate Tool"):
        ToolExecutor((tools[0], tools[0]), ReadOnlyPermissionPolicy(), InMemoryExecutionJournal())
    with pytest.raises(ValueError, match="Duplicate Skill"):
        StaticSkillRegistry(
            (demo_skill(), demo_skill()), frozenset(t.descriptor.tool_id for t in tools)
        )
    with pytest.raises(ValueError, match="Unknown tool"):
        StaticSkillRegistry((demo_skill(),), frozenset())
    with pytest.raises(KeyError):
        StaticSkillRegistry((), frozenset()).get("unknown")


def test_contract_rejects_false_success_and_forged_fixture() -> None:
    with pytest.raises(ValidationError):
        ToolResult(call_id="c", status="success")
    with pytest.raises(ValidationError):
        ToolResult(call_id="c", status="failed")
    with pytest.raises(ValidationError):
        SyntheticEvidence.model_validate(
            {
                "evidence_id": "x",
                "source_id": "x",
                "source_reference": "x",
                "locator": "x",
                "synthetic": False,
            }
        )
    with pytest.raises(ValidationError):
        request(max_steps=0)


def test_sessions_continuation_isolation_and_conflict() -> None:
    harness, sessions, journal = build_demo()
    sessions.create("s")
    sessions.create("other")
    first = harness.run(request())
    second = harness.run(request())
    assert first.run_id != second.run_id
    assert sessions.get("s").runs == (first, second)
    assert sessions.get("other").runs == () and journal.events("other") == ()
    assert sessions.get("s") is not sessions.get("s")
    with pytest.raises(SessionConflict):
        sessions.create("s")
    active = sessions.begin("s")
    with pytest.raises(SessionConflict):
        harness.run(request())
    with pytest.raises(SessionConflict):
        sessions.finish(first)
    sessions.release("s", active)
    assert harness.run(request()).status == "completed"
    with pytest.raises(KeyError):
        InMemorySessionStore().get("s")


@pytest.mark.parametrize(
    "args,status,code",
    [
        ({"objective": "unknown synthetic query"}, "needs_input", "missing_evidence"),
        ({"max_steps": 1}, "failed", "step_limit"),
        ({"skill_id": "unknown"}, "failed", "unknown_skill"),
    ],
)
def test_harness_failure_paths(args: dict[str, object], status: str, code: str) -> None:
    harness, sessions, journal = build_demo()
    sessions.create("s")
    result = harness.run(request(**args))
    assert result.status == status and result.error_code == code
    assert sessions.get("s").revision == 1
    assert journal.events("s")[-1].detail == code


def test_cancel_before_execution() -> None:
    harness, sessions, journal = build_demo()
    sessions.create("s")
    cancel = Event()
    cancel.set()
    result = harness.run(request(), cancel)
    assert result.status == "cancelled" and result.results == ()
    assert [e.kind for e in journal.events("s")] == [
        "run_started",
        "skill_selected",
        "run_finished",
    ]


def test_provider_failure_and_untrusted_call() -> None:
    class BadProvider:
        def respond(self, request: ModelRequest) -> ModelResponse:
            raise RuntimeError("private model payload")

    class UntrustedProvider:
        def respond(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(tool_id="submit_payment", arguments={})

    harness, sessions, journal = build_demo()
    sessions.create("s")
    harness.model = BadProvider()
    assert harness.run(request()).error_code == "model_error"
    harness.model = UntrustedProvider()
    assert harness.run(request()).results[0].status == "denied"
    assert "private model payload" not in str(journal.events("s"))


def test_failed_run_recording_releases_session_without_success() -> None:
    harness, sessions, _ = build_demo()
    sessions.create("s")
    harness.journal = BrokenJournal(1)
    with pytest.raises(OSError):
        harness.run(request())
    assert sessions.get("s").runs == ()
    # Ownership was released, but attempt IDs are never reused.
    assert sessions.begin("s") == "run:1:2"


def test_max_length_session_identifier_does_not_lock_session() -> None:
    harness, sessions, _ = build_demo()
    session_id = "s" * 120
    sessions.create(session_id)
    assert harness.run(request(session_id=session_id)).status == "completed"


def test_cancel_after_model_response_never_executes_tool() -> None:
    cancel = Event()

    class CancellingProvider:
        def respond(self, request: ModelRequest) -> ModelResponse:
            cancel.set()
            return ModelResponse(tool_id="search_service", arguments={"query": "synthetic service"})

    harness, sessions, journal = build_demo()
    sessions.create("s")
    harness.model = CancellingProvider()
    assert harness.run(request(), cancel).status == "cancelled"
    assert not any(e.kind == "tool_requested" for e in journal.events("s"))


def test_final_journal_failure_does_not_save_completed_run() -> None:
    harness, sessions, _ = build_demo()
    sessions.create("s")
    broken = BrokenJournal(12)
    harness.journal = broken
    harness.executor.journal = broken
    with pytest.raises(OSError):
        harness.run(request())
    assert sessions.get("s").runs == ()
    assert broken.events("s")[-1].kind == "tool_result"
    assert sessions.begin("s") == "run:1:2"
