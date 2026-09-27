"""Entirely synthetic data: no real university identifiers, coordinates or contacts."""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import JsonValue

from campuspilot.contracts import (
    Contract,
    Evidence,
    Identifier,
    OfficeResult,
    Payload,
    RouteResult,
    ServiceResult,
    ToolDescriptor,
)


class SearchInput(Contract):
    query: Identifier


class OfficeInput(Contract):
    office_id: Identifier


class RouteInput(Contract):
    origin: Identifier
    destination: Identifier


def evidence(name: str) -> tuple[Evidence, ...]:
    return (
        Evidence(
            evidence_id=f"synthetic:{name}",
            source_id="synthetic:fixtures",
            source_reference="synthetic:offline-demo",
            locator=name,
        ),
    )


def search_service(arguments: dict[str, JsonValue]) -> Payload | None:
    request = SearchInput.model_validate(arguments)
    if request.query != "synthetic service":
        return None
    return ServiceResult(
        service_id="synthetic:service",
        office_id="synthetic:office",
        label="Synthetic service",
        evidence=evidence("service"),
    )


def find_office(arguments: dict[str, JsonValue]) -> Payload | None:
    request = OfficeInput.model_validate(arguments)
    if request.office_id != "synthetic:office":
        return None
    return OfficeResult(
        office_id="synthetic:office",
        place_id="synthetic:destination",
        label="Synthetic office",
        evidence=evidence("office"),
    )


def route_plan(arguments: dict[str, JsonValue]) -> Payload | None:
    request = RouteInput.model_validate(arguments)
    if (request.origin, request.destination) != ("synthetic:origin", "synthetic:destination"):
        return None
    return RouteResult(
        origin=request.origin,
        destination=request.destination,
        steps=("Synthetic origin", "Synthetic destination"),
        evidence=evidence("route"),
    )


@dataclass(frozen=True)
class MockTool:
    descriptor: ToolDescriptor
    input_model: type[Contract]
    output_model: type[Payload]
    handler: Callable[[dict[str, JsonValue]], Payload | None]

    def execute(self, arguments: dict[str, JsonValue]) -> Payload | None:
        return self.handler(arguments)


def demo_tools() -> tuple[MockTool, ...]:
    return (
        MockTool(
            ToolDescriptor(tool_id="search_service", risk="public_read"),
            SearchInput,
            ServiceResult,
            search_service,
        ),
        MockTool(
            ToolDescriptor(tool_id="find_office", risk="public_read"),
            OfficeInput,
            OfficeResult,
            find_office,
        ),
        MockTool(
            ToolDescriptor(tool_id="route_plan", risk="public_read"),
            RouteInput,
            RouteResult,
            route_plan,
        ),
    )
