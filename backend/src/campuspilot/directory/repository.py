"""Load only explicit local files; validate the whole snapshot before exposing records."""

from pathlib import Path
from typing import Self

from pydantic import TypeAdapter

from campuspilot.domain import CampusOffice, CampusService, DirectoryRecord
from campuspilot.evidence import SourceEvidence


class DirectoryRepository:
    def __init__(
        self,
        services: tuple[CampusService, ...],
        offices: tuple[CampusOffice, ...],
        sources: tuple[SourceEvidence, ...],
    ) -> None:
        # Revalidate model instances too: model_copy/model_construct can skip validators.
        services = tuple(CampusService.model_validate(x.model_dump()) for x in services)
        offices = tuple(CampusOffice.model_validate(x.model_dump()) for x in offices)
        sources = tuple(SourceEvidence.model_validate(x.model_dump()) for x in sources)
        self._services = {x.service_id: x for x in services}
        self._offices = {x.office_id: x for x in offices}
        self._sources = {x.evidence_id: x for x in sources}
        if (len(self._services), len(self._offices), len(self._sources)) != (
            len(services),
            len(offices),
            len(sources),
        ):
            raise ValueError("Duplicate service, office or evidence identifier")
        if set(self._services) & set(self._offices):
            raise ValueError("Service and office identifiers must be distinct")
        for source in sources:
            host = source.source_url.host or ""
            if host != "cdut.edu.cn" and not host.endswith(".cdut.edu.cn"):
                raise ValueError("CDUT directory requires official CDUT sources")
            if not source.evidence_id.startswith("cdut:") or not source.source_id.startswith(
                "cdut:"
            ):
                raise ValueError("CDUT evidence must use the cdut namespace")
        for record in (*services, *offices):
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
        return cls(services, offices, sources)

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

    def evidence_for(self, records: tuple[DirectoryRecord, ...]) -> tuple[SourceEvidence, ...]:
        ids = {
            eid for record in records for link in record.field_evidence for eid in link.evidence_ids
        }
        return tuple(self._sources[eid] for eid in sorted(ids))
