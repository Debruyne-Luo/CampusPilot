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
        assert "<title>理小龙 CDUTdino</title>" in shell and "<h1>理小龙</h1>" in shell
        assert shell.count("<h1>") == 1
        assert 'rel="icon" href="/assets/v2/brand-icon.png"' in shell and 'rel="manifest"' in shell
        for removed in ("成都理工大学 · 校园行动助手", "资料来自学校公开页面", 'id="unlocated"'):
            assert removed not in shell
        # One search bar (categories live inside its panel) and one locate button.
        for kept in ('id="map-search"', 'id="search-panel"', 'id="locate"'):
            assert kept in shell
        for cluttered in ('id="origin-button"', 'class="origin-bar"', 'id="filter-list"'):
            assert cluttered not in shell
        icon = client.get("/assets/v2/brand-icon.png")
        assert icon.status_code == 200 and icon.content.startswith(b"\x89PNG\r\n\x1a\n")
        manifest = json.loads(client.get("/assets/v2/manifest.webmanifest").content)
        assert manifest["short_name"] == "理小龙" and "CDUTdino" in manifest["name"]


def test_map_frame_allows_amap_poi_click_lookup_only_in_the_frame() -> None:
    with TestClient(create_web_app(data_dir=DATA)) as client:
        frame = client.get("/map-view").headers["content-security-policy"]
        page = client.get("/").headers["content-security-policy"]
        assert "https://vdata.amap.com" in frame and "frame-ancestors 'self'" in frame
        assert "vdata.amap.com" not in page and "script-src 'self';" in page


def test_embedded_model_textures_can_be_fetched_only_in_the_map_frame() -> None:
    # GLTFLoader decodes embedded PNGs by fetching local blob URLs before
    # createImageBitmap; img-src permission alone does not permit that fetch.
    with TestClient(create_web_app(data_dir=DATA)) as client:
        for path in ("/map-view", "/", "/classic", "/assets/dino3d.mjs"):
            policy = client.get(path).headers["content-security-policy"]
            directives = dict(
                (tokens[0], tokens[1:]) for part in policy.split(";") if (tokens := part.split())
            )
            allowed = directives["connect-src"]
            assert "'self'" in allowed
            assert ("blob:" in allowed) == (path == "/map-view")
            assert "*" not in allowed and "data:" not in allowed


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


ASSETS = Path(__file__).resolve().parents[1] / "backend" / "src" / "campuspilot" / "web_assets"


def test_v2_ui_has_no_disclaimer_lines() -> None:
    for path in [*(ASSETS / "v2").glob("*.mjs"), ASSETS / "v2" / "index.html"]:
        text = path.read_text(encoding="utf-8")
        for line in ("仅供参考", "入口以现场为准", "需现场核实", "成都校区", "设为终点"):
            assert line not in text, (path.name, line)


def test_map_frame_is_limited_to_campus_plus_one_km() -> None:
    frame = (ASSETS / "map-frame.js").read_text(encoding="utf-8")
    assert "setLimitBounds" in frame and "zooms: [MIN_ZOOM, 20]" in frame
    assert "const MIN_ZOOM = 15;" in frame
    # Every entry point that turns a tap / POI / search hit into a place checks the area.
    assert frame.count("inArea(") >= 6
