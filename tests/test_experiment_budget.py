from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from campuspilot.evaluation_budget import BudgetExhausted, TokenPrice
from campuspilot.experiment_budget import CampaignBudget, ExperimentGateway, MeteredProvider


def test_campaign_does_not_reset_with_new_instance_and_unknown_usage(tmp_path: Path) -> None:
    budget = CampaignBudget(tmp_path)
    reservation = budget.reserve(Decimal(19), "unknown")
    budget.settle(reservation, None)
    another = CampaignBudget(tmp_path)
    with pytest.raises(BudgetExhausted):
        another.reserve(Decimal(2), "over")
    assert another.report()["charged_usd"] == "19"


def test_gateway_requires_known_model_and_meters_every_request(tmp_path: Path) -> None:
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"choices": [], "usage": {"prompt_tokens": 20, "completion_tokens": 10}}
        )

    budget = CampaignBudget(tmp_path)
    provider = MeteredProvider(
        "https://api.deepseek.com/chat/completions",
        "deepseek-flash",
        "synthetic-private-key",
        TokenPrice(Decimal("0.3"), Decimal("1.2")),
    )
    gateway = ExperimentGateway(
        budget, {"/v1/chat/completions": provider}, transport=httpx.MockTransport(respond)
    )
    assert gateway.dispatch("/v1/chat/completions", {"model": "other"})[0] == 400
    assert not seen
    assert gateway.dispatch("/v1/chat/completions", {"model": "deepseek-flash"})[0] == 200
    assert budget.report()["calls"] == 1
    assert Decimal(str(budget.report()["charged_usd"])) == Decimal("0.000018")
    assert b"synthetic-private-key" not in budget.path.read_bytes()


def test_gateway_budget_stops_transmission(tmp_path: Path) -> None:
    budget = CampaignBudget(tmp_path)
    budget.reserve(Decimal(20), "previous")
    provider = MeteredProvider(
        "https://api.deepseek.com/chat/completions",
        "deepseek-flash",
        "fake",
        TokenPrice(Decimal(1), Decimal(1)),
    )
    gateway = ExperimentGateway(
        budget,
        {"/v1/chat/completions": provider},
        transport=httpx.MockTransport(lambda _: pytest.fail("must not call")),
    )
    assert gateway.dispatch("/v1/chat/completions", {"model": "deepseek-flash"})[0] == 402
    assert gateway.failure is not None
    assert gateway.failure["reason"] == "campaign_budget_exhausted"
    assert gateway.dispatch("/v1/chat/completions", {"model": "deepseek-flash"})[0] == 503


def test_invalid_usage_cost_retains_reservation(tmp_path: Path) -> None:
    budget = CampaignBudget(tmp_path)
    provider = MeteredProvider(
        "https://api.deepseek.com/chat/completions",
        "deepseek-flash",
        "fake",
        TokenPrice(Decimal("0.3"), Decimal("1.2")),
    )
    gateway = ExperimentGateway(
        budget,
        {"/v1/chat/completions": provider},
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": "NaN"}}
            )
        ),
    )
    assert gateway.dispatch("/v1/chat/completions", {"model": "deepseek-flash"})[0] == 502
    assert Decimal(str(budget.report()["charged_usd"])) > Decimal("0.004")


def test_provider_failure_stops_further_paid_transmission(tmp_path: Path) -> None:
    sent = []

    def unavailable(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(503, json={"error": {"message": "synthetic outage"}})

    provider = MeteredProvider(
        "https://api.deepseek.com/chat/completions",
        "deepseek-flash",
        "fake",
        TokenPrice(Decimal("0.3"), Decimal("1.2")),
    )
    gateway = ExperimentGateway(
        CampaignBudget(tmp_path),
        {"/v1/chat/completions": provider},
        transport=httpx.MockTransport(unavailable),
    )
    assert gateway.dispatch("/v1/chat/completions", {"model": "deepseek-flash"})[0] == 503
    assert gateway.dispatch("/v1/chat/completions", {"model": "deepseek-flash"})[0] == 503
    assert len(sent) == 1
