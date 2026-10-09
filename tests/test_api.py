"""HTTP-specific boundary checks; existing directory tests own retrieval semantics."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from campuspilot.api import create_app  # noqa: E402
from campuspilot.directory.tools import SearchServiceTool  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import JsonValue  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"
TOKEN = "synthetic-test-credential-not-for-deployment"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SEARCH = "/v1/directory/services/search"


def client() -> TestClient:
    return TestClient(create_app(data_dir=DATA, api_token=TOKEN))


def test_real_query_evidence_and_unknown_office_location() -> None:
    api = client()
    response = api.post(SEARCH, json={"query": "研究生在读证明"}, headers=AUTH)
    assert response.status_code == 200
    payload = response.json()
    assert response.headers["X-Request-ID"] == payload["request_id"]
    result = payload["result"]
    assert result["status"] == "success" and result["data"]["synthetic"] is False
    record = result["data"]["matches"][0]
    assert record["verification_status"] == "needs_review"
    assert record["field_evidence"] and result["data"]["evidence"]
    office = api.get(f"/v1/directory/offices/{record['office_id']}", headers=AUTH).json()
    assert office["result"]["data"]["office"]["location"] is None
    assert office["request_id"] != payload["request_id"]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_authentication_fails_before_execution(headers: dict[str, str]) -> None:
    response = client().post(SEARCH, json={"query": "校园卡"}, headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert "trace" not in response.json() and "matches" not in response.text


@pytest.mark.parametrize(
    "body",
    [
        {"query": "校园卡", "allowed_tools": ["route_plan"]},
        {"query": "校园卡", "data_dir": "private-file"},
        {"query": 123},
        {"query": " "},
        {"query": "票据", "academic_year": "invalid-secret-value"},
    ],
)
def test_invalid_inputs_do_not_reflect_payload(body: dict[str, JsonValue]) -> None:
    response = client().post(SEARCH, json=body, headers=AUTH)
    assert response.status_code == 422
    assert response.json()["error_code"] == "invalid_input"
    assert "trace" not in response.json()
    assert "private-file" not in response.text and "invalid-secret-value" not in response.text


def test_empty_is_distinct_from_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    api = client()
    empty = api.post(SEARCH, json={"query": "not-in-inventory"}, headers=AUTH)
    assert empty.status_code == 200 and empty.json()["result"]["status"] == "empty"

    def unavailable(self: SearchServiceTool, arguments: dict[str, JsonValue]) -> None:
        raise RuntimeError("private provider error and secret")

    monkeypatch.setattr(SearchServiceTool, "execute", unavailable)
    failed = api.post(SEARCH, json={"query": "校园卡"}, headers=AUTH)
    assert failed.status_code == 503 and failed.json()["result"]["status"] == "failed"
    assert "private provider" not in failed.text and TOKEN not in failed.text


def test_requests_have_isolated_context_and_journals() -> None:
    api = client()

    def query(number: int) -> dict[str, JsonValue]:
        response = api.post(SEARCH, json={"query": f"synthetic-absent-{number}"}, headers=AUTH)
        result: dict[str, JsonValue] = response.json()
        return result

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(query, range(8)))
    assert len({str(result["request_id"]) for result in results}) == 8
    for result in results:
        trace = result["trace"]
        assert isinstance(trace, list) and len(trace) == 3
        for event in trace:
            assert isinstance(event, dict)
            assert event["session_id"] == f"http-session:{result['request_id']}"


def test_config_failure_and_only_declared_operations(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        create_app(data_dir=DATA, api_token="")
    with pytest.raises(OSError):
        create_app(data_dir=tmp_path, api_token=TOKEN)
    api = client()
    assert api.get("/healthz").json() == {"status": "ready"}
    assert api.post("/v1/route_plan", headers=AUTH).status_code == 404
    assert (
        api.post(SEARCH + "?allowed_tools=write", json={"query": "卡"}, headers=AUTH).status_code
        == 422
    )
    schema = api.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        SEARCH,
        "/v1/directory/offices/{office_id}",
        "/v1/directory/lookup",
        "/v1/directory/places/search",
        "/v1/directory/teachers/search",
        "/v1/directory/assist",
    }
    assert schema["paths"][SEARCH]["post"]["security"] == [{"HTTPBearer": []}]
    assert TOKEN not in str(schema) and "RouteResult" not in schema["components"]["schemas"]
