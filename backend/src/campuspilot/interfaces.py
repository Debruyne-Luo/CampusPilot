"""Small synchronous ports; no production orchestration framework selected."""

from threading import Event
from typing import Protocol

from pydantic import JsonValue

from campuspilot.contracts import (
    Contract,
    ExecutionContext,
    ModelRequest,
    ModelResponse,
    Payload,
    PermissionDecision,
    RunResult,
    Session,
    SkillDescriptor,
    TaskRequest,
    ToolDescriptor,
    TraceEvent,
)


class ModelProvider(Protocol):
    def respond(self, request: ModelRequest) -> ModelResponse: ...


class PermissionPolicy(Protocol):
    def decide(
        self,
        descriptor: ToolDescriptor,
        context: ExecutionContext,
    ) -> PermissionDecision: ...


class AgentHarness(Protocol):
    def run(self, request: TaskRequest, cancel: Event | None = None) -> RunResult: ...


class SessionStore(Protocol):
    def create(self, session_id: str) -> Session: ...
    def get(self, session_id: str) -> Session: ...
    def begin(self, session_id: str) -> str: ...
    def finish(self, result: RunResult) -> None: ...
    def release(self, session_id: str, run_id: str) -> None: ...


class Skill(Protocol):
    @property
    def descriptor(self) -> SkillDescriptor: ...


class Tool(Protocol):
    @property
    def descriptor(self) -> ToolDescriptor: ...
    @property
    def input_model(self) -> type[Contract]: ...
    @property
    def output_model(self) -> type[Payload]: ...
    def execute(self, arguments: dict[str, JsonValue]) -> Payload | None: ...


class ExecutionJournal(Protocol):
    def append(
        self,
        context: ExecutionContext,
        kind: str,
        detail: str,
        call_id: str | None = None,
        tool_id: str | None = None,
        evidence_ids: tuple[str, ...] = (),
    ) -> TraceEvent: ...
    def events(self, session_id: str) -> tuple[TraceEvent, ...]: ...
