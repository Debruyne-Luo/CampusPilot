"""Shared campus domain contracts, independent of Directory implementations."""

from datetime import date
from typing import Annotated, Literal, Self
from urllib.parse import parse_qsl

from pydantic import Field, HttpUrl, JsonValue, model_validator

from campuspilot.evidence import Contract, FieldEvidence, Text

CampusId = Annotated[str, Field(pattern=r"^cdut:[a-z0-9][a-z0-9:-]*$")]


class DirectoryRecord(Contract):
    synthetic: Literal[False] = False
    verification_status: Literal["needs_review"] = "needs_review"
    field_evidence: tuple[FieldEvidence, ...] = Field(min_length=1)
    notes: tuple[Text, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def provenance_coverage(self) -> Self:
        metadata = {"synthetic", "verification_status", "field_evidence", "notes", "position"}
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
        # Project notes are optional provenance; a source-backed note may cite its own evidence.
        for index, note in enumerate(self.notes):
            paths[f"notes.{index}"] = note
        links = {item.field_path: item for item in self.field_evidence}
        if len(links) != len(self.field_evidence):
            raise ValueError("Duplicate field provenance path")
        for path, link in links.items():
            if path not in paths:
                raise ValueError(f"Unknown provenance path: {path}")
            if paths[path] is None and link.evidence_ids:
                raise ValueError("Unknown fields must not claim supporting evidence")
        for path, value in paths.items():
            if path.startswith("notes."):
                continue
            if value is None or isinstance(value, (dict, list)) and value:
                continue
            if path in {"service_id", "office_id", "place_id", "teacher_id"}:
                continue  # Project-assigned identifiers, not university facts.
            if not any(
                link.evidence_ids and (path == prefix or path.startswith(prefix + "."))
                for prefix, link in links.items()
            ):
                raise ValueError(f"Missing field evidence: {path}")
        return self


class ServiceStep(Contract):
    mode: Literal["online", "self_service", "in_person"]
    instruction: Text
    condition: Text | None = None
    place_ids: tuple[CampusId, ...] | None = None


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
    modes: tuple[Literal["online", "self_service", "in_person"], ...] = Field(min_length=1)
    entry_points: tuple[Text, ...]
    summary: Text | None = None
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


class MapPosition(Contract):
    """Spatial evidence is separate from official service/teacher evidence."""

    longitude: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    latitude: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    coordinate_system: Literal["GCJ02", "WGS84"]
    source_kind: Literal["map_provider", "onsite_confirmation"]
    source_url: HttpUrl
    retrieved_at: date
    verification_status: Literal["needs_review", "confirmed"] = "needs_review"
    confirmed_at: date | None = None
    reviewer: Text | None = None
    note: Text

    @model_validator(mode="after")
    def spatial_review(self) -> Self:
        if (
            self.source_url.scheme != "https"
            or self.source_url.username
            or self.source_url.password
        ):
            raise ValueError("Spatial reference requires a credential-free HTTPS URL")
        if any(
            key.casefold() in {"key", "api_key", "token", "jscode", "password"}
            for key, _ in parse_qsl(self.source_url.query or "")
        ):
            raise ValueError("Spatial references cannot publish API credentials")
        if self.verification_status == "confirmed":
            if self.confirmed_at is None or self.reviewer is None:
                raise ValueError("Confirmed position requires reviewer and date")
        elif self.confirmed_at is not None or self.reviewer is not None:
            raise ValueError("Unconfirmed position cannot claim review")
        return self


class CampusPlace(DirectoryRecord):
    place_id: CampusId
    name: Text
    aliases: tuple[Text, ...]
    campus: Text | None
    category: Literal["teaching", "office", "library", "dining", "service", "sports", "gate"]
    address_detail: Text | None = None
    tags: tuple[Text, ...] | None = None
    position: MapPosition | None = None


class CampusTeacher(DirectoryRecord):
    teacher_id: CampusId
    name: Text
    aliases: tuple[Text, ...]
    department: Text
    campus: Text | None = None
    office: Text | None = None
    place_id: CampusId | None = None
    profile_url: HttpUrl
