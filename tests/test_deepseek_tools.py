"""Standalone Search/Fetch contracts; all HTTP responses are synthetic."""

import asyncio
import json
import time
from decimal import Decimal

import httpx
import pytest
from campuspilot.evaluation_budget import BudgetExhausted
from campuspilot.web_evidence import (
    DeepSeekToolsProvider,
    SafePageReader,
    TurnEvidenceContext,
    WebEvidenceService,
    campus_page_matches,
)
from pydantic import JsonValue
from test_web_evidence import MemoryBudget


def test_search_body_avoids_fetch_and_generated_summary_is_not_evidence() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        payload = json.loads(request.content)
        assert request.headers['authorization'] == 'Bearer SYNTHETIC-key'
        assert payload['need_content'] is True
        assert len(payload['query']) <= 128
        return httpx.Response(200, json={'results': [{
            'url': 'https://www.cdut.edu.cn/SYNTHETIC-guide', 'title': 'SYNTHETIC Guide',
            'content': 'SYNTHETIC original page body.', 'summary': 'SYNTHETIC invented summary',
        }]})

    budget = MemoryBudget()
    provider = DeepSeekToolsProvider('SYNTHETIC-key', transport=httpx.MockTransport(handler))
    body = asyncio.run(WebEvidenceService(budget, provider).search('SYNTHETIC ' * 30))
    assert calls == ['/v1/tools/search']
    assert body.status == 'success' and body.page_reads == 1
    assert body.pages[0].text == 'SYNTHETIC original page body.'
    assert body.pages[0].access_method == 'provider_extraction'
    assert list(budget.items.values()) == [(Decimal('0.00075'), Decimal('0.00075'))]


def test_fetch_only_missing_bodies_with_three_page_bound() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith('/search'):
            return httpx.Response(200, json={'results': [
                {'url': f'https://www.cdut.edu.cn/SYNTHETIC-{i}', 'title': 'SYNTHETIC',
                 'summary': 'SYNTHETIC summary only'} for i in range(7)
            ]})
        return httpx.Response(200, json={'title': 'SYNTHETIC', 'content': 'SYNTHETIC fetched body'})

    budget = MemoryBudget()
    provider = DeepSeekToolsProvider('SYNTHETIC-key', transport=httpx.MockTransport(handler))
    result = asyncio.run(WebEvidenceService(budget, provider).search('SYNTHETIC'))
    assert result.status == 'success' and len(result.pages) == 3 and result.page_reads == 3
    assert calls.count('/v1/tools/search') == 1 and calls.count('/v1/tools/fetch') == 3
    assert len(budget.items) == 4


@pytest.mark.parametrize('status', [401, 402, 403, 404, 429, 500, 504])
def test_error_does_not_become_success_or_optimistic_refund(status: int) -> None:
    budget = MemoryBudget()
    provider = DeepSeekToolsProvider('SYNTHETIC-key', transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json={'error': {'message': 'SYNTHETIC'}})
    ))
    result = asyncio.run(provider.search('SYNTHETIC', budget, time.monotonic() + 2))
    assert result.status != 'success' and not result.sources
    # An explicit non-200 response is not billable per the official contract.
    assert list(budget.items.values()) == [(Decimal('0.00075'), Decimal('0'))]


def test_empty_result_is_free_and_private_fetch_targets_never_sent() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={'results': [
            {'url': 'http://127.0.0.1/SYNTHETIC', 'summary': 'SYNTHETIC'},
            {'url': 'https://host.internal/SYNTHETIC', 'summary': 'SYNTHETIC'},
        ]})

    budget = MemoryBudget()
    provider = DeepSeekToolsProvider('SYNTHETIC-key', transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.search('SYNTHETIC', budget, time.monotonic() + 2))
    assert not result.sources and calls == ['/v1/tools/search']
    empty_budget = MemoryBudget()
    provider = DeepSeekToolsProvider('SYNTHETIC-key', transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'results': []})
    ))
    result = asyncio.run(provider.search('SYNTHETIC', empty_budget, time.monotonic() + 2))
    assert result.status == 'empty' and list(empty_budget.items.values())[0][1] == 0


def test_provider_content_still_rejects_protection_page() -> None:
    source_provider = DeepSeekToolsProvider('SYNTHETIC-key', transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'results': [{
            'url': 'https://www.cdut.edu.cn/SYNTHETIC', 'content': 'Verify you are human',
        }]})
    ))
    result = asyncio.run(WebEvidenceService(
        MemoryBudget(), source_provider, reader=SafePageReader(),
    ).search('SYNTHETIC'))
    assert result.status == 'limited' and not result.pages


def test_a_slow_fetch_cannot_discard_a_search_body_at_the_shared_deadline() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/search'):
            return httpx.Response(200, json={'results': [
                {'url': 'https://www.cdut.edu.cn/SYNTHETIC-ready',
                 'content': 'SYNTHETIC complete body'},
                {'url': 'https://www.cdut.edu.cn/SYNTHETIC-slow'},
            ]})
        await asyncio.sleep(1)
        return httpx.Response(200, json={'content': 'SYNTHETIC too late'})

    result = asyncio.run(WebEvidenceService(
        MemoryBudget(), DeepSeekToolsProvider('SYNTHETIC-key',
                                              transport=httpx.MockTransport(handler)),
        timeout_seconds=.1,
    ).search('SYNTHETIC'))
    assert result.status == 'success' and len(result.pages) == 1
    assert result.pages[0].text == 'SYNTHETIC complete body'
    assert result.latency_ms < 300


def test_fetch_budget_failure_preserves_an_already_available_body() -> None:
    class OneRequestBudget(MemoryBudget):
        def reserve(self, maximum_cost: Decimal, label: str) -> str:
            if self.items:
                raise BudgetExhausted('SYNTHETIC budget')
            return super().reserve(maximum_cost, label)

    provider = DeepSeekToolsProvider('SYNTHETIC-key', transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'results': [
            {'url': 'https://www.cdut.edu.cn/SYNTHETIC-ready', 'content': 'SYNTHETIC body'},
            {'url': 'https://www.cdut.edu.cn/SYNTHETIC-needs-fetch'},
        ]})
    ))
    result = asyncio.run(provider.search('SYNTHETIC', OneRequestBudget(), time.monotonic() + 2))
    assert result.status == 'success' and len(result.sources) == 1


@pytest.mark.parametrize('url,content', [
    ('https://www.cdut.edu.cn/ssjgy.jsp?newskeycode2=SYNTHETIC',
     'SYNTHETIC search results with incomplete snippets'),
    ('https://www.cdut.edu.cn/SYNTHETIC-long', 'SYNTHETIC body ' * 700),
], ids=['search-index', 'over-budget-body'])
def test_index_and_truncated_bodies_are_not_policy_evidence(url: str, content: str) -> None:
    provider = DeepSeekToolsProvider('SYNTHETIC-key', transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'results': [{'url': url, 'content': content}]})
    ))
    result = asyncio.run(WebEvidenceService(MemoryBudget(), provider).search('SYNTHETIC'))
    assert not result.pages and result.status == 'limited'


def test_web_evidence_keeps_explicit_campus_and_audience_constraints() -> None:
    url = 'https://yb.cdut.edu.cn/info/SYNTHETIC.htm'
    assert not campus_page_matches(url, 'chengdu')
    assert campus_page_matches(url, 'yibin') and campus_page_matches(url, 'all')
    scope: dict[str, JsonValue] = {
        'campus': 'chengdu', 'audience': 'undergraduate', 'academic_year': '2026-2027',
    }
    assert TurnEvidenceContext(retrieval_scope=scope).as_state()['retrieval_scope'] == scope
