"""New submission contracts and failure paths; upstream/provider replies are synthetic."""

import ast
import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
import yaml
from campuspilot.api import create_app
from campuspilot.dify import DifyClient
from campuspilot.directory.assist import AssistInput, assist
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.domain import CampusOffice, CampusPlace, CampusService, CampusTeacher, MapPosition
from campuspilot.evidence import SourceEvidence
from campuspilot.presentation import AnswerEnvelope, place_card, resolve_cards
from campuspilot.web import create_web_app
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/cdut"
TOKEN = "synthetic-tool-token-not-for-deployment"
KEY = "synthetic-dify-key-not-for-deployment"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}


def load_records() -> tuple[
    tuple[CampusService, ...],
    tuple[CampusOffice, ...],
    tuple[SourceEvidence, ...],
    tuple[CampusPlace, ...],
    tuple[CampusTeacher, ...],
]:
    return (
        TypeAdapter(tuple[CampusService, ...]).validate_json((DATA / "services.json").read_bytes()),
        TypeAdapter(tuple[CampusOffice, ...]).validate_json((DATA / "offices.json").read_bytes()),
        TypeAdapter(tuple[SourceEvidence, ...]).validate_json((DATA / "sources.json").read_bytes()),
        TypeAdapter(tuple[CampusPlace, ...]).validate_json((DATA / "places.json").read_bytes()),
        TypeAdapter(tuple[CampusTeacher, ...]).validate_json((DATA / "teachers.json").read_bytes()),
    )


def workflow_node(name: str) -> Any:
    scope: dict[str, Any] = {}
    code = (ROOT / "integrations/dify" / name).read_text(encoding="utf-8")
    exec(compile(code, name, "exec"), scope)
    return scope["main"]


def test_public_candidates_unknowns_and_authenticated_shared_queries() -> None:
    repo = DirectoryRepository.load(DATA)
    places = repo.search_place("")
    assert len(places) == 41
    positions = [p.position for p in places if p.position is not None]
    assert len(positions) == 41
    # 2026-10-11: nine provider points confirmed on site by the user; the rest stay candidates.
    confirmed = {
        p.place_id for p in places if p.position and p.position.verification_status == "confirmed"
    }
    assert confirmed == {
        "cdut:place:" + k
        for k in (
            "east-e1a",
            "east-e1b",
            "east-e2a",
            "east-e2b",
            "east-e2c",
            "yifu",
            "earth-sciences",
            "card-centre",
            "tourism",
            "water-library",
        )
    }
    for p in places:
        assert p.position is not None
        if p.place_id in confirmed:
            assert p.position.source_kind == "onsite_confirmation" and p.position.reviewer == "宇豪"
            assert str(place_card(p)["navigation_url"]).startswith(
                "https://uri.amap.com/navigation?"
            )
        else:
            assert p.position.verification_status == "needs_review"
            assert place_card(p)["navigation_url"] is None
    assert {p.place_id for p in places if p.hotspot} >= {
        "cdut:place:water-library",
        "cdut:place:card-centre",
        "cdut:place:hospital",
    }
    # User-provided same-building association uses the ecological college provider point.
    assert repo.search_place("网安楼")[0].position is not None
    assert repo.search_place("校园一卡通中心")[0].position is not None
    assert repo.search_place("珙桐食堂")[0].name == "珙桐餐厅"
    assert all(p.category == "library" for p in repo.search_place("", "library"))
    teacher = repo.search_teacher("王洪辉")[0]
    assert teacher.office == "网安楼204室" and teacher.place_id == "cdut:place:network-security"
    replacement = assist(
        repo, AssistInput(kind="service", service_key="campus_card_replacement"), "test"
    )
    assert replacement.status == "success"
    assert {p.place_id for p in replacement.places} == {
        "cdut:place:gongtong-dining",
        "cdut:place:camphor-dining",
        "cdut:place:finance",
        "cdut:place:ginkgo-dining",
    }
    assert replacement.services[0].service_id != "cdut:service:campus-card-loss"
    with TestClient(create_app(data_dir=DATA, api_token=TOKEN)) as client:
        for endpoint, query in (("teachers", "王洪辉"), ("places", "网安楼")):
            path = f"/v1/directory/{endpoint}/search"
            assert client.post(path, json={"query": query}).status_code == 401
            result = client.post(path, json={"query": query}, headers=AUTH).json()["result"]
            assert result["status"] == "success" and result["data"]["evidence"]
        empty = client.post(
            "/v1/directory/assist",
            json={"kind": "teacher", "query": "未收录测试姓名"},
            headers=AUTH,
        ).json()
        assert empty["status"] == "empty" and empty["places"] == empty["teachers"] == []


def test_ambiguity_returns_candidates_and_cross_campus_association_rejected() -> None:
    services, offices, sources, places, teachers = load_records()
    # Mutated copies are negative fixtures, not university facts or checked-in inventory.
    copy = teachers[0].model_copy(update={"teacher_id": "cdut:teacher:synthetic-copy"})
    repo = DirectoryRepository(services, offices, sources, places, (*teachers, copy))
    result = assist(repo, AssistInput(kind="teacher", query=teachers[0].name), "test")
    assert result.status == "needs_clarification" and len(result.teachers) == 2
    assert [p.place_id for p in result.places] == ["cdut:place:network-security"]
    broken = teachers[0].model_dump(mode="json")
    broken.update(
        campus="SYNTHETIC WRONG CAMPUS", office="SYNTHETIC ROOM", place_id=places[0].place_id
    )
    broken["field_evidence"].extend(
        [
            {
                "field_path": field,
                "evidence_ids": [sources[0].evidence_id],
                "note": "NEGATIVE TEST ONLY",
            }
            for field in ("campus",)
            if field not in {x["field_path"] for x in broken["field_evidence"]}
        ]
    )
    with pytest.raises(ValueError):
        bad = CampusTeacher.model_validate_json(json.dumps(broken))
        DirectoryRepository(services, offices, sources, places, (bad,))


@pytest.mark.parametrize(
    "system,status,has_navigation",
    [("GCJ02", "needs_review", False), ("WGS84", "confirmed", False), ("GCJ02", "confirmed", True)],
)
def test_navigation_requires_reviewed_provider_coordinates(
    system: str, status: str, has_navigation: bool
) -> None:
    position: dict[str, Any] = {
        "longitude": 1.0,
        "latitude": 2.0,
        "coordinate_system": system,
        "source_kind": "map_provider",
        "source_url": "https://example.com/synthetic",
        "retrieved_at": "2026-10-07",
        "verification_status": status,
        "note": "SYNTHETIC TEST ONLY, NOT CAMPUS COORDINATES",
    }
    if status == "confirmed":
        position.update(confirmed_at="2026-10-07", reviewer="SYNTHETIC TEST REVIEWER")
    validated = MapPosition.model_validate_json(json.dumps(position))
    place = load_records()[3][0].model_copy(update={"position": validated})
    assert bool(place_card(place)["navigation_url"]) is has_navigation
    position.pop("reviewer", None)
    position.pop("confirmed_at", None)
    position["verification_status"] = "confirmed"
    with pytest.raises(ValidationError):
        MapPosition.model_validate_json(json.dumps(position))


def test_deterministic_api_workflow_cards_and_invalid_references_fail_closed() -> None:
    repo = DirectoryRepository.load(DATA)
    actual = assist(
        repo, AssistInput(kind="teacher", query="王洪辉"), "synthetic-request"
    ).model_dump_json()
    parsed = workflow_node("parse_result.py")(actual, 200)
    prose = "SYNTHETIC answer asks for cdut:place:unrelated; prose cannot select cards."
    packed = workflow_node("pack_answer.py")(prose, parsed["state"], parsed["references"])["answer"]
    envelope = AnswerEnvelope.model_validate_json(packed)
    assert envelope.teacher_ids == ("cdut:teacher:wang-honghui",)
    assert envelope.place_ids == ("cdut:place:network-security",)
    places = resolve_cards(repo, envelope)["places"]
    assert isinstance(places, list) and isinstance(places[0], dict)
    assert places[0]["place_id"] == "cdut:place:network-security"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answer": packed, "conversation_id": str(uuid4())})

    with TestClient(
        create_web_app(
            data_dir=DATA,
            dify=DifyClient(KEY, transport=httpx.MockTransport(handler), structured_answers=True),
        )
    ) as client:
        client.post("/api/session", headers=HEADERS)
        reply = client.post("/api/chat", json={"message": "Synthetic test"}, headers=HEADERS)
        assert reply.status_code == 200 and reply.json()["teachers"][0]["name"] == "王洪辉"
        assert reply.json()["places"][0]["place_id"] == "cdut:place:network-security"
    for ids in (("cdut:place:unrecorded",), (repo.search_place("")[0].place_id,)):
        with pytest.raises(ValueError):
            resolve_cards(repo, envelope.model_copy(update={"place_ids": ids}))
    failure = workflow_node("parse_result.py")(actual, 503)
    assert failure["state"] == "unavailable" and not any(json.loads(failure["references"]).values())
    malicious = workflow_node("build_request.py")(
        '{"kind":"teacher","query":"王洪辉","place_ids":["invented"]}'
    )
    assert json.loads(malicious["body"])["kind"] == "unknown"


def test_candidate_wires_references_from_code_not_model() -> None:
    flow = yaml.safe_load(
        (ROOT / "integrations/dify/CampusPilot-submission-candidate.yml").read_text(
            encoding="utf-8"
        )
    )
    nodes = {node["id"]: node["data"] for node in flow["workflow"]["graph"]["nodes"]}
    for ident, node in nodes.items():
        if node["type"] == "code":
            ast.parse(node["code"], filename=ident, feature_version=(3, 10))
    for ident in ("cp_pack", "cp_clarify_pack"):
        ref = next(v for v in nodes[ident]["variables"] if v["variable"] == "references")
        assert ref["value_selector"] == ["cp_result", "references"]
    assert nodes["cp_http"]["ssl_verify"] and not nodes["cp_http"]["retry_config"]["retry_enabled"]
    assert all(v["value"] == "" for v in flow["workflow"]["environment_variables"])


@pytest.mark.parametrize(
    "answer",
    [
        "Synthetic plain model text",
        '{"schema_version":1,"status":"success","answer":"Synthetic","coordinates":[1,2]}',
        '{"schema_version":1,"status":"empty","answer":"Synthetic","place_ids":["cdut:place:fake"]}',
    ],
)
def test_structured_mode_rejects_model_text_coordinates_and_empty_references(answer: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answer": answer, "conversation_id": str(uuid4())})

    with TestClient(
        create_web_app(
            data_dir=DATA,
            dify=DifyClient(KEY, transport=httpx.MockTransport(handler), structured_answers=True),
        )
    ) as client:
        client.post("/api/session", headers=HEADERS)
        response = client.post(
            "/api/chat", json={"message": "Synthetic boundary test"}, headers=HEADERS
        )
        assert response.status_code == 502 and response.json()["error_code"] == "invalid_response"
        assert "places" not in response.json()


def test_sdk_execution_policy_is_confined_to_map_view() -> None:
    with TestClient(create_web_app(data_dir=DATA)) as client:
        for path in ("/", "/api/map-config", "/assets/app.js"):
            policy = client.get(path).headers["content-security-policy"]
            assert "'unsafe-eval'" not in policy and "script-src 'self';" in policy
            assert "frame-ancestors 'none'" in policy
        frame = client.get("/map-view")
        assert frame.status_code == 200
        assert "'unsafe-eval'" in frame.headers["content-security-policy"]
        assert "frame-ancestors 'self'" in frame.headers["content-security-policy"]
        assert 'sandbox="allow-scripts allow-same-origin"' in client.get("/").text


def test_sdk_startup_jsonp_mime_and_server_owned_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_client = httpx.AsyncClient
    calls = 0
    leak_secret = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert str(request.url.copy_with(query=None)) == "https://restapi.amap.com/v3/log/init"
        assert request.url.params["key"] == "synthetic-map-key"
        assert request.url.params["jscode"] == "synthetic-map-secret"
        body = 'Synthetic.callback({"status":"1"});'
        if leak_secret:
            body += "synthetic-map-secret"
        return httpx.Response(200, text=body, headers={"content-type": "application/octet-stream"})

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        return original_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("campuspilot.web.httpx.AsyncClient", factory)
    with TestClient(
        create_web_app(
            data_dir=DATA, amap_key="synthetic-map-key", amap_security_code="synthetic-map-secret"
        )
    ) as client:
        params = {"callback": "Synthetic.callback", "key": "caller-key", "jscode": "caller-secret"}
        response = client.get("/_AMapService/v3/log/init", params=params)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/javascript")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "synthetic-map-secret" not in response.text
        assert (
            client.get("/_AMapService/v3/log/init", params={"callback": "bad();"}).status_code
            == 422
        )
        assert client.get("/_AMapService/v3/place/text").status_code == 404
        assert calls == 1
        leak_secret = True
        assert client.get("/_AMapService/v3/log/init", params=params).status_code == 502


def test_production_origin_secure_session_map_secret_and_restart_notice() -> None:
    with TestClient(
        create_web_app(
            data_dir=DATA,
            public_origin="https://campus.example",
            api_token=TOKEN,
            amap_key="synthetic-public-key",
            amap_security_code="synthetic-secret",
        ),
        base_url="https://campus.example",
    ) as client:
        assert "synthetic-secret" not in client.get("/api/map-config").text
        assert client.get("/api/map-config").json()["configured"]
        assert client.get("/_AMapService/https://evil.example/").status_code == 404
        assert client.post("/api/session", headers=HEADERS).status_code == 403
        headers = {**HEADERS, "Origin": "https://campus.example"}
        started = client.post("/api/session", headers=headers)
        assert "Secure" in started.headers["set-cookie"]
        token = client.cookies.get("campuspilot_session")
    with TestClient(create_web_app(data_dir=DATA)) as restarted:
        restarted.cookies.set("campuspilot_session", token or "")
        assert (
            restarted.post(
                "/api/chat", json={"message": "Synthetic restart"}, headers=HEADERS
            ).status_code
            == 401
        )

        assert restarted.post("/api/session/reset", headers=HEADERS).status_code == 200


def test_two_waiting_chats_do_not_block_tools_and_global_limits_cross_sessions() -> None:
    async def scenario() -> None:
        entered, finish = asyncio.Event(), asyncio.Event()
        count = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal count
            count += 1
            if count == 2:
                entered.set()
            await finish.wait()
            return httpx.Response(
                200, json={"answer": "Synthetic answer", "conversation_id": str(uuid4())}
            )

        app = create_web_app(
            data_dir=DATA,
            api_token=TOKEN,
            daily_chat_limit=2,
            dify=DifyClient(KEY, transport=httpx.MockTransport(handler)),
        )
        transport = httpx.ASGITransport(app)
        async with (
            httpx.AsyncClient(
                transport=transport, base_url="http://testserver", headers=HEADERS
            ) as a,
            httpx.AsyncClient(
                transport=transport, base_url="http://testserver", headers=HEADERS
            ) as b,
            httpx.AsyncClient(
                transport=transport, base_url="http://testserver", headers=HEADERS
            ) as c,
        ):
            for client in (a, b, c):
                await client.post("/api/session")
            tasks = [
                asyncio.create_task(client.post("/api/chat", json={"message": "Synthetic waiting"}))
                for client in (a, b)
            ]
            try:
                await asyncio.wait_for(entered.wait(), timeout=3)
                tool = await asyncio.wait_for(
                    c.post(
                        "/v1/directory/assist",
                        json={"kind": "teacher", "query": "王洪辉"},
                        headers=AUTH,
                    ),
                    timeout=3,
                )
                assert tool.status_code == 200 and tool.json()["status"] == "success"
                assert (
                    await c.post("/api/chat", json={"message": "Synthetic third"})
                ).status_code == 429
            finally:
                finish.set()
            assert all(r.status_code == 200 for r in await asyncio.gather(*tasks))
            assert (
                await c.post("/api/chat", json={"message": "Synthetic daily exhausted"})
            ).status_code == 429

    asyncio.run(scenario())
