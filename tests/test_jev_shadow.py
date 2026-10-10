"""Shadow transport and durable spend limits; never calls a real provider."""

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from campuspilot.evaluation_budget import BudgetExhausted, EvaluationBudget, TokenPrice
from campuspilot.jev_shadow import OPENROUTER_ENDPOINT, JevShadowClient
from campuspilot.migration_config import price, secret
from campuspilot.rag import KnowledgeSnapshot, LexicalRetriever, RetrievalFilters, canonical

DATA = Path(__file__).resolve().parents[1] / "data/cdut/rag/bootstrap.json"
KEY = "SYNTHETIC-openrouter-test-key"
PRICE = TokenPrice(Decimal("0.042"), Decimal("0"))


@pytest.mark.parametrize(
    "fault", ["none", "choice", "probabilities", "score", "low_confidence", "usage", "timeout"]
)
def test_jev_uses_decisions_api_closed_choices_and_falls_back(fault: str, tmp_path: Path) -> None:
    original = KnowledgeSnapshot.model_validate_json(DATA.read_bytes())
    hits = LexicalRetriever(original).search(
        "学生邮箱激活", RetrievalFilters(today=date(2026, 10, 10))
    )
    assert hits
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == OPENROUTER_ENDPOINT
        calls.append(json.loads(request.content))
        if fault == "timeout":
            raise httpx.ReadTimeout(KEY)
        answers: dict[str, object] = {
            "answer_mode": {
                "type": "choice",
                "choice": "generate",
                "confidence": 0.9,
                "probabilities": {"direct": 0.05, "generate": 0.9, "clarify": 0.05},
            },
            "search_needed": {"type": "noul", "noul": 0.1},
            "sufficient": {"type": "noul", "noul": 0.9},
        }
        for i in range(len(hits)):
            answers[f"rank_{i}"] = {
                "type": "score",
                "score": 2,
                "confidence": 1,
                "probabilities": {"0": 0, "1": 0, "2": 1},
            }
        data = json.loads(canonical(answers))
        if fault == "choice":
            data["answer_mode"]["choice"] = "SYNTHETIC execute_tool"
        elif fault == "probabilities":
            data["answer_mode"]["probabilities"] = {}
        elif fault == "score":
            data["rank_0"]["score"] = 0.5
        elif fault == "low_confidence":
            data["answer_mode"]["confidence"] = 0.2
        raw = {
            "model": "typesafe/jev-1.13-SYNTHETIC-version",
            "answers": data,
            "usage": {"input_tokens": 100, "output_tokens": 40, "cost": 0.0000042},
        }
        if fault == "usage":
            del raw["usage"]
        return httpx.Response(200, json=raw)

    budget = EvaluationBudget(tmp_path, "phase2")
    client = JevShadowClient(KEY, PRICE, transport=httpx.MockTransport(handler))
    result = asyncio.run(client.evaluate("学生邮箱激活", hits, public_fixture=True, budget=budget))
    assert KEY not in repr(client) and len(calls) == 1
    assert calls[0]["model"] == "typesafe/jev-1.13"
    if fault == "none":
        assert result.status == "ok" and result.answer_mode == "generate"
        assert set(result.selected_ids) <= {h.chunk.chunk_id for h in hits}
    elif fault == "low_confidence":
        assert result.status == "unsure" and result.answer_mode == "unknown"
    else:
        assert result.status == "unknown"
    if fault != "none":
        assert result.selected_ids == tuple(h.chunk.chunk_id for h in hits[:4])
    assert budget.report()["calls"] == 1
    assert Decimal(str(budget.report()["charged_usd"])) > 0


def test_private_or_live_input_is_never_sent_to_shadow(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("No real conversations or coordinates may be sent to Jev")

    client = JevShadowClient(KEY, PRICE, transport=httpx.MockTransport(handler))
    budget = EvaluationBudget(tmp_path, "phase1")
    a = asyncio.run(client.evaluate("104.123456,30.123456", (), public_fixture=True, budget=budget))
    b = asyncio.run(
        client.evaluate("SYNTHETIC live request", (), public_fixture=False, budget=budget)
    )
    assert a.status == b.status == "unknown" and budget.report()["calls"] == 0


def test_budget_caps_dollars_and_requests_and_persists_unknown_usage(tmp_path: Path) -> None:
    budget = EvaluationBudget(tmp_path, "phase1")
    reservation = budget.reserve(Decimal("4.99"), "SYNTHETIC model")
    budget.settle(reservation, None)
    restarted = EvaluationBudget(tmp_path, "phase1")
    with pytest.raises(BudgetExhausted):
        restarted.reserve(Decimal("0.02"), "SYNTHETIC jev")
    assert restarted.report()["charged_usd"] == "4.99"
    # Use a separate phase to check the request ceiling without performing 1,000 I/O cycles.
    second = EvaluationBudget(tmp_path, "phase2")
    data = second.report()
    data["calls"] = 1000
    second.root.mkdir(parents=True)
    second.path.write_bytes(canonical(data))
    with pytest.raises(BudgetExhausted):
        second.reserve(Decimal("0"), "SYNTHETIC no cost")


def test_unknown_price_and_repository_credentials_fail_before_external_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in ("SYNTHETIC_INPUT_USD_PER_MILLION", "SYNTHETIC_OUTPUT_USD_PER_MILLION"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError):
        price("SYNTHETIC")
    file = tmp_path / "key.txt"
    file.write_text(KEY, encoding="utf-8")
    monkeypatch.setenv("SYNTHETIC_KEY_FILE", str(file))
    with pytest.raises(ValueError, match="outside"):
        secret("SYNTHETIC")
    monkeypatch.delenv("SYNTHETIC_KEY_FILE")
    monkeypatch.setenv("SYNTHETIC_API_KEY", KEY)
    assert secret("SYNTHETIC") == KEY
    monkeypatch.setenv("SYNTHETIC_KEY_FILE", str(file))
    with pytest.raises(ValueError):
        secret("SYNTHETIC")
