"""Source-backed alternatives to the demo Tools, registered in their own executor."""

from pydantic import JsonValue

from campuspilot.contracts import (
    Contract,
    DirectoryOfficeResult,
    OfficeInput,
    Payload,
    PlaceSearchResult,
    SearchInput,
    ServiceSearchResult,
    TeacherSearchResult,
    ToolDescriptor,
)
from campuspilot.directory.repository import DirectoryRepository


class SearchServiceTool:
    descriptor = ToolDescriptor(tool_id="search_service", risk="public_read")
    input_model: type[Contract] = SearchInput
    output_model: type[Payload] = ServiceSearchResult

    def __init__(self, repository: DirectoryRepository) -> None:
        self.repository = repository

    def execute(self, arguments: dict[str, JsonValue]) -> ServiceSearchResult | None:
        request = SearchInput.model_validate(arguments)
        matches = self.repository.search_service(request.query, request.academic_year)
        if not matches:
            return None
        return ServiceSearchResult(matches=matches, evidence=self.repository.evidence_for(matches))


class FindOfficeTool:
    descriptor = ToolDescriptor(tool_id="find_office", risk="public_read")
    input_model: type[Contract] = OfficeInput
    output_model: type[Payload] = DirectoryOfficeResult

    def __init__(self, repository: DirectoryRepository) -> None:
        self.repository = repository

    def execute(self, arguments: dict[str, JsonValue]) -> DirectoryOfficeResult | None:
        request = OfficeInput.model_validate(arguments)
        office = self.repository.find_office(request.office_id)
        if office is None:
            return None
        return DirectoryOfficeResult(
            office=office, evidence=self.repository.evidence_for((office,))
        )


class SearchPlaceTool:
    descriptor = ToolDescriptor(tool_id="search_place", risk="public_read")
    input_model: type[Contract] = SearchInput
    output_model: type[Payload] = PlaceSearchResult

    def __init__(self, repository: DirectoryRepository) -> None:
        self.repository = repository

    def execute(self, arguments: dict[str, JsonValue]) -> PlaceSearchResult | None:
        body = SearchInput.model_validate(arguments)
        matches = self.repository.search_place(body.query)
        return (
            PlaceSearchResult(matches=matches, evidence=self.repository.evidence_for(matches))
            if matches
            else None
        )


class SearchTeacherTool:
    descriptor = ToolDescriptor(tool_id="search_teacher", risk="public_read")
    input_model: type[Contract] = SearchInput
    output_model: type[Payload] = TeacherSearchResult

    def __init__(self, repository: DirectoryRepository) -> None:
        self.repository = repository

    def execute(self, arguments: dict[str, JsonValue]) -> TeacherSearchResult | None:
        body = SearchInput.model_validate(arguments)
        matches = self.repository.search_teacher(body.query)
        return (
            TeacherSearchResult(matches=matches, evidence=self.repository.evidence_for(matches))
            if matches
            else None
        )


def directory_tools(
    repository: DirectoryRepository,
) -> tuple[SearchServiceTool, FindOfficeTool, SearchPlaceTool, SearchTeacherTool]:
    return (
        SearchServiceTool(repository),
        FindOfficeTool(repository),
        SearchPlaceTool(repository),
        SearchTeacherTool(repository),
    )
