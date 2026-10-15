"""Synthetic provider replies exercise discovery boundaries, not real POI acceptance."""

from pathlib import Path

import httpx
import pytest
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.places_discovery import CAMPUS_CENTER, PlaceDiscovery
from campuspilot.tools.directory import PlaceDiscoveryTool
from campuspilot.web import create_web_app
from fastapi.testclient import TestClient

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}


def empty_repository() -> DirectoryRepository:
    return DirectoryRepository((), (), ())


def poi(name: str = "合成学院", ident: str = "SYNTHETIC01", location: str = "") -> dict[str, str]:
    return {
        "id": ident,
        "name": name,
        "address": "Synthetic fixture; not a campus record.",
        "location": location or ",".join(map(str, CAMPUS_CENTER)),
    }


def provider(rows: list[dict[str, str]]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "restapi.amap.com"
        assert request.url.path == "/v3/place/around"
        assert request.url.params["radius"] == "2000"
        assert request.url.params["offset"] == "10"
        assert request.url.params["sortrule"] == "weight"
        assert request.url.params["location"] == ",".join(map(str, CAMPUS_CENTER))
        assert "longitude" not in request.url.params
        return httpx.Response(200, json={"status": "1", "pois": rows})

    return httpx.MockTransport(handle)


def test_classroom_exact_prevents_provider_and_wider_buildings() -> None:
    def forbidden(_: httpx.Request) -> httpx.Response:
        raise AssertionError("Exact catalogue queries must not contact the provider")

    repo = DirectoryRepository.load(DATA)
    service = PlaceDiscovery(
        repo, enabled=True, key="synthetic", transport=httpx.MockTransport(forbidden)
    )
    for text in ("东教E2A403", "东教 Ｅ２Ａ４０３", "我想去东教 E2A 403"):
        result = service.search(text)
        assert result["provider_status"] == "local"
        assert result["resolution"] == "exact"
        assert isinstance(result["places"], list) and len(result["places"]) == 1
        card = result["places"][0]
        assert isinstance(card, dict)
        assert str(card["name"]).endswith("E2A")
    assert service.search("东教E9Z403")["places"] == []


@pytest.mark.parametrize(
    "campus_prefix", ["成都理工大学-", "成都理工大学二仙桥校区", "成都理工大学成都校区—"]
)
def test_exact_provider_match_is_typed_transient_location_only(campus_prefix: str) -> None:
    service = PlaceDiscovery(
        empty_repository(),
        enabled=True,
        key="synthetic",
        transport=provider([poi(campus_prefix + "合成学院")]),
    )
    result = service.search("我想去合成学院")
    assert result["resolution"] == "exact"
    cards = result["places"]
    assert isinstance(cards, list)
    card = cards[0]
    assert isinstance(card, dict)
    assert card["place_id"] == "amap:poi:SYNTHETIC01"
    assert card["source_provider"] == "amap" and card["transient"] is True
    assert card["evidence_scope"] == "location_only"
    assert "verification_status" not in card and "field_evidence" not in card
    assert empty_repository().search_place() == ()


def test_one_fuzzy_result_is_candidate_and_multiple_exact_do_not_autoselect() -> None:
    fuzzy = PlaceDiscovery(
        empty_repository(),
        enabled=True,
        key="synthetic",
        transport=provider([poi("合成学院办公楼")]),
    )
    assert fuzzy.search("合成学院")["resolution"] == "candidates"
    repeated = PlaceDiscovery(
        empty_repository(),
        enabled=True,
        key="synthetic",
        transport=provider([poi(), poi(ident="SYNTHETIC02", location="104.148,30.676")]),
    )
    result = repeated.search("合成学院")
    assert result["resolution"] == "candidates"
    assert isinstance(result["places"], list) and len(result["places"]) == 2


def test_invalid_out_of_range_unrelated_and_duplicate_rows_are_removed() -> None:
    service = PlaceDiscovery(
        empty_repository(),
        enabled=True,
        key="synthetic",
        transport=provider(
            [
                poi(),
                poi(),
                poi(ident="bad id"),
                poi(ident="SYNTHETIC02", location="NaN,30.675"),
                poi(ident="SYNTHETIC03", location="104.17,30.675"),
                poi("无关合成地点", "SYNTHETIC04"),
                poi(ident="SYNTHETIC05", location="104.15,30.694"),
            ]
        ),
    )
    result = service.search("合成学院")
    assert isinstance(result["places"], list) and len(result["places"]) == 1


@pytest.mark.parametrize(
    "kind, expected",
    [
        ("timeout", "timeout"),
        ("quota", "quota_exceeded"),
        ("invalid", "unavailable"),
        ("redirect", "unavailable"),
        ("oversize", "unavailable"),
        ("empty", "empty"),
    ],
)
def test_provider_failures_remain_distinct(kind: str, expected: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if kind == "timeout":
            raise httpx.ReadTimeout("Synthetic timeout", request=request)
        if kind == "quota":
            return httpx.Response(200, json={"status": "0", "infocode": "10003"})
        if kind == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/"})
        if kind == "oversize":
            return httpx.Response(200, content=b"x" * 256_001)
        if kind == "empty":
            return httpx.Response(200, json={"status": "1", "pois": []})
        return httpx.Response(200, json={"status": "1", "pois": "bad"})

    service = PlaceDiscovery(
        empty_repository(), enabled=True, key="synthetic", transport=httpx.MockTransport(handler)
    )
    result = service.search("合成学院")
    assert result["provider_status"] == expected
    assert result["places"] == [] and result["map_pick_available"] is True
    if kind == "quota":
        service.search("合成学院")
        assert calls == 1, "Quota errors stop retries during the cooldown"


def test_web_endpoint_and_tool_share_service_and_session_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PlaceDiscovery(
        empty_repository(), enabled=True, key="synthetic", transport=provider([poi()])
    )
    from campuspilot.app import factory

    monkeypatch.setattr(factory, "PlaceDiscovery", lambda *args, **kwargs: service)
    app = create_web_app(data_dir=DATA, amap_discovery=True, amap_web_service_key="synthetic")
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/places/search", json={"query": "合成学院"}, headers=HEADERS
            ).status_code
            == 401
        )
        client.post("/api/session", headers=HEADERS)
        assert client.post("/api/places/search", json={"query": "合成学院"}).status_code == 403
        response = client.post("/api/places/search", json={"query": "合成学院"}, headers=HEADERS)
        assert response.status_code == 200
        assert (
            response.json()["places"]
            == PlaceDiscoveryTool(service).run(PlaceDiscoveryTool.params_model(query="合成学院"))[
                "places"
            ]
        )
        assert '"key"' not in response.text
        assert (
            client.post(
                "/api/places/search",
                json={"query": "合成学院", "longitude": 104.1},
                headers=HEADERS,
            ).status_code
            == 422
        )
