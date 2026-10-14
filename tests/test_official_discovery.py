"""SYNTHETIC catalog discovery contract fixtures, never real university facts."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = "https://www.cdut.edu.cn/SYNTHETIC/catalog.htm"
DETAIL = "https://www.cdut.edu.cn/info/SYNTHETIC/1001.htm"


def module() -> ModuleType:
    name = "synthetic_official_discovery"
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/official_discovery.py")
    assert spec is not None and spec.loader is not None
    imported = importlib.util.module_from_spec(spec)
    sys.modules[name] = imported
    spec.loader.exec_module(imported)
    return imported


def catalog(url: str, body: str) -> str:
    return f"""<!-- saved from url=(0100){url} -->
    <html><head><title>SYNTHETIC saved catalog</title></head><body>{body}</body></html>"""


def write(tmp_path: Path, filename: str, url: str, body: str) -> Path:
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    (source / filename).write_text(catalog(url, body), encoding="utf-8")
    return source


def test_actual_links_and_pagination_frontier_without_date_stopping(tmp_path: Path) -> None:
    imported = module()
    source = write(tmp_path, "one.html", CATALOG, f"""
      <nav><a href="/index.htm">首页</a></nav>
      <ul><li><span>2020-01-01</span><a href="{DETAIL}">SYNTHETIC pinned old notice</a></li>
      <li><span>2026-10-14</span><a href="../info/SYNTHETIC/1002.htm">SYNTHETIC new notice</a></li>
      <li><span>2010-01-01</span><a href="/info/SYNTHETIC/1003.htm">SYNTHETIC archived policy</a>
      </li></ul><div class="p_pages"><span class="p_next"><a href="catalog/2.htm">下页</a>
      </span><span class="p_last"><a href="catalog/9.htm">尾页</a></span></div>""")
    write(tmp_path, "two.html", "https://www.cdut.edu.cn/SYNTHETIC/catalog/2.htm", """
      <ul><li><span>2001-01-01</span><a href="/info/SYNTHETIC/1004.htm">SYNTHETIC older rule</a>
      </li></ul><div class="pagination"><a href="../../catalog.htm">首页</a>
      <a href="3.htm">3</a></div>""")
    result = imported.discover(source, ["one.html", "two.html"], "2026-10-14")
    assert len(result["documents"]) == 4
    assert result["all_supplied_pages_scanned"] is True
    assert result["date_cutoff_used"] is False
    assert result["full_column_coverage_claimed"] is False
    assert result["network_access"] is False
    assert result["documents"][0]["observations"][0]["date_text"] == ["2020-01-01"]
    assert result["catalogs"][0]["pagination"][0]["saved_catalog_supplied"] is True
    assert len(result["unvisited_pagination"]) == 3
    assert all(row["fetched"] is False for row in result["unvisited_pagination"])
    assert not any(row["url"].endswith("index.htm") for row in result["unvisited_pagination"])


def test_url_normalization_deduplicates_actual_evidence(tmp_path: Path) -> None:
    imported = module()
    source = write(tmp_path, "one.html", CATALOG, """
      <a href="HTTPS://WWW.CDUT.EDU.CN:443/info/SYNTHETIC/100%31.htm?b=2&amp;a=1#part">
      SYNTHETIC first</a>
      <a href="/info/SYNTHETIC/1001.htm?a=1&amp;b=2&amp;utm_source=SYNTHETIC">SYNTHETIC second</a>
      <a href="/info/SYNTHETIC/1001.htm?b=2&amp;a=1&amp;_t=123">SYNTHETIC third</a>""")
    result = imported.discover(source, ["one.html"], "2026-10-14")
    assert len(result["documents"]) == 1
    item = result["documents"][0]
    assert item["url"] == DETAIL + "?a=1&b=2"
    assert len(item["observations"]) == 3
    assert item["title"] == "SYNTHETIC first"
    assert item["body_collected"] is False and item["adopted"] is False


def test_drops_script_form_hidden_private_and_nonofficial_links(tmp_path: Path) -> None:
    imported = module()
    source = write(tmp_path, "one.html", CATALOG, f"""
      <script>var token='SYNTHETIC_SECRET'; var html='<a href="{DETAIL}">SYNTHETIC script</a>';
      </script><form><a href="{DETAIL}">SYNTHETIC personal form</a></form>
      <div style="display:none"><a href="{DETAIL}">SYNTHETIC hidden</a></div>
      <a href="{DETAIL}?ticket=SYNTHETIC_SESSION">SYNTHETIC account</a>
      <a href="{DETAIL}#token=SYNTHETIC_FRAGMENT_SECRET">SYNTHETIC private fragment</a>
      <a href="https://www.cdut.edu.cn.example.test/info/SYNTHETIC/1001.htm">SYNTHETIC external</a>
      <a href="javascript:SYNTHETIC_EXEC()" onclick="location.href='{DETAIL}'">SYNTHETIC event</a>
      <a href="{DETAIL}" title="SYNTHETIC actual title">SYNTHETIC visible</a>""")
    result = imported.discover(source, ["one.html"], "2026-10-14")
    assert len(result["documents"]) == 1
    assert result["documents"][0]["title"] == "SYNTHETIC actual title"
    serialized = json.dumps(result)
    for forbidden in ("SECRET", "SESSION", "personal form", "hidden", "SYNTHETIC_EXEC",
                      "SYNTHETIC script", "ticket="):
        assert forbidden not in serialized


@pytest.mark.parametrize("name", ["../SYNTHETIC.html", "%2e%2e/SYNTHETIC.html",
                                  "C:/SYNTHETIC.html", "/SYNTHETIC.html"])
def test_catalog_path_escape_rejected(tmp_path: Path, name: str) -> None:
    imported = module()
    source = write(tmp_path, "one.html", CATALOG, "SYNTHETIC")
    with pytest.raises(imported.InvalidDiscovery, match="unsafe_catalog_path"):
        imported.discover(source, [name], "2026-10-14")


@pytest.mark.parametrize("url", ["https://www.cdut.edu.cn/SYNTHETIC.htm?token=SYNTHETIC",
                                 "https://www.cdut.edu.cn/EIP/personalCenter/SYNTHETIC.htm",
                                 "https://example.test/SYNTHETIC.htm"])
def test_private_or_nonofficial_catalog_source_rejected(tmp_path: Path, url: str) -> None:
    imported = module()
    source = write(tmp_path, "one.html", url, f'<a href="{DETAIL}">SYNTHETIC</a>')
    with pytest.raises(imported.InvalidDiscovery):
        imported.discover(source, ["one.html"], "2026-10-14")


def test_supplied_captures_of_same_url_are_all_scanned(tmp_path: Path) -> None:
    imported = module()
    source = write(tmp_path, "one.html", CATALOG, f'<a href="{DETAIL}">SYNTHETIC earlier</a>')
    write(tmp_path, "two.html", CATALOG, '<a href="/info/SYNTHETIC/1002.htm">SYNTHETIC later</a>')
    result = imported.discover(source, ["one.html", "two.html"], "2026-10-14")
    assert len(result["catalogs"]) == 2
    assert len(result["documents"]) == 2


def test_custom_pattern_and_malformed_pattern(tmp_path: Path) -> None:
    imported = module()
    source = write(tmp_path, "one.html", CATALOG,
                   '<a href="/SYNTHETIC/contents/1001.html">SYNTHETIC custom detail</a>')
    assert imported.discover(source, ["one.html"], "2026-10-14")["documents"] == []
    assert len(imported.discover(source, ["one.html"], "2026-10-14",
                                r"^/SYNTHETIC/contents/\d+\.html$")["documents"]) == 1
    with pytest.raises(imported.InvalidDiscovery, match="invalid_detail_pattern"):
        imported.discover(source, ["one.html"], "2026-10-14", "[")


def test_image_only_links_are_discovered_without_inventing_titles(tmp_path: Path) -> None:
    imported = module()
    source = write(tmp_path, "one.html", CATALOG, f"""
      <a href="{DETAIL}"><img src="SYNTHETIC.png"></a>
      <a href="{DETAIL}">SYNTHETIC later actual title</a>
      <a href="/info/SYNTHETIC/1002.htm"><img src="SYNTHETIC.png" alt="SYNTHETIC alt"></a>
      <a href="/info/SYNTHETIC/1003.htm"><img src="SYNTHETIC.png"></a>""")
    result = imported.discover(source, ["one.html"], "2026-10-14")
    assert len(result["documents"]) == 3
    assert result["documents"][0]["title"] == "SYNTHETIC later actual title"
    assert result["documents"][0]["observations"][0]["title"] is None
    assert result["documents"][1]["title"] == "SYNTHETIC alt"
    assert result["documents"][2]["title"] is None
