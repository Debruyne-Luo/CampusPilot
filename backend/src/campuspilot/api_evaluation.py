"""Complete API measurements on fixed public fixtures, with conservative paid-call caps."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from campuspilot.chat_runtime import public_input
from campuspilot.evaluation_budget import BudgetExhausted, EvaluationBudget, TokenPrice
from campuspilot.migration_eval import GoldenCase, percentile95


@dataclass(frozen=True)
class PublicAPICollector:
    base_url: str
    stage: str
    budget: EvaluationBudget
    price: TokenPrice
    max_input_tokens: int
    max_output_tokens: int
    max_inferences_per_request: int
    transport: httpx.AsyncBaseTransport | None = None

    def __post_init__(self) -> None:
        url = urlsplit(self.base_url)
        local = url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost", "::1"}
        if (
            not (url.scheme == "https" or local)
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
            or self.stage not in {"phase1", "phase2", "legacy"}
            or not 1 <= self.max_inferences_per_request <= 8
            or not 1 <= self.max_input_tokens <= 1_000_000
            or not 700 <= self.max_output_tokens <= 100_000
        ):
            raise ValueError("Invalid test endpoint or inference upper bounds")

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url.rstrip("/"),
            headers={"Origin": self.base_url.rstrip("/"), "X-CampusPilot-Request": "1"},
            timeout=20,
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
        )

    async def start(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/session/reset")
        value = response.json()
        if response.status_code != 200 or value.get("runtime_mode", "legacy") != self.stage:
            raise ValueError("Test service does not match the selected runtime")

    async def ask(self, client: httpx.AsyncClient, question: str) -> dict[str, Any]:
        if not public_input(question):
            raise ValueError("Only fixed public questions may enter evaluation")
        reservations = []
        # A client cannot see backend/provider usage. Reserve a verified upper bound;
        # unknown usage remains charged, so errors or process restarts cannot free budget.
        quote = self.price.cost(self.max_input_tokens, self.max_output_tokens)
        for _ in range(self.max_inferences_per_request):
            reservations.append(self.budget.reserve(quote, "complete_API_potential_inference"))
        started = time.perf_counter()
        try:
            response = await client.post("/api/chat", json={"message": question})
            if len(response.content) > 2_000_000:
                raise ValueError("Oversize test response")
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError("Invalid test response")
            return {
                "response": value,
                "http_status": response.status_code,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "transport_valid": response.status_code == 200 and bool(value.get("request_id")),
                "task_judgment": "PENDING_INDEPENDENT_LABEL_REVIEW",
            }
        finally:
            for reservation in reservations:
                self.budget.settle(reservation, None)

    async def answers(
        self,
        cases: tuple[GoldenCase, ...],
        progress: Callable[[list[dict[str, Any]]], None] | None = None,
    ) -> dict[str, Any]:
        queue = list(cases)
        outputs: list[dict[str, Any]] = []
        stopped = False

        async def worker() -> None:
            nonlocal stopped
            async with self.client() as client:
                while queue and not stopped:
                    case = queue.pop(0)
                    await self.start(client)
                    try:
                        prefix = [await self.ask(client, text) for text in case.messages]
                        result = await self.ask(client, case.question)
                    except BudgetExhausted:
                        stopped = True
                        return
                    outputs.append(
                        {
                            "case_id": case.case_id,
                            "split": case.split,
                            "group": case.group,
                            "prefix_responses": prefix,
                            **result,
                        }
                    )
                    if progress:
                        progress(outputs)

        await asyncio.gather(worker(), worker())
        return {
            "schema_version": 1,
            "mode": "api_live",
            "stage": self.stage,
            "concurrency": 2,
            "cases": sorted(outputs, key=lambda r: r["case_id"]),
            "collection_complete": not stopped and len(outputs) == len(cases),
            "budget_exhausted": stopped,
            "budget": self.budget.report(),
            "budget_accounting": "conservative_upper_bound; backend usage is not exposed",
            "release_gate": "NOT_EVALUATED",
        }

    async def timing(
        self,
        question: str,
        samples: int,
        *,
        cold_restart: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        restart_count = 0
        stopped = False
        clients = [self.client(), self.client()]
        try:
            if cold_restart is None:
                for client in clients:
                    await self.start(client)
                    await self.ask(client, question)  # warm-up is also budgeted
            for offset in range(0, samples, 2):
                if cold_restart is not None:
                    cold_restart()
                    restart_count += 1
                for client in clients:
                    await self.start(client)
                batch = await asyncio.gather(
                    *(self.ask(client, question) for client in clients[: min(2, samples - offset)]),
                    return_exceptions=True,
                )
                for outcome in batch:
                    if isinstance(outcome, BudgetExhausted):
                        stopped = True
                    elif isinstance(outcome, BaseException):
                        raise outcome
                    else:
                        results.append(outcome)
                if stopped:
                    break
        finally:
            for client in clients:
                await client.aclose()
        valid = [
            r["latency_ms"]
            for r in results
            if r["transport_valid"] and r["response"].get("result_status") == "success"
        ]
        return {
            "valid_samples": len(valid),
            "total_samples": len(results),
            "p95_ms": percentile95(valid),
            "samples": results,
            "cold_restart_count": restart_count,
            "budget_exhausted": stopped,
        }
