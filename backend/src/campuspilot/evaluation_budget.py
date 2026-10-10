"""Durable conservative reservations shared by all external calls in one stage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from campuspilot.knowledge_release import atomic_write, publication_lock
from campuspilot.rag import canonical


class BudgetExhausted(Exception):
    pass


@dataclass(frozen=True)
class TokenPrice:
    input_per_million: Decimal
    output_per_million: Decimal

    def __post_init__(self) -> None:
        if any(
            not p.is_finite() or p < 0 for p in (self.input_per_million, self.output_per_million)
        ):
            raise ValueError("Token prices must be known, finite and nonnegative")

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Invalid token usage")
        return (
            input_tokens * self.input_per_million + output_tokens * self.output_per_million
        ) / 1_000_000


class EvaluationBudget:
    def __init__(self, directory: Path, stage: str) -> None:
        if stage not in {"phase1", "phase2"}:
            raise ValueError("Invalid evaluation stage")
        self.root = directory / stage
        self.path = self.root / "budget.json"

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {
                "schema_version": 1,
                "limit_usd": "5",
                "max_calls": 1000,
                "calls": 0,
                "charged_usd": "0",
                "reservations": {},
            }
        result = json.loads(self.path.read_bytes())
        if result.get("limit_usd") != "5" or result.get("max_calls") != 1000:
            raise ValueError("Evaluation ledger limits were changed")
        return dict(result)

    def reserve(self, maximum_cost: Decimal, label: str) -> str:
        if not maximum_cost.is_finite() or maximum_cost < 0:
            raise ValueError("Unknown external request price")
        with publication_lock(self.root):
            data = self._read()
            charged = Decimal(str(data["charged_usd"]))
            calls = int(str(data["calls"]))
            if charged + maximum_cost > Decimal("5") or calls >= 1000:
                raise BudgetExhausted("stage_evaluation_budget_exhausted")
            ident = str(uuid4())
            reservations = data["reservations"]
            if not isinstance(reservations, dict):
                raise ValueError("Invalid evaluation ledger")
            reservations[ident] = {
                "maximum_usd": str(maximum_cost),
                "label": label,
                "status": "reserved",
            }
            data["charged_usd"] = str(charged + maximum_cost)
            data["calls"] = calls + 1
            atomic_write(self.path, canonical(data))
            return ident

    def settle(self, ident: str, actual_cost: Decimal | None) -> None:
        # Timeout/missing usage stays charged at the maximum, including interrupted runs.
        with publication_lock(self.root):
            data = self._read()
            reservations = data["reservations"]
            if not isinstance(reservations, dict):
                raise ValueError("Invalid evaluation ledger")
            item = reservations[ident]
            if not isinstance(item, dict) or item["status"] != "reserved":
                raise ValueError("Reservation already settled")
            maximum = Decimal(item["maximum_usd"])
            if actual_cost is None:
                item["status"] = "usage_unknown"
            else:
                if not actual_cost.is_finite() or actual_cost < 0:
                    raise ValueError("Invalid settlement")
                item["status"] = "settled"
                item["actual_usd"] = str(actual_cost)
                data["charged_usd"] = str(Decimal(str(data["charged_usd"])) - maximum + actual_cost)
            atomic_write(self.path, canonical(data))
            if actual_cost is not None and actual_cost > maximum:
                raise BudgetExhausted("provider_usage_exceeded_reservation")

    def report(self) -> dict[str, object]:
        return self._read()
