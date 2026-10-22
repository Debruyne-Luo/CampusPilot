"""SYNTHETIC provider responses; never call a live service or assert campus facts."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from campuspilot.official_capture import (
    FirecrawlCollector,
    attachment_links,
    classify_response,
    embedded_images,
    request_options,
    reviewed_capture,
)

URL = "https://www.cdut.edu.cn/info/SYNTHETIC.htm"
BODY = "SYNTHETIC 不代表学校事实的测试正文。" * 5


def payload(body: str = BODY, **metadata: object) -> dict[str, Any]:
    return {"success": True, "data": {"markdown": body, "metadata": {
        "statusCode": 200, "sourceURL": URL, **metadata}, "links": []}}


@pytest.mark.parametrize("value", ["https://evil.example/a", "https://cas.cdut.edu.cn/cas/login",
                                    "https://www.cdut.edu.cn/login/start",
                                    "https://www.cdut.edu.cn/guide?access_token=SYNTHETIC"])
def test_reject_unapproved_or_authenticated_destination_before_network(value: str) -> None:
    with pytest.raises(ValueError):
        request_options({"url": value})


def test_html_disables_unbudgeted_document_parsing_and_pdf_has_hard_bound() -> None:
    assert request_options({"url": URL})["parsers"] == []
    opts = request_options({"url": URL, "format": "pdf"})
    assert opts["parsers"][0]["maxPages"] == 10
    with pytest.raises(ValueError):
        request_options({"url": URL, "format": "office"})


def test_provider_success_is_never_authority_or_proof_of_complete_document() -> None:
    assert classify_response(payload(), "html", 10)["status"] == "pending_review"
    assert classify_response(payload(statusCode=412), "html", 10)["status"] == "access_failed"
    assert classify_response(payload("安全验证" * 30), "html", 10)["reason"] == "challenge_body"
    assert classify_response(payload(totalPages=20), "pdf", 10)["status"] == "truncated"
    assert classify_response(payload(), "pdf", 10)["reason"] == "pdf_completeness_unverified"


def test_links_are_deduplicated_public_attachments_only() -> None:
    links = attachment_links(URL, ["/SYNTHETIC.pdf", "/SYNTHETIC.pdf", "https://evil/a.pdf",
                                  "/login/a.pdf", "/SYNTHETIC.xlsx", "/notice.htm"])
    assert [x["format"] for x in links] == ["pdf", "office"]


def test_wechat_image_dependencies_are_counted_without_claiming_ocr() -> None:
    text = "![x](https://mmbiz.qpic.cn/a/640?wx_fmt=png#i=1) ![x](https://evil.example/a.png)"
    images = embedded_images("https://mp.weixin.qq.com/s/SYNTHETIC", text)
    assert len(images) == 1 and images[0]["status"] == "missing_ocr"
    assert embedded_images(URL, text) == []


def mock_client(*, timeout: bool = False, balance: int = 10) -> tuple[httpx.Client, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={"success": True, "data": {
                "remainingCredits": balance, "planCredits": 1000}})
        if timeout:
            raise httpx.ReadTimeout("SYNTHETIC timeout", request=request)
        return httpx.Response(200, json=payload())

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_timeout_reservation_survives_resume_without_resubmission(tmp_path: Path) -> None:
    client, calls = mock_client(timeout=True)
    collector = FirecrawlCollector("SYNTHETIC-KEY", tmp_path, credit_limit=2,
                                   client=client, sleep=lambda _: None)
    first = collector.collect([{"url": URL}], free_plan_confirmed=True, max_followups=0)
    assert first["reserved_credits"] == 1 and first["requests"][0]["status"] == "unknown"
    collector.collect([{"url": URL}], free_plan_confirmed=True, max_followups=0)
    assert calls.count("POST") == 1
    assert b"SYNTHETIC-KEY" not in (tmp_path / "collection.json").read_bytes()


def test_budget_is_reserved_before_network_and_never_exceeds_balance(tmp_path: Path) -> None:
    client, calls = mock_client(balance=1)
    collector = FirecrawlCollector("SYNTHETIC", tmp_path, credit_limit=2,
                                   client=client, sleep=lambda _: None)
    data = collector.collect([{"url": URL}, {"url": URL + "?second=1"}],
                             free_plan_confirmed=True, max_followups=0)
    assert calls.count("POST") == 1 and data["reserved_credits"] == 1
    assert data["deferred"][0]["reason"] == "free_credit_budget_exhausted"


def test_no_free_billing_confirmation_causes_zero_calls(tmp_path: Path) -> None:
    client, calls = mock_client()
    collector = FirecrawlCollector("SYNTHETIC", tmp_path, client=client)
    with pytest.raises(ValueError, match="confirmation_required"):
        collector.collect([{"url": URL}], free_plan_confirmed=False)
    assert calls == []


@pytest.mark.parametrize("balance", [-1, True, float("nan"), float("inf")])
def test_invalid_credit_balance_never_permits_submission(tmp_path: Path, balance: float) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        content = json.dumps({"success": True, "data": {"remainingCredits": balance}})
        return httpx.Response(200, content=content)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = FirecrawlCollector("SYNTHETIC-KEY", tmp_path, client=client)
    report = collector.collect([{"url": URL}], free_plan_confirmed=True)
    assert report["blocked_reason"] == "credit_balance_unavailable"
    assert report["reserved_credits"] == 0


def test_capture_export_requires_independent_hash_bound_reference_check(tmp_path: Path) -> None:
    client, _ = mock_client()
    collector = FirecrawlCollector("SYNTHETIC-KEY", tmp_path, client=client, sleep=lambda _: None)
    result = collector.collect([{"url": URL}], free_plan_confirmed=True, max_followups=0)
    row = result["requests"][0]
    review = {"body_sha256": row["body_sha256"], "complete": True,
              "checked_by": "synthetic-validator", "required_text": [BODY],
              "title": "SYNTHETIC title", "publisher": "SYNTHETIC publisher"}
    doc = reviewed_capture(tmp_path, row, review)
    assert doc["complete"] and "clauses" not in doc
    with pytest.raises(ValueError, match="hash_mismatch"):
        reviewed_capture(tmp_path, row, {**review, "body_sha256": "wrong"})
    ledger = json.loads((tmp_path / "collection.json").read_bytes())
    assert not ledger["adopted"] and not ledger["published"]
