from campuspilot.agent import FakeAgentHarness, FakeModelProvider
from campuspilot.contracts import Contract, RunResult, Session, TaskRequest, TraceEvent
from campuspilot.mocks import demo_tools
from campuspilot.skills import StaticSkillRegistry, demo_skill
from campuspilot.state import InMemoryExecutionJournal, InMemorySessionStore
from campuspilot.tools import ReadOnlyPermissionPolicy, ToolExecutor


class DemoOutput(Contract):
    notice: str = "SYNTHETIC OFFLINE DEMO. No university information or navigation."
    result: RunResult
    session: Session
    trace: tuple[TraceEvent, ...]


def build_demo() -> tuple[FakeAgentHarness, InMemorySessionStore, InMemoryExecutionJournal]:
    sessions = InMemorySessionStore()
    journal = InMemoryExecutionJournal()
    executor = ToolExecutor(demo_tools(), ReadOnlyPermissionPolicy(), journal)
    skills = StaticSkillRegistry((demo_skill(),), executor.tool_ids)
    harness = FakeAgentHarness(FakeModelProvider(), sessions, skills, executor, journal)
    return harness, sessions, journal


def run_demo() -> DemoOutput:
    harness, sessions, journal = build_demo()
    sessions.create("synthetic-session")
    result = harness.run(
        TaskRequest(
            session_id="synthetic-session",
            task_id="synthetic-task",
            objective="synthetic service",
        )
    )
    return DemoOutput(
        result=result,
        session=sessions.get("synthetic-session"),
        trace=journal.events("synthetic-session"),
    )
