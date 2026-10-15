"""SYNTHETIC portal probe classification; no browser or university facts."""

import runpy
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PROBE = runpy.run_path(str(SCRIPTS / "probe_official_collectors.py"))
URL = "https://bsdt.cdut.edu.cn/EIP/nonlogin/elobby/service/introduction/SYNTHETIC.htm"
CLAUSE = "SYNTHETIC 测试流程，不代表任何实际学校事实。" * 4
HTML = (
    '<div class="content-header-text-title">SYNTHETIC 服务</div>'
    '<div id="serviceCode">事项编号：1053</div>'
    '<section class="service-guide-item"><h2>基本信息</h2><p>SYNTHETIC 基本信息</p></section>'
    f'<section class="service-guide-item"><h2>办理流程</h2><p>{CLAUSE}</p></section>'
    '<section class="service-guide-item"><h2>其它说明</h2><p>SYNTHETIC 说明</p></section>'
    '<dl><dt>服务人群：</dt><dd>SYNTHETIC 学生</dd></dl>'
    '<dl><dt>所属部门：</dt><dd>SYNTHETIC 部门</dd></dl>'
    '<dl><dt>服务日期：</dt><dd>SYNTHETIC 日期</dd></dl>'
)
REFERENCE: dict[str, Any] = {
    "document_id": "SYNTHETIC", "title": "SYNTHETIC 服务", "item_code": "1053",
    "body": "\n".join(("SYNTHETIC 服务", "事项编号：1053", "基本信息", "SYNTHETIC 基本信息",
                       "办理流程", CLAUSE, "其它说明", "SYNTHETIC 说明", "服务人群：",
                       "SYNTHETIC 学生", "所属部门：", "SYNTHETIC 部门", "服务日期：",
                       "SYNTHETIC 日期")),
    "body_sha256": "SYNTHETIC reference hash",
}


def classify(html: str, url: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    result: dict[str, Any] = PROBE["classify_portal"](html, url, REFERENCE)
    return result


def test_portal_full_candidate_requires_every_reference_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = classify(HTML, URL, monkeypatch)
    assert result["full_body_candidate"] and result["matched_text_lines"] == 14
    assert result["reason"] == "portal_guide_all_reference_text_verified"
    partial = classify(HTML.replace(CLAUSE, "SYNTHETIC shortened flow"), URL, monkeypatch)
    assert not partial["full_body_candidate"] and partial["guide_nodes"] == 3
    assert partial["reason"] == "portal_guide_identity_or_reference_text_mismatch"
    assert not partial["challenge_marker_present"] and not partial["login_page_detected"]


@pytest.mark.parametrize("body,url,reason", [
    ("SYNTHETIC missing selectors", URL, "portal_guide_selector_missing_access_unresolved"),
    ("SYNTHETIC $_ts HTTP Status 412", URL, "challenge_without_complete_guide"),
    ('<form><input type="password"></form>', "https://cas.paas.cdut.edu.cn/cas/login",
     "login_page_without_complete_guide"),
])
def test_portal_selector_absence_is_not_misreported_as_access_failure(
    monkeypatch: pytest.MonkeyPatch, body: str, url: str, reason: str,
) -> None:
    result = classify(body, url, monkeypatch)
    assert not result["full_body_candidate"] and result["reason"] == reason
    assert "body" not in result and "html" not in result
