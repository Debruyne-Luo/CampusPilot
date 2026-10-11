"""理小龙 v2 shell: branding, removed notices, manifest/icon, and map-frame POI-click CSP."""

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from campuspilot.web import create_web_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"


def test_shell_branding_and_removed_notices() -> None:
    with TestClient(create_web_app(data_dir=DATA)) as client:
        shell = client.get("/").text
        assert "<title>理小龙 CDUTdino</title>" in shell and "<b>理小龙</b>" in shell
        assert 'rel="icon" href="/assets/v2/dino.svg"' in shell and 'rel="manifest"' in shell
        for removed in ("成都理工大学 · 校园行动助手", "资料来自学校公开页面", 'id="unlocated"'):
            assert removed not in shell
        assert 'id="map-search"' in shell and 'id="origin-button"' in shell
        icon = client.get("/assets/v2/dino.svg")
        assert icon.status_code == 200 and "<script" not in icon.text
        manifest = json.loads(client.get("/assets/v2/manifest.webmanifest").content)
        assert manifest["short_name"] == "理小龙" and "CDUTdino" in manifest["name"]


def test_map_frame_allows_amap_poi_click_lookup_only_in_the_frame() -> None:
    with TestClient(create_web_app(data_dir=DATA)) as client:
        frame = client.get("/map-view").headers["content-security-policy"]
        page = client.get("/").headers["content-security-policy"]
        assert "https://vdata.amap.com" in frame and "frame-ancestors 'self'" in frame
        assert "vdata.amap.com" not in page and "script-src 'self';" in page


def test_places_api_carries_hotspot_flag_for_an_uncluttered_map() -> None:
    headers = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}
    with TestClient(create_web_app(data_dir=DATA)) as client:
        client.post("/api/session", headers=headers)
        places = client.get("/api/places", headers=headers).json()["places"]
        hot = [p for p in places if p.get("hotspot")]
        assert 10 <= len(hot) <= 16 and len(hot) < len(places)
        assert all(p["position"] for p in hot)
        names = {p["name"] for p in hot}
        assert {"水上图书馆", "东区图书馆", "校园一卡通中心", "校医院", "珙桐餐厅"} <= names
