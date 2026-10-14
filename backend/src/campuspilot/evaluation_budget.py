"""Durable conservative reservations shared by all external calls in one stage."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol
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


class SpendBudget(Protocol):
    """Reserve-then-settle spend control shared by the eval ledger and the online budget."""

    def reserve(self, maximum_cost: Decimal, label: str) -> str: ...

    def settle(self, ident: str, actual_cost: Decimal | None) -> None: ...


class OnlineBudget:
    """Durable per-UTC-day ledger for online (CAMPUSPILOT_JEV) calls, separate from the
    fixed $5 evaluation ledger. Same conservative reserve/settle rules: unknown usage stays
    charged at the reservation maximum; exceeding a limit raises BudgetExhausted.
    """

    def __init__(
        self,
        directory: Path,
        limit_usd: Decimal,
        max_calls: int,
        today: str | None = None,
        max_search_flows: int = 100,
    ) -> None:
        if (
            not limit_usd.is_finite()
            or limit_usd <= 0
            or max_calls <= 0
            or max_search_flows <= 0
        ):
            raise ValueError("Invalid online budget limits")
        self.root = directory / "online"
        self.limit_usd, self.max_calls = limit_usd, max_calls
        self._today = today
        self.max_search_flows = max_search_flows

    @contextmanager
    def _lock(self) -> Iterator[None]:
        """Serialize concurrent workers without silently dropping a reservation."""
        deadline = time.monotonic() + 2
        while True:
            stack = ExitStack()
            try:
                stack.enter_context(publication_lock(self.root))
            except (FileExistsError, PermissionError):
                # Windows may return EACCES rather than EEXIST for a lock file
                # another worker is opening/removing. The retry remains bounded.
                stack.close()
                if time.monotonic() >= deadline:
                    raise BudgetExhausted("online_budget_busy") from None
                time.sleep(0.01)
                continue
            with stack:
                yield
            return

    @property
    def path(self) -> Path:
        day = self._today or datetime.now(UTC).strftime("%Y%m%d")
        return self.root / f"budget-{day}.json"

    def _read(self, path: Path) -> dict[str, object]:
        if not path.exists():
            return {
                "schema_version": 1,
                "calls": 0,
                "search_flows": 0,
                "charged_usd": "0",
                "reservations": {},
            }
        return dict(json.loads(path.read_bytes()))

    def reserve(self, maximum_cost: Decimal, label: str) -> str:
        if not maximum_cost.is_finite() or maximum_cost < 0:
            raise ValueError("Unknown external request price")
        path = self.path
        with self._lock():
            data = self._read(path)
            charged = Decimal(str(data["charged_usd"]))
            calls = int(str(data["calls"]))
            if charged + maximum_cost > self.limit_usd or calls >= self.max_calls:
                raise BudgetExhausted("online_budget_exhausted")
            ident = path.stem + ":" + str(uuid4())
            reservations = data["reservations"]
            assert isinstance(reservations, dict)
            reservations[ident] = {
                "maximum_usd": str(maximum_cost),
                "label": label,
                "status": "reserved",
            }
            data["charged_usd"] = str(charged + maximum_cost)
            data["calls"] = calls + 1
            atomic_write(path, canonical(data))
            return ident

    def settle(self, ident: str, actual_cost: Decimal | None) -> None:
        path = self.root / (ident.split(":", 1)[0] + ".json")
        with self._lock():
            data = self._read(path)
            reservations = data["reservations"]
            assert isinstance(reservations, dict)
            item = reservations[ident]
            if item["status"] != "reserved":
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
            atomic_write(path, canonical(data))
            if actual_cost is not None and actual_cost > maximum:
                raise BudgetExhausted("provider_usage_exceeded_reservation")

    def report(self) -> dict[str, object]:
        return self._read(self.path)

    def reserve_search_flow(self) -> str:
        """Count a turn's single web flow separately from Jev/provider request calls.

        The slot remains consumed on timeout/failure, preventing unlimited free retries.
        Dollar reservations are made separately for each actual provider call.
        """
        path = self.path
        with self._lock():
            data = self._read(path)
            flows = int(str(data.get("search_flows", 0)))
            if flows >= self.max_search_flows:
                raise BudgetExhausted("online_search_flow_exhausted")
            data["search_flows"] = flows + 1
            atomic_write(path, canonical(data))
        return path.stem + ":flow:" + str(uuid4())

    def reserve_free_search_credit(self, monthly_limit: int = 1000) -> None:
        """Conservative local Tavily basic-credit cap; account free mode is also required."""
        if not 0 < monthly_limit <= 1000:
            raise ValueError("Free search allowance must not exceed 1000 monthly credits")
        month = (self._today or datetime.now(UTC).strftime("%Y%m%d"))[:6]
        path = self.root / f"free-search-{month}.json"
        with self._lock():
            data = dict(json.loads(path.read_bytes())) if path.exists() else {"credits": 0}
            credits = int(str(data["credits"]))
            if credits >= monthly_limit:
                raise BudgetExhausted("free_search_credit_exhausted")
            data["credits"] = credits + 1
            atomic_write(path, canonical(data))
