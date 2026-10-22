"""SYNTHETIC service fixtures exercise completeness, not actual university procedures."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.directory.tools import SearchServiceTool
from campuspilot.domain import CampusService
from campuspilot.evidence import SourceEvidence
from campuspilot.presentation import service_card
from campuspilot.tools.checklist import ChecklistQuery, ChecklistTool
from campuspilot.tools.directory import DirectoryTool
from pydantic import ValidationError

from scripts.promote_services import build, write_directory


def fixture(level: str | None = "guide", *, steps: bool = False) -> dict[str, Any]:
    fields = ("name", "aliases", "department", "audience", "entry_points", "modes")
    value: dict[str, Any] = {
        "service_id": "cdut:service:synthetic-completeness", "name": "SYNTHETIC 测试事项",
        "aliases": (), "department": "SYNTHETIC 测试部门", "office_id": None,
        "audience": "SYNTHETIC 学生", "entry_points": ("SYNTHETIC 入口",),
        "modes": ("online",), "notes": ("SYNTHETIC: not university information",),
        "field_evidence": tuple({"field_path": name, "evidence_ids": ("cdut:evidence:synthetic",),
                                 "note": "SYNTHETIC fixture"} for name in fields),
    }
    if level is not None:
        value["information_level"] = level
    if steps:
        value["steps"] = ({"mode": "online", "instruction": "SYNTHETIC published step"},)
        value["field_evidence"] += ({"field_path": "steps.0", "evidence_ids": (
            "cdut:evidence:synthetic",), "note": "SYNTHETIC step evidence"},)
    return value


def repository(record: dict[str, Any]) -> DirectoryRepository:
    source = SourceEvidence.model_validate_json(json.dumps({
        "evidence_id": "cdut:evidence:synthetic", "source_id": "cdut:source:synthetic",
        "source_reference": "SYNTHETIC test source", "source_url": "https://www.cdut.edu.cn/SYNTHETIC-test",
        "publisher": "SYNTHETIC fixture", "source_authority": "official_university",
        "version": "SYNTHETIC-v1", "locator": "SYNTHETIC paragraph",
        "applicability": "SYNTHETIC only", "retrieved_at": "2026-10-17", "access_method": "direct",
    }))
    return DirectoryRepository((CampusService.model_validate(record),), (), (source,))


@pytest.mark.parametrize("level", ["directory", "guide"])
def test_catalogue_and_guide_do_not_need_procedure_or_known_channel(level: str) -> None:
    raw = fixture(level)
    raw["modes"] = ()
    service = CampusService.model_validate(raw)
    assert service.steps == () and service.modes == () and service.procedure_note


def test_procedure_requires_steps_and_each_step_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="requires source-backed"):
        CampusService.model_validate(fixture("procedure"))
    raw = fixture("procedure", steps=True)
    raw["field_evidence"] = tuple(f for f in raw["field_evidence"] if f["field_path"] != "steps.0")
    with pytest.raises(ValidationError, match="Missing field evidence"):
        CampusService.model_validate(raw)
    raw = fixture("procedure", steps=True)
    raw["modes"] = ("in_person",)
    with pytest.raises(ValidationError, match="published service mode"):
        CampusService.model_validate(raw)


def test_legacy_read_roundtrip_preserves_data_without_certifying_a_procedure() -> None:
    raw = fixture(None, steps=True)
    service = CampusService.model_validate(raw)
    assert service.information_level == "guide" and service.steps
    assert CampusService.model_validate_json(service.model_dump_json()) == service
    repo = repository(raw)
    card = service_card(repo, service)
    assert card["steps"] == [] and card["procedure_note"]
    tool = DirectoryTool(SearchServiceTool(repo))
    result = tool.run(tool.params_model(query="SYNTHETIC"))
    matches = result["matches"]
    assert isinstance(matches, list) and isinstance(matches[0], dict)
    assert matches[0]["steps"] == []


@pytest.mark.parametrize("level", ["directory", "guide", "procedure"])
def test_only_a_procedure_exposes_step_checklist(level: str) -> None:
    repo = repository(fixture(level, steps=True))
    service = repo.services()[0]
    result = ChecklistTool(repo).run(ChecklistQuery(service_id=service.service_id))
    assert result["checklist_available"] is (level == "procedure")
    items = result["items"]
    assert isinstance(items, list)
    assert len(items) == (1 if level == "procedure" else 0)
    if level == "procedure":
        assert isinstance(items[0], dict)
        assert items[0]["evidence_ids"] == ["cdut:evidence:synthetic"]


def test_capture_gate_never_fabricates_steps_even_with_legacy_flag() -> None:
    record = {"service_id": "synthetic12345678", "code": "synthetic",
              "name": "SYNTHETIC 事项", "department": "SYNTHETIC 部门",
              "service_object_text": "SYNTHETIC 学生", "handling_entry_text": "线上",
              "enquiry_phone": "SYNTHETIC no real number"}
    for legacy_flag in (False, True):
        service = CampusService.model_validate(build(record, allow_navigation_step=legacy_flag))
        assert service.information_level == "guide" and service.steps == ()
        assert service.contacts and service.contacts[0].value == record["enquiry_phone"]


def test_candidate_is_isolated_scope_filtered_and_loadable(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    repo = repository(fixture(None, steps=True))
    sections = (("services", repo.services()), ("offices", ()),
                ("sources", repo.evidence_for(repo.services())))
    for name, records in sections:
        (base / (name + ".json")).write_text(
            json.dumps([r.model_dump(mode="json") for r in records])
        )
    baseline = (base / "services.json").read_bytes()
    captured = {"service_id": "synthetic12345678", "code": "synthetic-new",
                "name": "SYNTHETIC 新事项", "department": "SYNTHETIC 部门",
                "service_object_text": "SYNTHETIC 学生", "handling_entry_text": "线上",
                "source_url": "https://www.cdut.edu.cn/SYNTHETIC-capture",
                "audiences": ["graduate"]}
    staff = {**captured, "code": "synthetic-staff", "audiences": ["staff"]}
    rows = [captured, staff]
    admitted = [CampusService.model_validate(build(r)).model_dump(mode="json") for r in rows]
    candidate = tmp_path / "candidate"
    report = write_directory(candidate, admitted, rows, base, json.dumps(rows).encode(), None)
    assert report["in_scope_new"] == 1 and report["out_of_scope"] == 1
    assert len(DirectoryRepository.load(candidate).services()) == 2
    assert (base / "services.json").read_bytes() == baseline
    source = json.loads((candidate / "sources.json").read_bytes())[-1]
    capture = candidate / "raw/bsdt/bsdt-synthetic-new.json"
    assert source["source_file_sha256"] == hashlib.sha256(capture.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="must not replace"):
        write_directory(base, admitted, rows, base, b"[]", None)
