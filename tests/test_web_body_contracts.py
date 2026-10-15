"""Synthetic official-page readability and search-result selection contracts."""

import asyncio
import time

import httpx
import pytest
from campuspilot.web_evidence import (
    PageReadError,
    ProviderSearchResult,
    SafePageReader,
    SearchSource,
    WebEvidenceService,
    WebPageEvidence,
)
from test_web_evidence import FakeProvider, MemoryBudget, public_dns


def read_body(
    body: str,
    access_method: str,
) -> WebPageEvidence:
    """Exercise both public reader entry points without actual network access."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert access_method == "direct", "Provider extraction must not refetch a page"
        return httpx.Response(200, content=body.encode("utf-8"), headers={
            "content-type": "text/html; charset=utf-8",
        })

    reader = SafePageReader(httpx.MockTransport(handler), public_dns)
    source = SearchSource(
        "https://fixture.cdut.edu.cn/synthetic-notice",
        "SYNTHETIC source",
        raw_content=body if access_method == "provider_extraction" else None,
        access_method=access_method,
    )
    return asyncio.run(reader.read(source, time.monotonic() + 2))


@pytest.mark.parametrize("access_method", ["direct", "provider_extraction"])
@pytest.mark.parametrize("body", [
    "<html><title>SYNTHETIC Access Denied</title><body>Access denied</body></html>",
    "<html><title>SYNTHETIC 安全验证</title>"
    "<script>var $_ts = 'SYNTHETIC challenge';</script>"
    "<body>Please enable JavaScript to continue</body></html>",
    "<html><title>SYNTHETIC browser check</title>"
    "<body>Checking your browser before accessing the site</body></html>",
])
def test_http_200_protection_page_is_never_official_document_evidence(
    access_method: str, body: str,
) -> None:
    with pytest.raises(PageReadError, match="^page_protection_required$"):
        read_body(body, access_method)


@pytest.mark.parametrize("access_method", ["direct", "provider_extraction"])
def test_password_login_page_is_never_official_document_evidence(access_method: str) -> None:
    body = (
        "<html><title>SYNTHETIC 统一身份认证</title><body><form action='/login'>"
        "<label>帐号</label><input name='username'>"
        "<label>密码</label><input type='password' name='password'>"
        "<button>登录</button></form></body></html>"
    )
    with pytest.raises(PageReadError, match="^page_login_required$"):
        read_body(body, access_method)


@pytest.mark.parametrize("access_method", ["direct", "provider_extraction"])
def test_actual_guide_may_explain_logging_in_and_entering_password(access_method: str) -> None:
    body = (
        "<html><title>SYNTHETIC 登录使用指南</title><article>"
        "<h1>SYNTHETIC 统一身份认证操作指南</h1>"
        "<p>登录统一身份认证平台，按提示输入帐号和密码。</p>"
        "<p>首次使用先激活帐号，再办理查询业务。</p>"
        "</article></html>"
    )
    page = read_body(body, access_method)
    assert page.source_authority == "official_university"
    assert "首次使用先激活帐号" in page.text
    assert "按提示输入帐号和密码" in page.text


@pytest.mark.parametrize("content_type, prefix, encoding", [
    ("text/html; charset=gb18030", "", "gb18030"),
    ("text/html", '<meta charset="gb18030">', "gb18030"),
    ("text/html", "<meta http-equiv='Content-Type' content='text/html; charset=gb2312'>",
     "gb2312"),
    ("text/html; charset=utf-8", "", "utf-8"),
    ("text/html", "", "utf-8-sig"),
])
def test_official_chinese_text_uses_declared_charset_meta_or_bom(
    content_type: str, prefix: str, encoding: str,
) -> None:
    body = ("<html><head>" + prefix + "</head><body>"
            "<p>SYNTHETIC 本科生借书四十本。</p></body></html>")
    reader = SafePageReader(httpx.MockTransport(lambda request: httpx.Response(
        200, content=body.encode(encoding), headers={"content-type": content_type},
    )), public_dns)
    page = asyncio.run(reader.read(
        SearchSource("https://fixture.cdut.edu.cn/synthetic-guide", "SYNTHETIC guide"),
        time.monotonic() + 2,
    ))
    assert "本科生借书四十本。" in page.text
    assert "\ufffd" not in page.text


@pytest.mark.parametrize("body, content_type", [
    (b"<p>SYNTHETIC \xff</p>", "text/html; charset=utf-8"),
    ("<p>SYNTHETIC 中文。</p>".encode("gb18030"), "text/html; charset=utf-8"),
    ("<p>SYNTHETIC 中文。</p>".encode(), "text/html; charset=ascii"),
    (b"<p>SYNTHETIC content</p>", "text/html; charset=synthetic-unknown-codec"),
])
def test_invalid_encoding_is_explicit_failure_instead_of_replacement_evidence(
    body: bytes, content_type: str,
) -> None:
    reader = SafePageReader(httpx.MockTransport(lambda request: httpx.Response(
        200, content=body, headers={"content-type": content_type},
    )), public_dns)
    with pytest.raises(PageReadError, match="^page_encoding_invalid$"):
        asyncio.run(reader.read(
            SearchSource("https://fixture.cdut.edu.cn/synthetic-guide", "SYNTHETIC guide"),
            time.monotonic() + 2,
        ))


def test_http_412_reports_access_protection_without_claiming_document_read() -> None:
    reader = SafePageReader(httpx.MockTransport(lambda request: httpx.Response(
        412, text="SYNTHETIC access protection", headers={"content-type": "text/html"},
    )), public_dns)
    with pytest.raises(PageReadError, match="^page_protection_required$"):
        asyncio.run(reader.read(
            SearchSource("https://fixture.cdut.edu.cn/synthetic-guide", "SYNTHETIC guide"),
            time.monotonic() + 2,
        ))


def test_official_priority_preserves_provider_relevance_before_three_page_cap() -> None:
    urls = (
        "https://third.example/synthetic-z",
        "https://fixture.cdut.edu.cn/synthetic-z",
        "https://fixture.cdut.edu.cn/synthetic-y",
        "https://fixture.cdut.edu.cn/synthetic-a",
        "https://fixture.cdut.edu.cn/synthetic-0",
        "https://third.example/synthetic-a",
    )
    provider = FakeProvider(ProviderSearchResult("success", tuple(
        SearchSource(url, "SYNTHETIC result") for url in urls
    )))
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        # Read completion order must not replace provider relevance order either.
        await asyncio.sleep(0.02 if request.url.path.endswith("-z") else 0)
        return httpx.Response(200, text="SYNTHETIC official document body",
                              headers={"content-type": "text/plain; charset=utf-8"})

    budget = MemoryBudget()
    service = WebEvidenceService(
        budget, provider, reader=SafePageReader(httpx.MockTransport(handler), public_dns),
    )
    result = asyncio.run(service.search("SYNTHETIC official source query"))
    assert result.status == "success"
    assert result.attempts == 1 and result.page_reads == 3 and budget.flows == 1
    assert [page.url for page in result.pages] == list(urls[1:4])
    assert sorted(paths) == ["/synthetic-a", "/synthetic-y", "/synthetic-z"]


def test_third_party_order_is_stable_after_official_priority() -> None:
    urls = (
        "https://third.example/synthetic-z",
        "https://fixture.cdut.edu.cn/synthetic-notice",
        "https://third.example/synthetic-a",
    )
    provider = FakeProvider(ProviderSearchResult("success", tuple(
        SearchSource(url, "SYNTHETIC result") for url in urls
    )))
    reader = SafePageReader(httpx.MockTransport(lambda request: httpx.Response(
        200, text="SYNTHETIC readable source body", headers={"content-type": "text/plain"},
    )), public_dns)
    result = asyncio.run(WebEvidenceService(MemoryBudget(), provider, reader=reader).search(
        "SYNTHETIC source query",
    ))
    assert [page.url for page in result.pages] == [urls[1], urls[0], urls[2]]
    assert result.page_reads == 3


def test_deadline_retains_body_read_before_slow_sibling() -> None:
    provider = FakeProvider(ProviderSearchResult("success", (
        SearchSource("https://fixture.cdut.edu.cn/synthetic-slow", "SYNTHETIC slow"),
        SearchSource("https://fixture.cdut.edu.cn/synthetic-fast", "SYNTHETIC fast"),
    )))

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("-slow"):
            await asyncio.sleep(1)
        return httpx.Response(200, text="SYNTHETIC readable body",
                              headers={"content-type": "text/plain"})

    result = asyncio.run(WebEvidenceService(
        MemoryBudget(), provider, reader=SafePageReader(httpx.MockTransport(handler), public_dns),
        timeout_seconds=0.05,
    ).search("SYNTHETIC public question"))
    assert result.status == "success" and result.reason == "partial_page_reads"
    assert [page.url for page in result.pages] == [
        "https://fixture.cdut.edu.cn/synthetic-fast"
    ]


def test_flow_preserves_common_page_failure_reason() -> None:
    provider = FakeProvider(ProviderSearchResult("success", (
        SearchSource("https://fixture.cdut.edu.cn/synthetic-notice", "SYNTHETIC"),
    )))
    result = asyncio.run(WebEvidenceService(
        MemoryBudget(), provider, reader=SafePageReader(
            httpx.MockTransport(lambda request: httpx.Response(412)), public_dns
        ),
    ).search("SYNTHETIC public question"))
    assert result.status == "limited" and not result.pages
    assert result.reason == "page_protection_required"
