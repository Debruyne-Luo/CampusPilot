"""Shared campus domain contracts, independent of Directory implementations."""

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from campuspilot.evidence import Contract, FieldEvidence, Text

CampusId = Annotated[str, Field(pattern=r"^cdut:[a-z0-9][a-z0-9:-]*$")]


class DirectoryRecord(Contract):
    synthetic: Literal[False] = False
    verification_status: Literal["needs_review"] = "needs_review"
    field_evidence: tuple[FieldEvidence, ...] = Field(min_length=1)
    notes: tuple[Text, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def provenance_coverage(self) -> Self:
        metadata = {"synthetic", "verification_status", "field_evidence", "notes"}
        data = self.model_dump(mode="json", exclude=metadata)
        paths: dict[str, JsonValue] = {}

        def collect(value: JsonValue, path: str) -> None:
            paths[path] = value
            if isinstance(value, dict):
                for key, child in value.items():
                    collect(child, f"{path}.{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    collect(child, f"{path}.{index}")

        for key, value in data.items():
            collect(value, key)
        links = {item.field_path: item for item in self.field_evidence}
        if len(links) != len(self.field_evidence):
            raise ValueError("Duplicate field provenance path")
        for path, link in links.items():
            if path not in paths:
                raise ValueError(f"Unknown provenance path: {path}")
            if paths[path] is None and link.evidence_ids:
                raise ValueError("Unknown fields must not claim supporting evidence")
        for path, value in paths.items():
            if value is None or isinstance(value, (dict, list)) and value:
                continue
            if path in {"service_id", "office_id"}:
                continue  # Project-assigned identifiers, not university facts.
            if not any(
                link.evidence_ids and (path == prefix or path.startswith(prefix + "."))
                for prefix, link in links.items()
            ):
                raise ValueError(f"Missing field evidence: {path}")
        return self


class ServiceStep(Contract):
    mode: Literal["online", "self_service"]
    instruction: Text
    condition: Text | None = None


class AvailabilityRule(Contract):
    condition: Text
    wait: Text


class CampusService(DirectoryRecord):
    service_id: CampusId
    name: Text
    aliases: tuple[Text, ...]
    department: Text
    office_id: CampusId | None
    audience: Text
    academic_year: Annotated[str, Field(pattern=r"^\d{4}-\d{4}$")] | None = None
    modes: tuple[Literal["online", "self_service"], ...] = Field(min_length=1)
    entry_points: tuple[Text, ...]
    required_materials: tuple[Text, ...] | None = None
    required_inputs: tuple[Text, ...] | None = None
    steps: tuple[ServiceStep, ...] = Field(min_length=1)
    availability: tuple[AvailabilityRule, ...] | None = None
    fees: tuple[Text, ...] | None = None
    limits: tuple[Text, ...] | None = None


class PublicContact(Contract):
    label: Text
    value: Text


class CampusOffice(DirectoryRecord):
    """An organizational entry; a known department does not imply a known location."""

    office_id: CampusId
    name: Text
    location: Text | None = None
    office_hours: Text | None = None
    contacts: tuple[PublicContact, ...] | None = None
