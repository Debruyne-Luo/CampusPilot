"""Route proxy and query status boundaries; upstream replies are synthetic."""

import json
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from campuspilot.dify import DifyClient
from campuspilot.directory.assist import AssistInput, assist
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.presentation import AnswerEnvelope, resolve_cards
from campuspilot.web import create_web_app
from fastapi.testclient import TestClient

DATA = Path(__file__).resolve().parents[1] / "data/cdut"
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}


@pytest.mark.parametrize("status", ["success", "needs_clarification", "empty"])
def test_chat_retains_business_status(status: str) -> None:
    answer = {"schema_version": 1, "status": status, "answer": "SYNTHETIC answer"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"answer": json.dumps(answer), "conversation_id": str(uuid4())}
        )

    dify = DifyClient(
        "synthetic-key", transport=httpx.MockTransport(handler), structured_answers=True
    )
    with TestClient(create_web_app(data_dir=DATA, dify=dify)) as client:
        client.post("/api/session", headers=HEADERS)
        response = client.post("/api/chat", headers=HEADERS, json={"message": "SYNTHETIC"})
        assert response.json()["result_status"] == status


def test_legacy_chat_does_not_claim_unique_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"answer": "SYNTHETIC text", "conversation_id": str(uuid4())}
        )

    with TestClient(
        create_web_app(
            data_dir=DATA, dify=DifyClient("synthetic-key", transport=httpx.MockTransport(handler))
        )
    ) as client:
        client.post("/api/session", headers=HEADERS)
        response = client.post("/api/chat", headers=HEADERS, json={"message": "SYNTHETIC"})
        assert response.json()["result_status"] is None


def test_route_proxy_bounds_and_no_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    original = httpx.AsyncClient
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.url.host == "restapi.amap.com"
        assert request.url.params["key"] == "synthetic-map-key"
        assert request.url.params["jscode"] == "synthetic-map-secret"
        return httpx.Response(200, text='Synthetic.callback({"status":"1"})')

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("campuspilot.web.httpx.AsyncClient", factory)
    with TestClient(
        create_web_app(
            data_dir=DATA, amap_key="synthetic-map-key", amap_security_code="synthetic-map-secret"
        )
    ) as client:
        params = {"origin": "1,1", "destination": "1.01,1.01", "callback": "Synthetic.callback"}
        response = client.get("/_AMapService/v3/direction/walking", params=params)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["content-type"].startswith("application/javascript")
        response = client.get(
            "/_AMapService/v3/assistant/coordinate/convert",
            params={"locations": "1,1", "coordsys": "gps"},
        )
        assert response.status_code == 200
        for invalid in [
            {"origin": "NaN,1"},
            {"origin": "181,1"},
            {"destination": "1,1;2,2"},
            {"callback": "alert(1)"},
            {"url": "https://example.com"},
        ]:
            assert (
                client.get(
                    "/_AMapService/v3/direction/walking", params={**params, **invalid}
                ).status_code
                == 422
            )
        assert client.get("/_AMapService/v3/direction/driving", params=params).status_code == 404
        assert len(calls) == 2


def test_geolocation_and_deployment_logging_contract() -> None:
    with TestClient(create_web_app(data_dir=DATA)) as client:
        assert client.get("/").headers["permissions-policy"] == "geolocation=(self)"
    root = DATA.parents[1]
    assert "--no-access-log" in (root / "deploy/campuspilot.service").read_text()
    assert "Access logs disabled" in (root / "deploy/Caddyfile.campuspilot").read_text()


def test_provider_place_proxy_is_bounded_and_uses_fixed_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = httpx.AsyncClient
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "restapi.amap.com"
        assert request.url.params["key"] == "synthetic-map-key"
        assert request.url.params["jscode"] == "synthetic-map-secret"
        paths.append(request.url.path)
        return httpx.Response(200, json={"status": "1", "pois": []})

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("campuspilot.web.httpx.AsyncClient", factory)
    params = {
        "location": "104.147531,30.675012",
        "radius": "2000",
        "offset": "10",
        "page": "1",
        "extensions": "base",
        "keywords": "SYNTHETIC PLACE",
        "type_": "",
        "children": "1",
        "antiCrab": "1",
        "key": "caller-key",
    }
    with TestClient(
        create_web_app(
            data_dir=DATA, amap_key="synthetic-map-key", amap_security_code="synthetic-map-secret"
        )
    ) as client:
        found = client.get("/_AMapService/v3/place/around", params=params)
        assert found.status_code == 200 and found.headers["cache-control"] == "no-store"
        assert (
            client.get("/_AMapService/v3/place/detail", params={"id": "SYNTHETICPOI"}).status_code
            == 200
        )
        for invalid in [
            {"location": "1,1"},
            {"location": "NaN,30.675012"},
            {"radius": "50000"},
            {"offset": "100"},
            {"keywords": ""},
            {"extensions": "all"},
            {"url": "https://example.com"},
            {"callback": "alert(1)"},
        ]:
            assert (
                client.get(
                    "/_AMapService/v3/place/around", params={**params, **invalid}
                ).status_code
                == 422
            )
        assert (
            client.get("/_AMapService/v3/place/detail", params={"id": "../private"}).status_code
            == 422
        )
        assert client.get("/_AMapService/v3/place/text", params=params).status_code == 404
        # A tapped base-map label: small radius around a point near campus.
        tap = {**params, "location": "104.154035,30.675967", "radius": "60", "keywords": "楼|馆"}
        assert client.get("/_AMapService/v3/place/around", params=tap).status_code == 200
        for invalid in [
            {"radius": "500"},
            {"keywords": ""},
            {"location": "104.20,30.675012"},
            {"location": "104.154035,30.75"},
        ]:
            assert (
                client.get("/_AMapService/v3/place/around", params={**tap, **invalid}).status_code
                == 422
            )
    assert paths == ["/v3/place/around", "/v3/place/detail", "/v3/place/around"]


def test_synthetic_teacher_and_service_associations(tmp_path: Path) -> None:
    # Modify only disposable fixtures, never the real directory snapshot.
    for source in DATA.glob("*.json"):
        shutil.copyfile(source, tmp_path / source.name)
    teachers = json.loads((tmp_path / "teachers.json").read_text(encoding="utf-8"))
    teacher = next(t for t in teachers if t["office"])
    teacher.update(
        name="SYNTHETIC Faculty",
        campus="成都校区",
        office="SYNTHETIC ROOM",
        place_id="cdut:place:east-library",
    )
    for link in teacher["field_evidence"]:
        if link["field_path"] == "campus":
            link["evidence_ids"] = teacher["field_evidence"][0]["evidence_ids"]
            link["note"] = "SYNTHETIC TEST ONLY"
    if not any(link["field_path"] == "campus" for link in teacher["field_evidence"]):
        teacher["field_evidence"].append(
            {
                "field_path": "campus",
                "evidence_ids": teacher["field_evidence"][0]["evidence_ids"],
                "note": "SYNTHETIC TEST ONLY",
            }
        )
    (tmp_path / "teachers.json").write_text(json.dumps([teacher]), encoding="utf-8")
    services = json.loads((tmp_path / "services.json").read_text(encoding="utf-8"))
    service = next(s for s in services if s["service_id"] == "cdut:service:campus-card-replacement")
    service["aliases"].append(service["name"])
    service["name"] = "SYNTHETIC service"
    for step in service["steps"]:
        step.pop("place_ids", None)
    service["steps"][0]["place_ids"] = ["cdut:place:east-library", "cdut:place:gongtong-dining"]
    (tmp_path / "services.json").write_text(json.dumps(services), encoding="utf-8")
    repo = DirectoryRepository.load(tmp_path)
    teacher_result = assist(repo, AssistInput(kind="teacher", query="SYNTHETIC Faculty"), "test")
    assert teacher_result.status == "success"
    assert [p.place_id for p in teacher_result.places] == ["cdut:place:east-library"]
    service_result = assist(
        repo, AssistInput(kind="service", service_key="campus_card_replacement"), "test"
    )
    assert len(service_result.places) == 2
    envelope = AnswerEnvelope(
        schema_version=1,
        status="success",
        answer="SYNTHETIC",
        teacher_ids=(teacher["teacher_id"],),
        place_ids=("cdut:place:east-library",),
    )
    cards = resolve_cards(repo, envelope)
    assert len(cards["places"]) == 1  # type: ignore[arg-type]
