"""Source-backed alternatives to the demo Tools, registered in their own executor."""

from pydantic import JsonValue

from campuspilot.contracts import (
    Contract,
    DirectoryOfficeResult,
    OfficeInput,
    Payload,
    SearchInput,
    ServiceSearchResult,
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


def directory_tools(repository: DirectoryRepository) -> tuple[SearchServiceTool, FindOfficeTool]:
    return SearchServiceTool(repository), FindOfficeTool(repository)
