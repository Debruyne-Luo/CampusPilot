"""Load only explicit local files; validate the whole snapshot before exposing records."""

import re
import unicodedata
from pathlib import Path
from typing import Self

from pydantic import TypeAdapter

from campuspilot.domain import (
    CampusOffice,
    CampusPlace,
    CampusService,
    CampusTeacher,
    DirectoryRecord,
)
from campuspilot.evidence import SourceEvidence


class DirectoryRepository:
    def __init__(
        self,
        services: tuple[CampusService, ...],
        offices: tuple[CampusOffice, ...],
        sources: tuple[SourceEvidence, ...],
        places: tuple[CampusPlace, ...] = (),
        teachers: tuple[CampusTeacher, ...] = (),
    ) -> None:
        # Revalidate model instances too: model_copy/model_construct can skip validators.
        services = tuple(CampusService.model_validate(x.model_dump()) for x in services)
        offices = tuple(CampusOffice.model_validate(x.model_dump()) for x in offices)
        sources = tuple(SourceEvidence.model_validate(x.model_dump()) for x in sources)
        places = tuple(CampusPlace.model_validate(x.model_dump()) for x in places)
        teachers = tuple(CampusTeacher.model_validate(x.model_dump()) for x in teachers)
        self._services = {x.service_id: x for x in services}
        self._offices = {x.office_id: x for x in offices}
        self._sources = {x.evidence_id: x for x in sources}
        self._places = {x.place_id: x for x in places}
        self._teachers = {x.teacher_id: x for x in teachers}
        if len(self._places) != len(places) or len(self._teachers) != len(teachers):
            raise ValueError("Duplicate place or teacher identifier")
        ids = [*self._services, *self._offices, *self._places, *self._teachers]
        if len(ids) != len(set(ids)):
            raise ValueError("Directory identifiers must be distinct")
        if (len(self._services), len(self._offices), len(self._sources)) != (
            len(services),
            len(offices),
            len(sources),
        ):
            raise ValueError("Duplicate service, office or evidence identifier")
        if set(self._services) & set(self._offices):
            raise ValueError("Service and office identifiers must be distinct")
        for source in sources:
            host = source.source_url.host if source.source_url else ""
            if source.source_authority.startswith("official_"):
                if host != "cdut.edu.cn" and not (host or "").endswith(".cdut.edu.cn"):
                    raise ValueError("Directory requires official CDUT sources for official claims")
            elif source.source_authority == "map_provider":
                if (
                    host != "ditu.amap.com"
                    or source.access_method != "provider_api"
                    or source.source_url is None
                    or source.source_url.scheme != "https"
                    or not re.fullmatch(r"/place/[A-Za-z0-9]{8,32}", source.source_url.path or "")
                    or source.source_url.query
                ):
                    raise ValueError("Provider evidence requires an Amap public POI reference")
            elif source.access_method != "user_message" or source.source_url is not None:
                raise ValueError(
                    "User supplements must be explicitly attributed without a source URL"
                )
            if not source.evidence_id.startswith("cdut:") or not source.source_id.startswith(
                "cdut:"
            ):
                raise ValueError("CDUT evidence must use the cdut namespace")
        for record in (*services, *offices, *places, *teachers):
            for link in record.field_evidence:
                if set(link.evidence_ids) - self._sources.keys():
                    raise ValueError("Unresolved field evidence reference")
        for service in services:
            if service.office_id is not None and service.office_id not in self._offices:
                raise ValueError("Unresolved office reference")
            if service.office_id is not None:
                office = self._offices[service.office_id]
                if service.department != office.name:
                    raise ValueError("Office does not match the responsible department")
            for step in service.steps:
                if set(step.place_ids or ()) - self._places.keys():
                    raise ValueError("Unresolved service place reference")
        for teacher in teachers:
            host = teacher.profile_url.host or ""
            if teacher.profile_url.scheme != "https" or not host.endswith(".cdut.edu.cn"):
                raise ValueError("Teacher profile requires an official HTTPS URL")
            if teacher.place_id is not None:
                place = self._places.get(teacher.place_id)
                if place is None or teacher.office is None:
                    raise ValueError("Teacher location needs an office and existing place")
                if teacher.campus is None or teacher.campus != place.campus:
                    raise ValueError("Teacher and place must have the same explicit campus")

    @classmethod
    def load(cls, directory: Path) -> Self:
        services = TypeAdapter(tuple[CampusService, ...]).validate_json(
            (directory / "services.json").read_bytes()
        )
        offices = TypeAdapter(tuple[CampusOffice, ...]).validate_json(
            (directory / "offices.json").read_bytes()
        )
        sources = TypeAdapter(tuple[SourceEvidence, ...]).validate_json(
            (directory / "sources.json").read_bytes()
        )
        places = (
            TypeAdapter(tuple[CampusPlace, ...]).validate_json(
                (directory / "places.json").read_bytes()
            )
            if (directory / "places.json").exists()
            else ()
        )
        teachers = (
            TypeAdapter(tuple[CampusTeacher, ...]).validate_json(
                (directory / "teachers.json").read_bytes()
            )
            if (directory / "teachers.json").exists()
            else ()
        )
        return cls(services, offices, sources, places, teachers)

    def search_service(
        self, query: str, academic_year: str | None = None
    ) -> tuple[CampusService, ...]:
        normalized = query.strip().casefold()
        if not normalized:
            return ()
        # Return every match in stable ID order; never choose an ambiguous result silently.
        return tuple(
            service
            for _, service in sorted(self._services.items())
            if (academic_year is None or service.academic_year in {None, academic_year})
            and any(normalized in label.casefold() for label in (service.name, *service.aliases))
        )

    def find_office(self, office_id: str) -> CampusOffice | None:
        return self._offices.get(office_id)

    def services(self) -> tuple[CampusService, ...]:
        return tuple(self._services[key] for key in sorted(self._services))

    def find_service(self, service_id: str) -> CampusService | None:
        return self._services.get(service_id)

    def find_place(self, place_id: str) -> CampusPlace | None:
        return self._places.get(place_id)

    def find_teacher(self, teacher_id: str) -> CampusTeacher | None:
        return self._teachers.get(teacher_id)

    def search_place(self, query: str = "", category: str | None = None) -> tuple[CampusPlace, ...]:
        text = normalise_place_query(query)
        # A classroom code resolves its building/wing, never a fictitious room coordinate.
        block = re.search(r"e[12][abc](?=\d|\b)", text)
        if block:
            text = block.group()
        found = tuple(
            p
            for _, p in sorted(self._places.items())
            if (category is None or p.category == category)
            and (not text or any(text in normalise_place_query(x) for x in (p.name, *p.aliases)))
        )
        if found or block or not text:
            return found
        return tuple(
            p
            for p in self.match_places_in_question(query)
            if category is None or p.category == category
        )

    def match_places_in_question(self, query: str) -> tuple[CampusPlace, ...]:
        text = normalise_place_query(query)
        block = re.search(r"e[12][abc](?=\d|\b)", text)
        if block:
            return self.search_place(block.group())
        matches = [
            (
                max(
                    (
                        len(label)
                        for raw in (p.name, *p.aliases)
                        if (label := normalise_place_query(raw)) in text
                    ),
                    default=0,
                ),
                p,
            )
            for p in self._places.values()
        ]
        longest = max((score for score, _ in matches), default=0)
        return tuple(p for score, p in matches if score == longest and score > 1)

    def search_teacher(self, query: str = "") -> tuple[CampusTeacher, ...]:
        text = query.strip().casefold()
        return tuple(
            t
            for _, t in sorted(self._teachers.items())
            if not text or any(text in x.casefold() for x in (t.name, *t.aliases, t.department))
        )

    def service_places(self, service: CampusService) -> tuple[CampusPlace, ...]:
        ids = {pid for step in service.steps for pid in (step.place_ids or ())}
        return tuple(self._places[key] for key in sorted(ids))

    def evidence_for(self, records: tuple[DirectoryRecord, ...]) -> tuple[SourceEvidence, ...]:
        ids = {
            eid for record in records for link in record.field_evidence for eid in link.evidence_ids
        }
        return tuple(self._sources[eid] for eid in sorted(ids))


def normalise_place_query(query: str) -> str:
    return re.sub(r"[\s·（）()_-]+", "", unicodedata.normalize("NFKC", query).casefold())
