"""Synthetic native-search block parsing and conservative cache-usage settlement."""

import asyncio
import time
from decimal import Decimal
from typing import Any

import httpx
import pytest
from campuspilot.web_evidence import ProviderSearchResult
from test_web_evidence import MemoryBudget, deepseek, native_reply

SOURCE = "https://synthetic.invalid/__SYNTHETIC_native_search_fixture__"
TOOL_ERROR = {"type": "web_search_tool_result_error", "error_code": "max_uses_exceeded"}


def search(raw: dict[str, Any]) -> tuple[ProviderSearchResult, MemoryBudget]:
    budget = MemoryBudget()
    provider = deepseek(lambda request: httpx.Response(200, json=raw))
    result = asyncio.run(provider.search("SYNTHETIC fixture query", budget, time.monotonic() + 2))
    return result, budget


@pytest.mark.parametrize("list_error", [False, True], ids=["dict-error", "list-error"])
@pytest.mark.parametrize("error_first", [False, True], ids=["success-first", "error-first"])
def test_native_search_preserves_sources_across_independent_tool_error_blocks(
    list_error: bool, error_first: bool
) -> None:
    raw = native_reply(SOURCE)
    error = {
        "type": "web_search_tool_result",
        "content": [TOOL_ERROR] if list_error else TOOL_ERROR,
    }
    blocks = raw["content"]
    assert isinstance(blocks, list)
    raw["content"] = [error, *blocks] if error_first else [*blocks, error]

    result, budget = search(raw)

    assert result.status == "success"
    assert [source.url for source in result.sources] == [SOURCE]
    assert budget.items["0"][1] == Decimal("0.0000264")


@pytest.mark.parametrize("list_error", [False, True], ids=["dict-error", "list-error"])
def test_native_search_error_only_is_unavailable_instead_of_empty(list_error: bool) -> None:
    raw: dict[str, Any] = {
        "content": [{
            "type": "web_search_tool_result",
            "content": [TOOL_ERROR] if list_error else TOOL_ERROR,
        }],
        "usage": {"input_tokens": 40, "output_tokens": 12},
    }

    result, _ = search(raw)

    assert result.status == "unavailable"
    assert result.reason == "native_search_tool_error"
    assert result.sources == ()


@pytest.mark.parametrize(
    ("cache_usage", "expected_actual"),
    [
        ({"cache_read_input_tokens": 60}, "0.0000444"),
        ({"cache_creation_input_tokens": 60}, "0.0000444"),
        ({"cache_read_input_tokens": 60, "cache_creation_input_tokens": 20}, "0.0000504"),
        ({"cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}, "0.0000264"),
    ],
    ids=["cache-read", "cache-creation", "both", "explicit-zero"],
)
def test_native_search_charges_cache_usage_at_conservative_input_price(
    cache_usage: dict[str, int], expected_actual: str
) -> None:
    raw = native_reply(SOURCE)
    raw["usage"] = {"input_tokens": 40, "output_tokens": 12, **cache_usage}

    result, budget = search(raw)

    assert result.status == "success"
    maximum, actual = budget.items["0"]
    assert actual == Decimal(expected_actual)
    assert actual <= maximum


@pytest.mark.parametrize("field", ["cache_read_input_tokens", "cache_creation_input_tokens"])
@pytest.mark.parametrize("invalid", [-1, "60", None, True, {}, 1.5])
def test_native_search_malformed_cache_usage_retains_reservation(
    field: str, invalid: Any
) -> None:
    raw = native_reply(SOURCE)
    raw["usage"] = {"input_tokens": 40, "output_tokens": 12, field: invalid}

    _, budget = search(raw)

    maximum, actual = budget.items["0"]
    assert maximum > Decimal("0")
    assert actual is None  # Invalid or unknown usage never earns an optimistic refund.
