"""Provider-extracted fixtures preserve source identity and verification limits."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from campuspilot.evaluation_budget import OnlineBudget
from campuspilot.web_evidence import SafePageReader, TavilySearchProvider, WebEvidenceService


@pytest.mark.parametrize(
    ("source_url", "authority"),
    [
        ("https://fixture.cdut.edu.cn/synthetic-notice#section", "official_university"),
        ("https://outside.example/synthetic-notice", "third_party"),
        ("https://cdut.edu.cn.outside.example/synthetic-notice", "third_party"),
    ],
)
def test_extraction_retains_returned_source_and_unverified_historical_scope(
    tmp_path: Path, source_url: str, authority: str,
) -> None:
    sent: list[dict[str, Any]] = []

    def reply(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={
            "answer": "SYNTHETIC GENERATED ANSWER MUST NOT BECOME EVIDENCE",
            "results": [{
                "url": source_url,
                "title": "SYNTHETIC historical document",
                "published_date": "2014-12-04",
                "raw_content": "<p>SYNTHETIC historical source body</p>",
                "content": "SYNTHETIC SNIPPET MUST NOT BECOME EVIDENCE",
            }],
        })

    def no_local_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Provider extraction must not trigger a local HTTP request")

    async def no_local_dns(host: str) -> tuple[str, ...]:
        raise AssertionError("Provider extraction must not resolve a local HTTP target")

    provider = TavilySearchProvider(
        "SYNTHETIC-key", free_plan_confirmed=True, transport=httpx.MockTransport(reply),
    )
    reader = SafePageReader(httpx.MockTransport(no_local_request), no_local_dns)
    budget = OnlineBudget(tmp_path, Decimal("1"), 20, today="20261015")
    result = asyncio.run(WebEvidenceService(budget, provider, reader=reader).search("SYNTHETIC"))

    assert result.status == "success" and len(result.pages) == 1
    assert sent[0]["query"].startswith("成都理工大学 site:cdut.edu.cn ")
    page = result.pages[0]
    assert page.url == source_url.split("#", 1)[0]
    assert page.source_authority == authority
    assert page.access_method == "provider_extraction"
    assert page.published_at == "2014-12-04"
    assert page.temporal_status == "unknown"
    assert page.text == "SYNTHETIC historical source body"
    hit = page.as_hit()
    assert hit["verification_status"] == "unreviewed_web"
    assert hit["grounded"] is False
    assert result.page_reads == 1
