"""Offline contract/lookup regressions against the reviewed public-source inventory.

Malformed cases mutate copies of real records, never the checked-in source files.
Synthetic data remains in campuspilot.mocks and never loads into the real repository.
"""

import json
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from campuspilot.__main__ import query_directory
from campuspilot.contracts import (
    ExecutionContext,
    Payload,
    RunResult,
    ServiceSearchResult,
    ToolCall,
    ToolResult,
)
from campuspilot.demo import build_demo, run_demo
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.directory.tools import directory_tools
from campuspilot.domain import CampusOffice, CampusService
from campuspilot.evidence import FieldEvidence, SourceEvidence
from campuspilot.mocks import demo_tools
from campuspilot.state import InMemoryExecutionJournal
from campuspilot.tools import ReadOnlyPermissionPolicy, ToolExecutor
from pydantic import HttpUrl, JsonValue, TypeAdapter, ValidationError

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"


def services() -> tuple[CampusService, ...]:
    return TypeAdapter(tuple[CampusService, ...]).validate_json(
        (DATA / "services.json").read_bytes()
    )


def offices() -> tuple[CampusOffice, ...]:
    return TypeAdapter(tuple[CampusOffice, ...]).validate_json((DATA / "offices.json").read_bytes())


def sources() -> tuple[SourceEvidence, ...]:
    return TypeAdapter(tuple[SourceEvidence, ...]).validate_json(
        (DATA / "sources.json").read_bytes()
    )


def repository() -> DirectoryRepository:
    return DirectoryRepository.load(DATA)


def test_seed_sources_remain_unreviewed() -> None:
    assert len(services()) == 3 and len(offices()) == 3
    assert all(
        not row.synthetic and row.verification_status == "needs_review" for row in services()
    )
    for source in sources():
        assert source.source_authority == "official_department"
        assert source.verification_status == "needs_review"
        assert source.reviewer is None and source.verified_at is None
        assert source.source_updated_at is None  # Retrieval is not a source update.
    proof = repository().search_service("研究生在读证明")[0]
    evidence = repository().evidence_for((proof,))
    canonical = next(item for item in evidence if "graduate-proof" in item.evidence_id)
    assert str(canonical.source_url) == "https://gra.cdut.edu.cn/info/1007/5283.htm"
    limits = next(link for link in proof.field_evidence if link.field_path == "limits")
    assert limits.evidence_ids == ("cdut:evidence:graduate-proof-2023",)


def test_lookup_and_unknown_fields() -> None:
    repo = repository()
    proof = repo.search_service(" 在读证明 ")[0]
    assert proof.required_materials is None
    assert proof.office_id is not None
    office = repo.find_office(proof.office_id)
    assert office is not None
    assert office.location is None and office.office_hours is None
    assert office.contacts is not None and office.contacts[0].value == "84078860"
    assert repo.search_service("不存在的服务") == ()
    assert repo.search_service("   ") == ()
    assert repo.find_office("不存在的部门") is None


def test_academic_year_and_payment_scope() -> None:
    repo = repository()
    assert repo.search_service("缴费票据", "2025-2026") == ()
    assert repo.search_service("缴费票据", "2027-2028") == ()
    receipt = repo.search_service("缴费票据", "2026-2027")[0]
    assert receipt.academic_year == "2026-2027"
    assert receipt.availability is not None and len(receipt.availability) == 2
    day_rule = next(rule for rule in receipt.availability if "24" in rule.wait)
    assert day_rule.condition == "微信或网页缴费成功；仅限2026-2027学年"
    assert "支付宝" not in day_rule.condition
    assert any("支付宝" in note and "未知" in note for note in receipt.notes)


def test_ambiguous_lookup_returns_all_in_stable_order() -> None:
    original = repository().search_service("在读证明")[0]
    # Collision test derived from a real record; this copy is never a published campus fact.
    duplicate = original.model_copy(update={"service_id": "cdut:service:collision-test"})
    repo = DirectoryRepository((*services(), duplicate), offices(), sources())
    result = repo.search_service("在读证明")
    assert len(result) == 2
    assert [row.service_id for row in result] == sorted(row.service_id for row in result)


@pytest.mark.parametrize("kind", ["service", "office", "evidence"])
def test_duplicate_ids_rejected(kind: str) -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        DirectoryRepository(
            services() + (services()[:1] if kind == "service" else ()),
            offices() + (offices()[:1] if kind == "office" else ()),
            sources() + (sources()[:1] if kind == "evidence" else ()),
        )


@pytest.mark.parametrize("mutation", ["missing", "typo", "empty", "duplicate"])
def test_invalid_field_provenance_rejected(mutation: str) -> None:
    data = services()[0].model_dump()
    links = list(services()[0].field_evidence)
    target = next(link for link in links if link.field_path == "name")
    links.remove(target)
    if mutation == "typo":
        links.append(target.model_copy(update={"field_path": "naem"}))
    elif mutation == "empty":
        links.append(target.model_copy(update={"evidence_ids": ()}))
    elif mutation == "duplicate":
        links.extend((target, target))
    data["field_evidence"] = tuple(link.model_dump() for link in links)
    with pytest.raises(ValidationError):
        CampusService.model_validate(data)


def test_unresolved_evidence_and_office_rejected() -> None:
    with pytest.raises(ValueError, match="Unresolved field"):
        DirectoryRepository(services(), offices(), ())
    with pytest.raises(ValueError, match="Unresolved office"):
        DirectoryRepository(services(), (), sources())


def test_no_inferred_office_fields_and_no_fake_verification() -> None:
    office = offices()[0].model_dump()
    office["location"] = "unsupported location"
    with pytest.raises(ValidationError, match="Missing field evidence"):
        CampusOffice.model_validate(office)
    raw = sources()[0].model_dump()
    raw["verification_status"] = "verified"
    with pytest.raises(ValidationError, match="reviewer"):
        SourceEvidence.model_validate(raw)
    raw = services()[0].model_dump()
    raw["verification_status"] = "verified"
    with pytest.raises(ValidationError):
        CampusService.model_validate(raw)


@pytest.mark.parametrize("url", ["https://example.org/", "https://cdut.edu.cn.example.org/"])
def test_nonofficial_sources_rejected(url: str) -> None:
    source = sources()[0].model_copy(update={"source_url": HttpUrl(url)})
    with pytest.raises(ValueError, match="official CDUT"):
        DirectoryRepository(services(), offices(), (source, *sources()[1:]))


def test_schema_rejects_extra_fields_wrong_types_and_synthetic_records() -> None:
    for update in ({"synthetic": True}, {"name": 123}, {"secret": "not-a-real-secret"}):
        raw = services()[0].model_dump()
        raw.update(update)
        with pytest.raises(ValidationError):
            CampusService.model_validate(raw)
    with pytest.raises(ValidationError):
        SourceEvidence.model_validate(demo_tools()[0].execute({"query": "synthetic service"}))


def test_dangling_result_evidence_rejected() -> None:
    service = repository().search_service("在读证明")[0]
    with pytest.raises(ValidationError, match="resolve"):
        ServiceSearchResult(matches=(service,), evidence=(sources()[0],))


def test_card_guide_version_and_human_source_confirmation() -> None:
    card = repository().search_service("一卡通挂失")[0]
    evidence = repository().evidence_for((card,))[0]
    assert evidence.version == "第四版；封面2024年8月"
    assert evidence.access_method == "user_provided_file"
    assert (
        evidence.source_file_sha256
        == "825729937cfd2791c768c2682d1bc1ac41b57a4a6ded57033b0de63f419239b9"
    )
    assert evidence.verification_status == "needs_review"
    assert evidence.source_published_at is None


def test_separate_assemblies_and_no_fallback() -> None:
    journal = InMemoryExecutionJournal()
    real = directory_tools(repository())
    executor = ToolExecutor(real, ReadOnlyPermissionPolicy(), journal)
    demo, _, demo_journal = build_demo()
    assert executor is not demo.executor and journal is not demo_journal
    assert executor.tool_ids == {"search_service", "find_office"}
    assert demo.executor.tool_ids == {"search_service", "find_office", "route_plan"}
    call = ToolCall(call_id="c", tool_id="search_service", arguments={"query": "在读证明"})
    context = ExecutionContext(
        session_id="s", task_id="t", run_id="r", allowed_tools=executor.tool_ids
    )
    result = executor.execute(call, context)
    assert result.data is not None and not result.data.synthetic
    assert query_directory(DATA, "search_service", "synthetic service").result.status == "empty"
    assert query_directory(DATA, "find_office", "synthetic:office").result.status == "empty"
    assert demo_tools()[0].execute({"query": "在读证明"}) is None
    route = ToolCall(call_id="route", tool_id="route_plan", arguments={})
    assert executor.execute(route, context).error_code == "unknown_tool"


def test_denied_and_invalid_directory_requests_never_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def must_not_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("Denied/invalid requests must not enter the repository")

    monkeypatch.setattr(DirectoryRepository, "search_service", must_not_run)
    executor = ToolExecutor(
        directory_tools(repository()), ReadOnlyPermissionPolicy(), InMemoryExecutionJournal()
    )
    context = ExecutionContext(session_id="s", task_id="t", run_id="r", allowed_tools=frozenset())
    denied = ToolCall(call_id="c", tool_id="search_service", arguments={"query": "在读证明"})
    assert executor.execute(denied, context).status == "denied"
    for arguments in ({"query": " "}, {"query": "在读证明", "data_origin": "synthetic"}):
        invalid = ToolCall.model_validate(
            {"call_id": "c", "tool_id": "search_service", "arguments": arguments}
        )
        assert executor.execute(invalid, context).status == "invalid"


def test_source_tools_offline_trace_and_fake_harness_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Directory queries must not use the network")

    monkeypatch.setattr(socket, "socket", no_network)
    result = query_directory(DATA, "search_service", "在读证明")
    assert result == query_directory(DATA, "search_service", "在读证明")
    assert result.result.status == "success" and result.result.data is not None
    assert result.trace[-1].evidence_ids == tuple(
        e.evidence_id for e in result.result.data.evidence
    )
    assert [event.kind for event in result.trace] == ["tool_requested", "permission", "tool_result"]
    assert "在读证明" not in str(result.trace)
    raw = run_demo().result.model_dump()
    raw["results"] = (result.result.model_dump(),)
    with pytest.raises(ValidationError, match="fake harness"):
        RunResult.model_validate(raw)


def test_cli_from_other_directory_and_missing_data(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "campuspilot",
            "search-service",
            "缴费票据",
            "--data-dir",
            str(DATA),
            "--academic-year",
            "2026-2027",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert json.loads(proc.stdout)["result"]["data"]["matches"][0]["academic_year"] == "2026-2027"
    missing = subprocess.run(
        [sys.executable, "-m", "campuspilot", "search-service", "在读证明"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert missing.returncode == 2 and not missing.stdout
    assert "no synthetic fallback" in missing.stderr


def test_corrupt_file_is_not_silently_ignored(tmp_path: Path) -> None:
    (tmp_path / "services.json").write_text("not JSON", encoding="utf-8")
    with pytest.raises(ValidationError):
        DirectoryRepository.load(tmp_path)


def test_record_is_immutable() -> None:
    service = services()[0]
    with pytest.raises(ValidationError):
        service.name = "cannot mutate"
    assert repository().search_service(service.name)[0] == service


def test_field_evidence_duplicate_ids_rejected() -> None:
    with pytest.raises(ValidationError):
        FieldEvidence(field_path="name", evidence_ids=("same", "same"), note="test")


def test_real_office_tool_preserves_unknown_location_and_evidence() -> None:
    output = query_directory(DATA, "find_office", "cdut:office:graduate-school")
    assert output.result.status == "success"
    data = output.result.data
    assert data is not None and data.kind == "directory_office"
    assert data.office.location is None and data.office.contacts is not None
    assert data.office.contacts[0].value == "84078860"
    assert output.trace[-1].evidence_ids == ("cdut:evidence:graduate-proof-2023",)


def test_synthetic_evidence_cannot_enter_real_payload() -> None:
    output = query_directory(DATA, "search_service", "在读证明").result
    fixture = demo_tools()[0].execute({"query": "synthetic service"})
    assert fixture is not None
    assert output.data is not None
    raw = output.data.model_dump()
    raw["evidence"] = fixture.model_dump()["evidence"]
    with pytest.raises(ValidationError):
        ServiceSearchResult.model_validate(raw)


def test_core_and_demo_import_without_directory_implementation() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import campuspilot.contracts; import campuspilot.demo; "
            "assert not any(name == 'campuspilot.directory' or "
            "name.startswith('campuspilot.directory.') for name in sys.modules)",
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.parametrize("registered_real", [True, False])
def test_executor_rejects_wrong_payload_family(
    monkeypatch: pytest.MonkeyPatch, registered_real: bool
) -> None:
    real = directory_tools(repository())[0]
    mock = demo_tools()[0]
    real_payload = real.execute({"query": "在读证明"})
    mock_payload = mock.execute({"query": "synthetic service"})

    def wrong(arguments: dict[str, JsonValue]) -> Payload | None:
        return mock_payload if registered_real else real_payload

    if registered_real:
        monkeypatch.setattr(real, "execute", wrong)
    else:
        mock = replace(mock, handler=wrong)
    executor = ToolExecutor(
        (real if registered_real else mock,),
        ReadOnlyPermissionPolicy(),
        InMemoryExecutionJournal(),
    )
    context = ExecutionContext(
        session_id="s", task_id="t", run_id="r", allowed_tools=executor.tool_ids
    )
    call = ToolCall(call_id="c", tool_id="search_service", arguments={"query": "test"})
    assert executor.execute(call, context).error_code == "invalid_output"


@pytest.mark.parametrize(
    "command,query",
    [
        ("search-service", "校园卡挂失"),
        ("search-service", "在读证明"),
        ("search-service", "缴费票据"),
        ("find-office", "cdut:office:graduate-school"),
    ],
)
def test_real_cli_exposes_needs_review(command: str, query: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "campuspilot", command, query, "--data-dir", str(DATA)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    output = json.loads(proc.stdout)
    data = output["result"]["data"]
    assert data["synthetic"] is False
    assert "need human review" in output["notice"]
    assert "needs human review" in data["notice"]
    records = data["matches"] if command == "search-service" else [data["office"]]
    assert all(record["verification_status"] == "needs_review" for record in records)
    assert all(source["verification_status"] == "needs_review" for source in data["evidence"])
    # Moving the public models must preserve the full typed JSON contract.
    result = ToolResult.model_validate_json(json.dumps(output["result"]))
    assert result.model_dump(mode="json") == output["result"]
