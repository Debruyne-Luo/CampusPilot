"""Business-scope checks for the Dify-facing lookup; no model retrieval evaluation."""

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from campuspilot.api import create_app  # noqa: E402
from campuspilot.directory.tools import FindOfficeTool  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import JsonValue  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"
TOKEN = "synthetic-lookup-token-not-for-deployment"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
LOOKUP = "/v1/directory/lookup"


@pytest.mark.parametrize(
    "body,status",
    [
        ({"service_key": "unknown"}, "needs_clarification"),
        ({"service_key": "enrollment_proof"}, "needs_clarification"),
        ({"service_key": "enrollment_proof", "audience": "undergraduate"}, "out_of_scope"),
        ({"service_key": "tuition_receipt"}, "needs_clarification"),
        ({"service_key": "tuition_receipt", "academic_year": "2025-2026"}, "out_of_scope"),
    ],
)
def test_missing_or_inapplicable_conditions_do_not_release_procedure(
    body: dict[str, str], status: str
) -> None:
    with TestClient(create_app(data_dir=DATA, api_token=TOKEN)) as client:
        response = client.post(LOOKUP, json=body, headers=AUTH)
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == status
        assert payload["service"] is None and payload["office"] is None
        assert payload["trace"] == []


@pytest.mark.parametrize(
    "body",
    [
        {"service_key": "campus_card_loss"},
        {"service_key": "enrollment_proof", "audience": "graduate"},
        {"service_key": "tuition_receipt", "academic_year": "2026-2027"},
    ],
)
def test_service_and_office_are_resolved_through_real_tool_boundary(body: dict[str, str]) -> None:
    with TestClient(create_app(data_dir=DATA, api_token=TOKEN)) as client:
        response = client.post(LOOKUP, json=body, headers=AUTH)
        payload = response.json()
        assert response.status_code == 200 and payload["status"] == "success"
        assert payload["service"]["office_id"] == payload["office"]["office_id"]
        assert payload["office"]["location"] is None
        assert payload["service"]["verification_status"] == "needs_review"
        assert payload["evidence"] and len(payload["trace"]) == 6
        assert {event["tool_id"] for event in payload["trace"]} == {"search_service", "find_office"}


def test_office_failure_is_not_relabelled_as_empty_or_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(self: FindOfficeTool, arguments: dict[str, JsonValue]) -> None:
        raise RuntimeError("private synthetic failure")

    monkeypatch.setattr(FindOfficeTool, "execute", fail)
    with TestClient(create_app(data_dir=DATA, api_token=TOKEN)) as client:
        response = client.post(LOOKUP, json={"service_key": "campus_card_loss"}, headers=AUTH)
        assert response.status_code == 503 and response.json()["status"] == "unavailable"
        assert "private synthetic" not in response.text
        assert response.json()["service"] is None


def test_lookup_rejects_authority_and_foreign_office_ids() -> None:
    with TestClient(create_app(data_dir=DATA, api_token=TOKEN)) as client:
        assert client.post(LOOKUP, json={"service_key": "campus_card_loss"}).status_code == 401
        for extra in ("office_id", "allowed_tools", "data_dir", "url"):
            response = client.post(
                LOOKUP,
                json={"service_key": "campus_card_loss", extra: "private-value"},
                headers=AUTH,
            )
            assert response.status_code == 422 and "private-value" not in response.text


def test_gateway_hides_docs_bounds_bodies_and_limits_traffic() -> None:
    with TestClient(create_app(data_dir=DATA, api_token=TOKEN, tool_gateway=True)) as client:
        for path in ("/docs", "/redoc", "/openapi.json", "/", "/api/chat"):
            assert client.get(path).status_code == 404
        assert client.post(LOOKUP, content=b"x" * 16385, headers=AUTH).status_code == 413
        assert (
            client.post(LOOKUP, json={"service_key": "campus_card_loss"}, headers=AUTH).status_code
            == 200
        )
        assert client.get("/healthz").status_code == 200
        responses = [
            client.post(LOOKUP, json={"service_key": "campus_card_loss"}, headers=AUTH)
            for _ in range(91)
        ]
        assert responses[-1].status_code == 429
        assert responses[-1].json()["error_code"] == "rate_limited"
