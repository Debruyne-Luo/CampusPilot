"""One bounded workflow query; all directory reads pass through public-read tools."""

from typing import Annotated, Literal

from pydantic import Field

from campuspilot.contracts import (
    Contract,
    ExecutionContext,
    PlaceSearchResult,
    TeacherSearchResult,
    ToolCall,
    TraceEvent,
)
from campuspilot.directory.lookup import LookupInput, ServiceKey, lookup
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.directory.tools import directory_tools
from campuspilot.domain import CampusOffice, CampusPlace, CampusService, CampusTeacher
from campuspilot.evidence import SourceEvidence
from campuspilot.state import InMemoryExecutionJournal
from campuspilot.tools import ReadOnlyPermissionPolicy, ToolExecutor


class AssistInput(Contract):
    kind: Literal["service", "teacher", "place", "unknown"]
    query: Annotated[str, Field(max_length=120)] = ""
    service_key: ServiceKey = "unknown"
    audience: Literal["graduate", "undergraduate", "staff", "unknown"] = "unknown"
    academic_year: Annotated[str, Field(pattern=r"^\d{4}-\d{4}$")] | None = None


class AssistResponse(Contract):
    request_id: str
    status: Literal["success", "needs_clarification", "out_of_scope", "empty", "unavailable"]
    message: str
    services: tuple[CampusService, ...] = ()
    teachers: tuple[CampusTeacher, ...] = ()
    places: tuple[CampusPlace, ...] = ()
    office: CampusOffice | None = None
    evidence: tuple[SourceEvidence, ...] = ()
    trace: tuple[TraceEvent, ...] = ()
    notice: str = "资料待人工核验，仅提供指引，未替你办理。"


def assist(repository: DirectoryRepository, body: AssistInput, request_id: str) -> AssistResponse:
    if body.kind == "service":
        service_result = lookup(
            repository,
            LookupInput(
                service_key=body.service_key,
                audience=body.audience,
                academic_year=body.academic_year,
            ),
            request_id,
        )
        return AssistResponse(
            request_id=request_id,
            status=service_result.status,
            message=service_result.message,
            services=(service_result.service,) if service_result.service else (),
            office=service_result.office,
            places=service_result.places,
            evidence=service_result.evidence,
            trace=service_result.trace,
        )
    if body.kind == "unknown" or not body.query.strip():
        return AssistResponse(
            request_id=request_id,
            status="needs_clarification",
            message="请提供具体事务、教师姓名或地点名称。",
        )
    journal = InMemoryExecutionJournal()
    executor = ToolExecutor(directory_tools(repository), ReadOnlyPermissionPolicy(), journal)
    tool = "search_teacher" if body.kind == "teacher" else "search_place"
    context = ExecutionContext(
        session_id=f"assist-session:{request_id}",
        task_id=f"assist-task:{request_id}",
        run_id=f"assist-run:{request_id}",
        allowed_tools=frozenset({tool}),
    )
    result = executor.execute(
        ToolCall(
            call_id=f"assist-call:{request_id}", tool_id=tool, arguments={"query": body.query}
        ),
        context,
    )
    trace = journal.events(context.session_id)
    if result.status == "empty":
        return AssistResponse(
            request_id=request_id, trace=trace, status="empty", message="没有收录符合条件的记录。"
        )
    if result.status != "success" or not isinstance(
        result.data, (TeacherSearchResult, PlaceSearchResult)
    ):
        return AssistResponse(
            request_id=request_id, trace=trace, status="unavailable", message="业务查询暂不可用。"
        )
    teachers = result.data.matches if isinstance(result.data, TeacherSearchResult) else ()
    places = (
        result.data.matches
        if isinstance(result.data, PlaceSearchResult)
        else tuple(
            p for t in teachers if t.place_id for p in (repository.find_place(t.place_id),) if p
        )
    )
    places = tuple({p.place_id: p for p in places}.values())
    # Same-name/cross-campus matches are candidates; never silently pick one.
    ambiguous = len(result.data.matches) != 1
    return AssistResponse(
        request_id=request_id,
        trace=trace,
        status="needs_clarification" if ambiguous else "success",
        message="找到多个候选，请确认姓名与校区。"
        if ambiguous
        else "已查询目录，未知字段保留未知。",
        teachers=teachers,
        places=places,
        evidence=repository.evidence_for((*teachers, *places)),
    )
