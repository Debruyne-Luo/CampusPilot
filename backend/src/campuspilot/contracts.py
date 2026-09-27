"""Provider-independent records. All current payloads are synthetic fixtures."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=120)]
Risk = Literal["public_read", "restricted_read", "write", "sensitive", "unknown"]
Status = Literal["success", "empty", "denied", "invalid", "failed", "cancelled"]


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Evidence(Contract):
    evidence_id: Identifier
    source_id: Identifier
    source_reference: Identifier
    version: Identifier = "fixture-v1"
    locator: Identifier
    applicability: str = "synthetic demo only; not university information"
    source_url: str | None = None
    source_updated_at: str | None = None
    retrieved_at: str | None = None
    verified_at: str | None = None
    verification: Literal["synthetic"] = "synthetic"
    synthetic: Literal[True] = True


class Payload(Contract):
    synthetic: Literal[True] = True
    evidence: tuple[Evidence, ...] = Field(min_length=1)


class ServiceResult(Payload):
    kind: Literal["service"] = "service"
    service_id: Identifier
    office_id: Identifier
    label: str


class OfficeResult(Payload):
    kind: Literal["office"] = "office"
    office_id: Identifier
    place_id: Identifier
    label: str


class RouteResult(Payload):
    kind: Literal["route"] = "route"
    origin: Identifier
    destination: Identifier
    steps: tuple[str, ...]
    warning: Literal["Synthetic fixture. Do not use for navigation."] = (
        "Synthetic fixture. Do not use for navigation."
    )


ToolData = Annotated[ServiceResult | OfficeResult | RouteResult, Field(discriminator="kind")]


class ToolCall(Contract):
    call_id: Identifier
    tool_id: Identifier
    arguments: dict[str, JsonValue]


class ExecutionContext(Contract):
    """Constructed by the application, never accepted from model arguments."""

    session_id: Identifier
    task_id: Identifier
    run_id: Identifier
    allowed_tools: frozenset[str]


class ToolResult(Contract):
    call_id: Identifier
    status: Status
    data: ToolData | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.status == "success") != (self.data is not None):
            raise ValueError("Only success has data")
        if self.status in {"success", "empty"}:
            if self.error_code is not None:
                raise ValueError("Success/empty cannot contain an error")
        elif self.error_code is None:
            raise ValueError("Non-success outcome requires an error code")
        return self


class ToolDescriptor(Contract):
    tool_id: Identifier
    version: Identifier = "1"
    risk: Risk = "unknown"


class SkillDescriptor(Contract):
    skill_id: Identifier
    version: Identifier = "1"
    description: str
    instructions: str
    required_tools: tuple[Identifier, ...] = Field(min_length=1)
    completion_criteria: str
    risk: Risk = "unknown"


class PermissionDecision(Contract):
    allowed: bool
    reason: Literal["public_read_allowed", "tool_not_allowed", "risk_not_allowed"]


class TraceEvent(Contract):
    sequence: int = Field(ge=1)
    session_id: Identifier
    task_id: Identifier
    run_id: Identifier
    call_id: Identifier | None = None
    tool_id: Identifier | None = None
    component_version: str = "skeleton-v1"
    kind: Literal[
        "run_started",
        "skill_selected",
        "tool_requested",
        "permission",
        "tool_result",
        "run_finished",
    ]
    detail: str
    evidence_ids: tuple[str, ...] = ()


class TaskRequest(Contract):
    session_id: Identifier
    task_id: Identifier
    objective: Annotated[str, Field(min_length=1, max_length=2000)]
    skill_id: Identifier = "synthetic-campus-guide"
    max_steps: int = Field(default=3, ge=1, le=10)


class RunResult(Contract):
    session_id: Identifier
    task_id: Identifier
    run_id: Identifier
    status: Literal["completed", "needs_input", "failed", "cancelled"]
    task_outcome: Literal["synthetic_guidance", "unresolved"]
    results: tuple[ToolResult, ...]
    error_code: str | None = None
    synthetic: Literal[True] = True


class Session(Contract):
    session_id: Identifier
    revision: int = Field(default=0, ge=0)
    runs: tuple[RunResult, ...] = ()


class ModelRequest(Contract):
    objective: str
    allowed_tools: tuple[str, ...]
    previous_results: tuple[ToolResult, ...]


class ModelResponse(Contract):
    tool_id: Identifier
    arguments: dict[str, JsonValue]
    synthetic: Literal[True] = True
