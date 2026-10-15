"""Synthetic web-provider contracts, SSRF barriers and budget/decision failure behavior."""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from campuspilot.evaluation_budget import BudgetExhausted, OnlineBudget, SpendBudget, TokenPrice
from campuspilot.jev_plugin import JevPlugin, combine
from campuspilot.jev_shadow import JevShadowClient, ShadowResult
from campuspilot.rag import RetrievalHit
from campuspilot.web_evidence import (
    DeepSeekSearchProvider,
    PageReadError,
    ProviderSearchResult,
    SafePageReader,
    SearchSource,
    TavilySearchProvider,
    TurnEvidenceContext,
    WebEvidenceService,
    WebPageEvidence,
    public_url,
    validated_addresses,
)


class MemoryBudget(OnlineBudget):
    """Synthetic ledger for HTTP-only tests; real durable-ledger tests are separate."""

    def __init__(self) -> None:
        self.items: dict[str, tuple[Decimal, Decimal | None]] = {}
        self.flows = 0
        self.credits = 0

    def reserve(self, maximum_cost: Decimal, label: str) -> str:
        ident = str(len(self.items))
        self.items[ident] = (maximum_cost, None)
        return ident

    def settle(self, ident: str, actual_cost: Decimal | None) -> None:
        maximum, _ = self.items[ident]
        self.items[ident] = (maximum, actual_cost)

    def reserve_search_flow(self) -> str:
        self.flows += 1
        return str(self.flows)

    def reserve_free_search_credit(self, monthly_limit: int = 1000) -> None:
        self.credits += 1


async def public_dns(host: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


def native_reply(*sources: str) -> dict[str, object]:
    return {
        "content": [{"type": "web_search_tool_result", "content": [
            {"type": "web_search_result", "url": u, "title": "SYNTHETIC " + str(i),
             "page_age": "2026-10-14"}
            for i, u in enumerate(sources)
        ]}],
        "usage": {"input_tokens": 40, "output_tokens": 12},
    }


def deepseek(handler: Any) -> DeepSeekSearchProvider:
    return DeepSeekSearchProvider(
        "SYNTHETIC-key", TokenPrice(Decimal("0.3"), Decimal("1.2")), Decimal("0"),
        transport=httpx.MockTransport(handler),
    )


def test_native_protocol_only_real_blocks_and_actual_usage() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        assert request.url.path == "/anthropic/v1/messages"
        assert request.headers["anthropic-version"] == "2023-06-01"
        return httpx.Response(200, json=native_reply("https://fixture.example/notice"))

    budget = MemoryBudget()
    result = asyncio.run(deepseek(handler).search("SYNTHETIC question", budget,
                                                time.monotonic() + 2))
    assert result.status == "success" and len(result.sources) == 1
    assert sent[0]["tools"] == [{"type": "web_search_20250305", "name": "web_search",
                                 "max_uses": 1}]
    maximum, actual = budget.items["0"]
    assert maximum >= Decimal("0.3")  # reserve hidden native-retrieval input too
    assert actual == Decimal("0.0000264")
    prose = deepseek(lambda r: httpx.Response(200, json={
        "content": [{"type": "text", "text": "See https://fixture.example/notice"}]
    }))
    out = asyncio.run(prose.search("SYNTHETIC", budget, time.monotonic() + 2))
    assert out.status == "unavailable" and out.reason == "native_search_block_missing"


def test_native_unknown_price_prevents_call_and_no_snippet_is_trusted() -> None:
    called: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(request)
        return httpx.Response(200, json={})

    provider = DeepSeekSearchProvider("SYNTHETIC-key", transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.search("SYNTHETIC", MemoryBudget(), time.monotonic() + 2))
    assert result.status == "not_configured" and not called


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "https://user:pass@fixture.example/", "http://fixture.example:8080/",
    "ftp://fixture.example/",
])
def test_page_url_guards(url: str) -> None:
    with pytest.raises(PageReadError):
        public_url(url)


@pytest.mark.parametrize("addresses", [
    ("127.0.0.1",), ("10.0.0.1",), ("169.254.169.254",), ("::1",), ("fc00::1",),
    ("93.184.216.34", "192.168.1.1"), ("224.0.0.1",), ("64:ff9b::7f00:1",),
])
def test_private_mixed_and_translation_dns_blocked(addresses: tuple[str, ...]) -> None:
    with pytest.raises(PageReadError):
        validated_addresses(addresses)


def test_reader_pins_address_strips_scripts_and_follows_guarded_redirects() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["Host"] == "fixture.example"
        assert request.extensions["sni_hostname"] == "fixture.example"
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, text="<h1>SYNTHETIC notice</h1><script>LEAK</script><p>body</p>",
                              headers={"content-type": "text/html; charset=utf-8"})

    page = asyncio.run(SafePageReader(httpx.MockTransport(handler), public_dns).read(
        SearchSource("https://fixture.example/start#1", "SYNTHETIC"), time.monotonic() + 2
    ))
    assert page.url == "https://fixture.example/final" and "LEAK" not in page.text
    assert "SYNTHETIC notice" in page.text and len(requests) == 2
    assert page.source_authority == "third_party"


def test_reader_blocks_redirect_to_metadata_and_body_limits() -> None:
    async def dns(host: str) -> tuple[str, ...]:
        return (host,) if host == "169.254.169.254" else ("93.184.216.34",)

    seen: list[str] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

    with pytest.raises(PageReadError, match="private"):
        asyncio.run(SafePageReader(httpx.MockTransport(redirect), dns).read(
            SearchSource("https://fixture.example/", "SYNTHETIC"), time.monotonic() + 2
        ))
    assert len(seen) == 1
    with pytest.raises(PageReadError, match="too_large"):
        asyncio.run(SafePageReader(httpx.MockTransport(lambda r: httpx.Response(
            200, text="x" * 101, headers={"content-type": "text/plain"}
        )), public_dns, max_bytes=100).read(
            SearchSource("https://fixture.example/", "SYNTHETIC"), time.monotonic() + 2
        ))


@dataclass
class FakeProvider:
    result: ProviderSearchResult
    delay: float = 0
    name: str = "synthetic"
    available: bool = True
    deadlines: list[float] = field(default_factory=list)

    async def search(self, query: str, budget: OnlineBudget, deadline: float,
                     max_uses: int = 1, max_pages: int = 3) -> ProviderSearchResult:
        self.deadlines.append(deadline)
        await asyncio.sleep(self.delay)
        return self.result


def test_flow_has_one_deadline_two_searches_three_pages_official_priority() -> None:
    primary = FakeProvider(ProviderSearchResult("unavailable"), delay=0.01)
    fallback = FakeProvider(ProviderSearchResult("success", tuple(
        SearchSource(u, "SYNTHETIC") for u in (
            "https://third.example/", "https://fixture.cdut.edu.cn/1",
            "https://fixture.cdut.edu.cn/2", "https://fixture.cdut.edu.cn/3",
        )
    )))
    read_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        read_hosts.append(request.headers["Host"])
        return httpx.Response(200, text="SYNTHETIC fetched page body",
                              headers={"content-type": "text/plain"})

    budget = MemoryBudget()
    service = WebEvidenceService(budget, primary, fallback,
                                SafePageReader(httpx.MockTransport(handler), public_dns))
    out = asyncio.run(service.search("SYNTHETIC campus question"))
    assert out.status == "success" and out.attempts == 2 and out.page_reads == 3
    assert primary.deadlines == fallback.deadlines
    assert all(h == "fixture.cdut.edu.cn" for h in read_hosts)
    assert budget.flows == 1 and len(out.as_tool_result()["hits"]) == 3  # type: ignore[arg-type]


def test_no_fetched_body_is_limited_not_success_and_timeout_stops_fallback() -> None:
    primary = FakeProvider(ProviderSearchResult("success", (
        SearchSource("https://fixture.example/", "SYNTHETIC"),
    )))
    reader = SafePageReader(httpx.MockTransport(lambda r: httpx.Response(403)), public_dns)
    out = asyncio.run(
        WebEvidenceService(MemoryBudget(), primary, reader=reader).search("SYNTHETIC")
    )
    assert out.status == "limited" and not out.pages
    slow = FakeProvider(ProviderSearchResult("unavailable"), delay=0.1)
    fallback = FakeProvider(ProviderSearchResult("empty"))
    out = asyncio.run(WebEvidenceService(MemoryBudget(), slow, fallback,
                                        timeout_seconds=0.02).search("SYNTHETIC"))
    assert out.status == "timeout" and not fallback.deadlines


def test_tavily_free_mode_explicit_and_basic_only() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"results": []})

    budget = MemoryBudget()
    provider = TavilySearchProvider("SYNTHETIC-key", transport=httpx.MockTransport(handler))
    out = asyncio.run(provider.search("SYNTHETIC", budget, time.monotonic() + 2))
    assert out.status == "not_configured" and not sent
    provider = TavilySearchProvider("SYNTHETIC-key", True, transport=httpx.MockTransport(handler))
    out = asyncio.run(provider.search("SYNTHETIC", budget, time.monotonic() + 2))
    assert out.status == "empty" and budget.credits == 1
    assert sent[0]["search_depth"] == "basic" and sent[0]["auto_parameters"] is False
    assert sent[0]["include_raw_content"] is True and sent[0]["max_results"] == 3


def test_native_body_blocked_uses_free_fallback_raw_body_with_three_page_cap() -> None:
    calls: list[dict[str, Any]] = []
    native = FakeProvider(ProviderSearchResult("success", tuple(
        SearchSource(f"https://fixture.cdut.edu.cn/{i}", "SYNTHETIC") for i in range(3)
    )))

    def fallback_reply(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        # A provider over-return is bounded by the requested remaining one-page budget.
        return httpx.Response(200, json={"results": [
            {"url": f"https://fixture.cdut.edu.cn/{i}", "title": "SYNTHETIC page",
             "raw_content": "<p>SYNTHETIC original document</p><script>INSTRUCTION</script>",
             "content": "GENERATED SNIPPET MUST NOT BECOME EVIDENCE"}
            for i in range(3)
        ]})

    fallback = TavilySearchProvider("SYNTHETIC-key", True,
                                    transport=httpx.MockTransport(fallback_reply))
    page_attempts: list[httpx.Request] = []

    def blocked_page(request: httpx.Request) -> httpx.Response:
        page_attempts.append(request)
        return httpx.Response(412)

    reader = SafePageReader(httpx.MockTransport(blocked_page), public_dns)
    budget = MemoryBudget()
    out = asyncio.run(WebEvidenceService(budget, native, fallback, reader).search("SYNTHETIC"))
    assert out.status == "success" and out.provider == "tavily" and out.attempts == 2
    assert out.page_reads == 3 and len(page_attempts) == 2 and len(out.pages) == 1
    assert calls[0]["max_results"] == 1 and calls[0]["include_raw_content"] is True
    page = out.pages[0]
    assert page.access_method == "provider_extraction"
    assert page.source_authority == "official_university"
    assert "SYNTHETIC original document" in page.text
    assert "INSTRUCTION" not in page.text and "GENERATED" not in page.text
    assert page.url == "https://fixture.cdut.edu.cn/0"  # same URL after failed native read
    assert budget.flows == 1 and budget.credits == 1


def test_provider_raw_body_missing_does_not_trust_content_or_generated_answer() -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "answer": "GENERATED ANSWER",
            "results": [{"url": "https://fixture.cdut.edu.cn/notice", "title": "SYNTHETIC",
                         "content": "GENERATED SNIPPET", "raw_content": None}],
        })

    provider = TavilySearchProvider("SYNTHETIC-key", True,
                                   transport=httpx.MockTransport(reply))

    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Extraction failure cannot exceed the reader budget by refetching")

    reader = SafePageReader(httpx.MockTransport(forbidden), public_dns)
    out = asyncio.run(
        WebEvidenceService(MemoryBudget(), provider, reader=reader).search("SYNTHETIC")
    )
    assert out.status == "limited" and out.page_reads == 1 and not out.pages


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://169.254.169.254/", "http://localhost/",
    "https://private.local/", "https://user:pass@fixture.cdut.edu.cn/",
])
def test_provider_extraction_private_reference_is_rejected(url: str) -> None:
    reader = SafePageReader()
    with pytest.raises(PageReadError):
        asyncio.run(reader.read(SearchSource(url, "SYNTHETIC", raw_content="SYNTHETIC",
                                             access_method="provider_extraction"),
                                time.monotonic() + 1))


def test_durable_budget_serializes_flow_and_money_reservations(tmp_path: Path) -> None:
    def attempt(i: int) -> bool:
        budget = OnlineBudget(tmp_path, Decimal("1"), 100, today="20261014", max_search_flows=5)
        try:
            budget.reserve_search_flow()
            ident = budget.reserve(Decimal("0.1"), "synthetic")
            budget.settle(ident, Decimal("0.01"))
            return True
        except BudgetExhausted:
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt, range(20)))
    assert sum(results) == 5
    report = OnlineBudget(tmp_path, Decimal("1"), 100, today="20261014").report()
    assert report["search_flows"] == 5 and Decimal(str(report["charged_usd"])) == Decimal("0.05")


def test_free_monthly_credits_survive_days(tmp_path: Path) -> None:
    budget = OnlineBudget(tmp_path, Decimal("1"), 100, today="20261014")
    budget.reserve_free_search_credit(1)
    with pytest.raises(BudgetExhausted, match="free_search"):
        OnlineBudget(tmp_path, Decimal("1"), 100, today="20261015").reserve_free_search_credit(1)
    OnlineBudget(tmp_path, Decimal("1"), 100, today="20261101").reserve_free_search_credit(1)


def jev_reply(sufficient: float, need: float = 0.9) -> dict[str, object]:
    return {"model": "typesafe/jev-1.13", "answers": {
        "answer_mode": {"type": "choice", "choice": "direct", "confidence": 0.9,
                        "probabilities": {"direct": 0.9, "generate": 0.05, "clarify": 0.05}},
        "search_needed": {"type": "noul", "noul": need},
        "sufficient": {"type": "noul", "noul": sufficient},
    }, "usage": {"input_tokens": 5, "output_tokens": 3}}


def test_jev_zero_hits_directory_and_web_evidence_separate_from_observations() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        state = json.loads(request.content)
        sent.append(state)
        return httpx.Response(200, json=jev_reply(0.9 if len(sent) == 2 else 0.1))

    client = JevShadowClient("SYNTHETIC-key", TokenPrice(Decimal("0.042"), Decimal("0")),
                             transport=httpx.MockTransport(handler))
    context = TurnEvidenceContext(task="SYNTHETIC location", directory_facts=({
        "name": "SYNTHETIC building", "source_authority": "map_provider",
        "coordinates": [104.123456, 30.123456],
    },), user_observations=("SYNTHETIC 403",))
    out = asyncio.run(client.evaluate("SYNTHETIC", (), public_fixture=False, online=True,
                                     budget=MemoryBudget(), evidence_context=context))
    assert out.status == "ok" and out.search_needed is True
    state = sent[0]["state"]["evidence_context"]
    assert "coordinates" not in json.dumps(state)
    assert state["user_observations"] == ["SYNTHETIC 403"]
    context = TurnEvidenceContext(task="SYNTHETIC", web_pages=(WebPageEvidence(
        "web:synthetic", "SYNTHETIC", "https://fixture.cdut.edu.cn/", "SYNTHETIC body",
        "official_university", "2026-10-14",
    ),), search_completed=True)
    out = asyncio.run(client.evaluate("SYNTHETIC", (), public_fixture=False, online=True,
                                     budget=MemoryBudget(), evidence_context=context))
    assert out.status == "ok" and out.sufficient_probability == 0.9


class FakeJudge:
    timeout_seconds = 0.1

    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, question: str, candidates: tuple[RetrievalHit, ...], *,
                       public_fixture: bool, budget: SpendBudget,
                       rule_summary: str = "", online: bool = False) -> ShadowResult:
        self.calls += 1
        return ShadowResult("ok", answer_mode="generate", search_needed=True,
                            sufficient_probability=0.1)


def test_jev_turn_two_actual_calls_and_stage_cache() -> None:
    fake = FakeJudge()
    turn = JevPlugin(fake, MemoryBudget(), "on").turn()

    async def run() -> None:
        first = await turn.assess("SYNTHETIC", ())
        cached = await turn.assess("SYNTHETIC", ())
        assert first is cached and first.search_needed is True
        await turn.assess("SYNTHETIC", (), stage="after_search")
        limited = await turn.assess("SYNTHETIC other", ())
        assert limited.reason == "turn_judge_limit"

    asyncio.run(run())
    assert fake.calls == 2
    unsure = combine(ShadowResult("unsure", search_needed=True), "unassessed", ())
    assert unsure.search_needed is None
