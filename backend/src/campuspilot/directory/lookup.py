"""Bounded business lookup: applicability checks, then permission-checked directory tools.

This is not an LLM or a second Agent. Dify supplies extracted fields; the server checks
the supported public-data scope and resolves office IDs from actual service records.
"""

from typing import Annotated, Literal

from pydantic import Field

from campuspilot.contracts import (
    Contract,
    DirectoryOfficeResult,
    ExecutionContext,
    ServiceSearchResult,
    ToolCall,
    TraceEvent,
)
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.directory.tools import directory_tools
from campuspilot.domain import CampusOffice, CampusPlace, CampusService
from campuspilot.evidence import SourceEvidence
from campuspilot.state import InMemoryExecutionJournal
from campuspilot.tools import ReadOnlyPermissionPolicy, ToolExecutor

ServiceKey = Literal[
    "campus_card_loss", "campus_card_replacement", "enrollment_proof", "tuition_receipt", "unknown"
]


class LookupInput(Contract):
    service_key: ServiceKey
    audience: Literal["graduate", "undergraduate", "staff", "unknown"] = "unknown"
    academic_year: Annotated[str, Field(pattern=r"^\d{4}-\d{4}$")] | None = None


class LookupResponse(Contract):
    request_id: str
    status: Literal["success", "needs_clarification", "out_of_scope", "empty", "unavailable"]
    message: str
    service: CampusService | None = None
    office: CampusOffice | None = None
    places: tuple[CampusPlace, ...] = ()
    evidence: tuple[SourceEvidence, ...] = ()
    trace: tuple[TraceEvent, ...] = ()
    notice: Literal["资料待人工核验，仅提供指引，未替你办理。"] = (
        "资料待人工核验，仅提供指引，未替你办理。"
    )


def lookup(repository: DirectoryRepository, body: LookupInput, request_id: str) -> LookupResponse:
    def clarify(message: str) -> LookupResponse:
        return LookupResponse(request_id=request_id, status="needs_clarification", message=message)

    if body.service_key == "unknown":
        return clarify("你想查询校园卡挂失、补办、在读证明，还是学杂费电子票据？")
    if body.service_key == "enrollment_proof":
        if body.audience == "unknown":
            return clarify("你要查询的是研究生在读证明，还是本科生在读证明？目前资料仅覆盖研究生。")
        if body.audience != "graduate":
            return LookupResponse(
                request_id=request_id,
                status="out_of_scope",
                message="目前只有研究生在读证明资料，不能据此提供本科生或教职工的办理流程。",
            )
    if body.service_key == "tuition_receipt":
        if body.academic_year is None:
            return clarify("你要查询哪个学年的学杂费电子票据？目前资料仅覆盖 2026-2027 学年。")
        if body.academic_year != "2026-2027":
            return LookupResponse(
                request_id=request_id,
                status="out_of_scope",
                message="当前资料仅适用于 2026-2027 学年，不能用于所查询的其他学年。",
            )

    query = {
        "campus_card_loss": "校园卡挂失",
        "campus_card_replacement": "校园卡补办",
        "enrollment_proof": "研究生在读证明",
        "tuition_receipt": "缴费票据",
    }[body.service_key]
    journal = InMemoryExecutionJournal()
    executor = ToolExecutor(directory_tools(repository), ReadOnlyPermissionPolicy(), journal)
    context = ExecutionContext(
        session_id=f"lookup-session:{request_id}",
        task_id=f"lookup-task:{request_id}",
        run_id=f"lookup-run:{request_id}",
        allowed_tools=frozenset({"search_service", "find_office"}),
    )
    search = executor.execute(
        ToolCall(
            call_id=f"lookup-search:{request_id}",
            tool_id="search_service",
            arguments={"query": query, "academic_year": body.academic_year},
        ),
        context,
    )

    def failed(message: str, empty: bool = False) -> LookupResponse:
        return LookupResponse(
            request_id=request_id,
            status="empty" if empty else "unavailable",
            message=message,
            trace=journal.events(context.session_id),
        )

    if search.status == "empty":
        return failed("目录中没有符合条件的记录，不能补造办理流程。", empty=True)
    if search.status != "success" or not isinstance(search.data, ServiceSearchResult):
        return failed("事务查询暂不可用，本次没有获得可用于回答的业务结果。")
    if len(search.data.matches) != 1:
        return LookupResponse(
            request_id=request_id,
            status="needs_clarification",
            message="查询到多个事务，请补充更具体的事项名称。",
            trace=journal.events(context.session_id),
        )
    service = search.data.matches[0]
    office = None
    sources = {e.evidence_id: e for e in search.data.evidence}
    if service.office_id:
        office_result = executor.execute(
            ToolCall(
                call_id=f"lookup-office:{request_id}",
                tool_id="find_office",
                arguments={"office_id": service.office_id},
            ),
            context,
        )
        if office_result.status != "success" or not isinstance(
            office_result.data, DirectoryOfficeResult
        ):
            return failed("事务信息已找到，但负责部门查询未完成；本次业务查询未成功。")
        office = office_result.data.office
        sources.update({e.evidence_id: e for e in office_result.data.evidence})
    places = repository.service_places(service)
    sources.update({e.evidence_id: e for e in repository.evidence_for(places)})
    return LookupResponse(
        request_id=request_id,
        status="success",
        message="已查询事务与负责部门；来源仍待复核，未知字段必须保留未知。",
        service=service,
        office=office,
        places=places,
        evidence=tuple(sources[k] for k in sorted(sources)),
        trace=journal.events(context.session_id),
    )
