"""Regression for conflicting intent fields observed in the public card query."""

import json
import runpy
from pathlib import Path
from typing import Any

import pytest
from campuspilot.directory.assist import AssistInput, assist
from campuspilot.directory.repository import DirectoryRepository

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/cdut"


def build_request(data: dict[str, Any]) -> dict[str, Any]:
    node = runpy.run_path(str(ROOT / "integrations/dify/build_request.py"))
    body: dict[str, Any] = json.loads(node["main"](json.dumps(data))["body"])
    return body


@pytest.mark.parametrize(
    "service_key,service_id",
    [
        ("campus_card_replacement", "cdut:service:campus-card-replacement"),
        ("campus_card_loss", "cdut:service:campus-card-loss"),
    ],
)
def test_recognized_card_service_with_unknown_kind_reaches_real_directory(
    service_key: str, service_id: str
) -> None:
    # Reproduced extractor shape; the phrase itself is not a requirement for the fix.
    body = build_request({"kind": "unknown", "service_key": service_key})
    result = assist(DirectoryRepository.load(DATA), AssistInput.model_validate(body), "synthetic")
    assert body["kind"] == "service" and result.status == "success"
    assert [record.service_id for record in result.services] == [service_id]
    expected = {"cdut:place:gongtong-dining", "cdut:place:camphor-dining"}
    if service_key == "campus_card_replacement":
        expected.update({"cdut:place:finance", "cdut:place:ginkgo-dining"})
    assert {place.place_id for place in result.places} == expected


@pytest.mark.parametrize(
    "data",
    [
        {"kind": "unknown", "service_key": "unknown"},
        {"kind": "unknown", "service_key": "invented_service"},
        {"kind": "unknown", "service_key": "campus_card_replacement", "place_ids": ["fake"]},
        {"kind": "unknown", "service_key": "campus_card_replacement", "url": "https://example.com"},
        {"kind": "unknown", "service_key": "campus_card_replacement", "academic_year": "now"},
    ],
)
def test_unknown_or_invalid_parameters_do_not_gain_a_service(data: dict[str, Any]) -> None:
    body = build_request(data)
    result = assist(DirectoryRepository.load(DATA), AssistInput.model_validate(body), "synthetic")
    assert result.status == "needs_clarification" and not result.services and not result.places


def test_explicit_teacher_kind_is_preserved() -> None:
    body = build_request(
        {"kind": "teacher", "query": "王洪辉", "service_key": "campus_card_replacement"}
    )
    result = assist(DirectoryRepository.load(DATA), AssistInput.model_validate(body), "synthetic")
    assert body["kind"] == "teacher" and result.status == "success"
    assert not result.services
    assert [p.place_id for p in result.places] == ["cdut:place:network-security"]
    assert [teacher.teacher_id for teacher in result.teachers] == ["cdut:teacher:wang-honghui"]
