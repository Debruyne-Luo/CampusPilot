"""Resolve workflow references against the local snapshot; never parse model coordinates."""

from typing import Annotated, Literal
from urllib.parse import urlencode

from pydantic import Field, JsonValue, model_validator

from campuspilot.contracts import Contract
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.domain import CampusId, CampusPlace


class AnswerEnvelope(Contract):
    schema_version: Literal[1]
    status: Literal["success", "needs_clarification", "out_of_scope", "empty", "unavailable"]
    answer: Annotated[str, Field(min_length=1, max_length=100_000, pattern=r"\S")]
    service_ids: tuple[CampusId, ...] = Field(default=(), max_length=8)
    teacher_ids: tuple[CampusId, ...] = Field(default=(), max_length=8)
    place_ids: tuple[CampusId, ...] = Field(default=(), max_length=25)

    @model_validator(mode="after")
    def reference_scope(self) -> AnswerEnvelope:
        for ids in (self.service_ids, self.teacher_ids, self.place_ids):
            if len(set(ids)) != len(ids):
                raise ValueError("Duplicate reference")
        if self.status not in {"success", "needs_clarification"} and (
            self.service_ids or self.teacher_ids or self.place_ids
        ):
            raise ValueError("Unsuccessful replies cannot link records")
        return self


def place_card(place: CampusPlace) -> dict[str, JsonValue]:
    data = place.model_dump(mode="json")
    data["navigation_url"] = None
    pos = place.position
    if pos and pos.coordinate_system == "GCJ02" and pos.verification_status == "confirmed":
        data["navigation_url"] = "https://uri.amap.com/navigation?" + urlencode(
            {
                "to": f"{pos.longitude},{pos.latitude},{place.name}",
                "mode": "walk",
                "src": "CampusPilot",
                "coordinate": "gaode",
                "callnative": "0",
            }
        )
    return data


def resolve_cards(repository: DirectoryRepository, reply: AnswerEnvelope) -> dict[str, JsonValue]:
    services = tuple(repository.find_service(key) for key in reply.service_ids)
    teachers = tuple(repository.find_teacher(key) for key in reply.teacher_ids)
    places = tuple(repository.find_place(key) for key in reply.place_ids)
    if any(x is None for x in (*services, *teachers, *places)):
        raise ValueError("Unknown workflow reference")
    related: set[str] = set()
    for service in services:
        if service:
            related.update(p.place_id for p in repository.service_places(service))
    for teacher in teachers:
        if teacher and teacher.place_id:
            related.add(teacher.place_id)
    if (services or teachers) and set(reply.place_ids) - related:
        raise ValueError("Unrelated workflow place reference")
    return {
        "services": [s.model_dump(mode="json") for s in services if s],
        "teachers": [t.model_dump(mode="json") for t in teachers if t],
        "places": [place_card(p) for p in places if p],
    }
