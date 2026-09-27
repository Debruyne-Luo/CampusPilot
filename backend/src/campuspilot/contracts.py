"""Provider-independent execution records and discriminated Tool results."""

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from campuspilot.domain import CampusOffice, CampusService, DirectoryRecord
from campuspilot.evidence import Contract as Contract
from campuspilot.evidence import Evidence as Evidence
from campuspilot.evidence import FieldEvidence as FieldEvidence
from campuspilot.evidence import Identifier as Identifier
from campuspilot.evidence import Payload as Payload
from campuspilot.evidence import SourceEvidence as SourceEvidence
from campuspilot.evidence import SyntheticEvidence as SyntheticEvidence
from campuspilot.evidence import SyntheticPayload

Risk = Literal["public_read", "restricted_read", "write", "sensitive", "unknown"]
Status = Literal["success", "empty", "denied", "invalid", "failed", "cancelled"]


class ServiceResult(SyntheticPayload):
    kind: Literal["service"] = "service"
    service_id: Identifier
    office_id: Identifier
    label: str


class OfficeResult(SyntheticPayload):
    kind: Literal["office"] = "office"
    office_id: Identifier
    place_id: Identifier
    label: str


class RouteResult(SyntheticPayload):
    kind: Literal["route"] = "route"
    origin: Identifier
    destination: Identifier
    steps: tuple[str, ...]
    warning: Literal["Synthetic fixture. Do not use for navigation."] = (
        "Synthetic fixture. Do not use for navigation."
    )


class DirectoryPayload(Payload):
    synthetic: Literal[False] = False
    evidence: tuple[SourceEvidence, ...] = Field(min_length=1)
    notice: Literal["Source-backed guidance; needs human review. No action was performed."] = (
        "Source-backed guidance; needs human review. No action was performed."
    )


class ServiceSearchResult(DirectoryPayload):
    kind: Literal["directory_services"] = "directory_services"
    matches: tuple[CampusService, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def referenced_evidence_present(self) -> Self:
        check_result_evidence(self.matches, self.evidence)
        return self


class DirectoryOfficeResult(DirectoryPayload):
    kind: Literal["directory_office"] = "directory_office"
    office: CampusOffice

    @model_validator(mode="after")
    def referenced_evidence_present(self) -> Self:
        check_result_evidence((self.office,), self.evidence)
        return self


def check_result_evidence(
    records: tuple[DirectoryRecord, ...], evidence: tuple[SourceEvidence, ...]
) -> None:
    referenced = {
        eid for record in records for link in record.field_evidence for eid in link.evidence_ids
    }
    if referenced != {item.evidence_id for item in evidence}:
        raise ValueError("Result evidence must exactly resolve its field references")


ToolData = Annotated[
    ServiceResult | OfficeResult | RouteResult | ServiceSearchResult | DirectoryOfficeResult,
    Field(discriminator="kind"),
]


class SearchInput(Contract):
    query: Annotated[str, Field(min_length=1, max_length=120, pattern=r"\S")]
    academic_year: Annotated[str, Field(pattern=r"^\d{4}-\d{4}$")] | None = None


class OfficeInput(Contract):
    office_id: Identifier


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

    @model_validator(mode="after")
    def synthetic_results_only(self) -> Self:
        if any(result.data and not result.data.synthetic for result in self.results):
            raise ValueError("The fake harness cannot contain real directory results")
        return self


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
