"""Fixed public cases and evaluation diagnostics; judgments come from independent labels."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

from campuspilot.chat_model import SYSTEM, ChatCompletionsModel, ChatTurn, ModelReply
from campuspilot.chat_runtime import ChatRuntime, ConversationContext, Mode, public_input
from campuspilot.contracts import Contract
from campuspilot.dify import ChatUnavailable
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.evaluation_budget import BudgetExhausted, EvaluationBudget, TokenPrice
from campuspilot.jev_shadow import JevShadowClient
from campuspilot.knowledge import KnowledgeStore
from campuspilot.rag import SnapshotStore, canonical, digest


class GoldenCase(Contract):
    case_id: str
    split: Literal["development", "holdout"]
    question: str
    messages: tuple[str, ...]
    group: str
    public_fixture: Literal[True]
    expected_facts: tuple[str, ...]
    required_premises: tuple[str, ...]
    chunk_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    service_ids: tuple[str, ...]
    teacher_ids: tuple[str, ...]
    place_ids: tuple[str, ...]
    answer_strategy: Literal["direct", "generate", "clarify", "empty"]
    expected_search_needed: bool


def load_cases(directory: Path) -> tuple[GoldenCase, ...]:
    import json

    raw = (directory / "cases.jsonl").read_bytes()
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if digest(raw) != manifest["cases_sha256"]:
        raise ValueError("Fixed golden cases changed")
    cases = tuple(GoldenCase.model_validate_json(row) for row in raw.splitlines() if row)
    if len(cases) != 120 or len({c.case_id for c in cases}) != 120:
        raise ValueError("Expected 120 unique cases")
    if sum(c.split == "holdout" for c in cases) != 40:
        raise ValueError("Expected 80 development and 40 holdout cases")
    if any(not public_input(q) for c in cases for q in (*c.messages, c.question)):
        raise ValueError("Fixed public fixtures cannot include private data")
    return cases


@dataclass(frozen=True)
class BudgetedModel:
    model: ChatCompletionsModel
    price: TokenPrice
    budget: EvaluationBudget

    async def generate(
        self, question: str, evidence: str, history: tuple[ChatTurn, ...]
    ) -> ModelReply:
        approximate = (
            len(canonical([SYSTEM, question, evidence, [h.model_dump() for h in history]])) + 2048
        )
        reservation = self.budget.reserve(
            self.price.cost(approximate, self.model.max_output_tokens), "generation"
        )
        try:
            reply = await self.model.generate(question, evidence, history)
        except ChatUnavailable:
            self.budget.settle(reservation, None)
            raise
        self.budget.settle(
            reservation,
            self.price.cost(reply.input_tokens, reply.output_tokens) if reply.usage_known else None,
        )
        return reply


def percentile95(values: list[float]) -> float | None:
    if not values:
        return None
    return sorted(values)[math.ceil(len(values) * 0.95) - 1]


async def evaluate(
    data_dir: Path,
    cases: tuple[GoldenCase, ...],
    stage: Mode,
    *,
    model: BudgetedModel | None = None,
    jev: JevShadowClient | None = None,
    budget: EvaluationBudget | None = None,
    progress: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    evaluation_started = time.perf_counter()
    backend = ChatRuntime(
        DirectoryRepository.load(data_dir),
        KnowledgeStore.load(data_dir / "knowledge.json"),
        SnapshotStore(data_dir / "rag"),
        mode=stage,
        model=model,
    )
    outputs: list[dict[str, object]] = []
    stopped = False
    for case in cases:
        context = ConversationContext()
        for text in case.messages:
            prefix = backend.prepare(text, context, case.case_id)
            try:
                response = await backend.generate(prefix, context.history)
            except ChatUnavailable as error:
                response = backend.limited(prefix, error.code)
            except BudgetExhausted:
                stopped = True
                break
            answer = response.get("answer")
            if isinstance(answer, str):
                context.remember(text, answer)
        if stopped:
            break
        started = time.perf_counter()
        prepared = backend.prepare(case.question, context, case.case_id)
        try:
            response = await backend.generate(prepared, context.history)
        except ChatUnavailable as error:
            response = backend.limited(prepared, error.code)
        except BudgetExhausted:
            stopped = True
            break
        elapsed = (time.perf_counter() - started) * 1000
        candidates = tuple(h.chunk.chunk_id for h in prepared.hits)
        shadow: dict[str, object] = {"status": "NOT_RUN"}
        if jev is not None and budget is not None:
            summary = str((prepared.response or {}).get("answer", ""))
            try:
                result = await jev.evaluate(
                    case.question,
                    prepared.hits,
                    public_fixture=True,
                    budget=budget,
                    rule_summary=summary,
                )
            except BudgetExhausted:
                stopped = True
                break
            shadow = asdict(result)
            shadow["strategy_matches_label"] = result.answer_mode == case.answer_strategy
            shadow["search_matches_label"] = result.search_needed == case.expected_search_needed
            shadow["independent_context_overlap"] = len(
                set(result.selected_ids) & set(case.chunk_ids)
            )
        outputs.append(
            {
                "case_id": case.case_id,
                "split": case.split,
                "group": case.group,
                "route": prepared.route,
                "response": response,
                "latency_ms": elapsed,
                "total_evaluation_latency_ms": (time.perf_counter() - started) * 1000,
                "candidate_ids": candidates,
                "selected_ids": candidates[:4],
                "retrieval_label_hit": bool(set(candidates) & set(case.chunk_ids))
                if case.chunk_ids
                else None,
                "initial_context_label_overlap": len(set(candidates[:4]) & set(case.chunk_ids)),
                "task_judgment": "PENDING_INDEPENDENT_LABEL_REVIEW",
                "jev_shadow": shadow,
            }
        )
        if progress:
            progress(
                {
                    "mode": "live_adapters" if model or jev else "offline",
                    "stage": stage,
                    "cases": outputs,
                    "budget": budget.report() if budget else None,
                    "release_gate": "NOT_EVALUATED",
                    "collection_complete": False,
                }
            )
    retrieval = [r["retrieval_label_hit"] for r in outputs if r["retrieval_label_hit"] is not None]
    shadows = [cast(dict[str, object], r["jev_shadow"]) for r in outputs]
    successful = [r for r in shadows if r.get("status") == "ok"]
    labelled = [r for r in outputs if r["retrieval_label_hit"] is not None]
    return {
        "schema_version": 1,
        "stage": stage,
        "mode": "live_adapters" if model or jev else "offline",
        "cases": outputs,
        "requested_cases": len(cases),
        "collection_complete": not stopped and len(outputs) == len(cases),
        "budget_exhausted": stopped,
        "total_evaluation_elapsed_ms": (time.perf_counter() - evaluation_started) * 1000,
        "answer_quality": "PENDING_INDEPENDENT_LABEL_REVIEW",
        "model_configuration": {"base_url": model.model.base_url, "model": model.model.model}
        if model
        else None,
        "retrieval_label_hit_rate": sum(bool(v) for v in retrieval) / len(retrieval)
        if retrieval
        else None,
        "observed_adapter_p95_ms": percentile95([float(str(r["latency_ms"])) for r in outputs]),
        "performance_scope": "in_process_adapter_diagnostic_not_complete_API_deployment_acceptance",
        "budget": budget.report() if budget else None,
        "independent_label_diagnostics": {
            "retrieval_misses": sum(not bool(r["retrieval_label_hit"]) for r in labelled),
            "initial_context_overlap_mean": sum(
                int(str(r["initial_context_label_overlap"])) for r in labelled
            )
            / len(labelled)
            if labelled
            else None,
            "jev_valid_choices": len(successful),
            "strategy_matches": sum(bool(r.get("strategy_matches_label")) for r in successful),
            "search_matches": sum(bool(r.get("search_matches_label")) for r in successful),
            "ineffective_search_suggestions": sum(
                r.get("search_needed") is True and r.get("search_matches_label") is False
                for r in successful
            ),
            "missed_search_suggestions": sum(
                r.get("search_needed") is False and r.get("search_matches_label") is False
                for r in successful
            ),
            "jev_context_overlap_mean": sum(
                int(str(r.get("independent_context_overlap", 0))) for r in successful
            )
            / len(successful)
            if successful
            else None,
            "jev_p95_ms": percentile95([float(str(r.get("latency_ms", 0))) for r in successful]),
        },
        "release_gate": "NOT_EVALUATED",
    }
