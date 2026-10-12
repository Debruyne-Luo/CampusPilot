"""Synthetic HTTP responses verify complete-API isolation and paid-call accounting."""

import asyncio
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from campuspilot.api_evaluation import PublicAPICollector
from campuspilot.evaluation_budget import EvaluationBudget, TokenPrice
from campuspilot.migration_eval import load_cases

ROOT = Path(__file__).resolve().parents[1]


def collector(tmp_path: Path, price: str = "0.1") -> PublicAPICollector:
    def reply(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("reset"):
            return httpx.Response(
                200,
                json={"runtime_mode": "phase2"},
                headers={"Set-Cookie": "campuspilot_session=SYNTHETIC; Path=/"},
            )
        assert request.headers["cookie"] == "campuspilot_session=SYNTHETIC"
        return httpx.Response(
            200,
            json={
                "answer": "SYNTHETIC complete API answer",
                "request_id": "SYNTHETIC",
                "result_status": "success",
                "services": [],
                "teachers": [],
                "places": [],
            },
        )

    return PublicAPICollector(
        "https://example.com",
        "phase2",
        EvaluationBudget(tmp_path, "phase2"),
        TokenPrice(Decimal(price), Decimal(price)),
        1000,
        700,
        1,
        transport=httpx.MockTransport(reply),
    )


def test_api_answers_keep_fixed_case_identity_and_charge_unknown_usage(tmp_path: Path) -> None:
    client = collector(tmp_path)
    cases = load_cases(ROOT / "evaluation/runtime-migration")[:2]
    report = asyncio.run(client.answers(cases))
    assert report["collection_complete"] and len(report["cases"]) == 2
    assert report["cases"][0]["case_id"] == cases[0].case_id
    assert report["cases"][0]["response"]["request_id"] == "SYNTHETIC"
    budget = client.budget.report()
    assert budget["calls"] == 2 and Decimal(str(budget["charged_usd"])) > 0


def test_exhausted_budget_returns_partial_evidence_without_model_request(tmp_path: Path) -> None:
    client = collector(tmp_path, price="100000")
    cases = load_cases(ROOT / "evaluation/runtime-migration")[:2]
    report = asyncio.run(client.answers(cases))
    assert report["budget_exhausted"] and not report["collection_complete"]
    assert not report["cases"] and client.budget.report()["calls"] == 0


def test_cold_timing_restarts_before_each_concurrent_pair(tmp_path: Path) -> None:
    client = collector(tmp_path)
    restarts = []
    report = asyncio.run(
        client.timing("SYNTHETIC fixed question", 100, cold_restart=lambda: restarts.append(True))
    )
    assert len(restarts) == 50 and report["valid_samples"] == 100
    assert client.budget.report()["calls"] == 100


def test_private_question_cannot_be_sent_to_api_evaluator(tmp_path: Path) -> None:
    client = collector(tmp_path)

    async def run() -> None:
        async with client.client() as http:
            with pytest.raises(ValueError):
                await client.ask(http, "密码是SYNTHETIC_SECRET")

    asyncio.run(run())
    assert client.budget.report()["calls"] == 0
