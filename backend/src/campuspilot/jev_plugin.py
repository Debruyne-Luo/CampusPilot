"""Optional in-process Jev plugin (not MCP): reranker + sufficiency policy over one turn.

CAMPUSPILOT_JEV=off|shadow|on (default off). The agent calls :meth:`JevTurn.assess` once,
after the plan's tools ran and before the model answers:

- ``shadow``: Jev is asked and its decision recorded (logs, response ``jev`` metadata);
  answers, citations and summaries are untouched.
- ``on``: chunks Jev scores as irrelevant (rank 0) are dropped and the rest reordered; when
  Jev judges the evidence insufficient (and the local grounding signal does not disagree) the
  turn refuses or asks to clarify without showing unrelated citations.

Any timeout, error, exhausted budget, ``unsure`` or ``unknown`` answer fails open: the
original flow continues unchanged. One Jev request per turn serves both the reranker and the
policy (results are cached per turn).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Literal, Protocol

from pydantic import JsonValue

from campuspilot.evaluation_budget import BudgetExhausted, EvaluationBudget
from campuspilot.jev_shadow import ShadowResult
from campuspilot.rag import RetrievalHit, SnapshotStore

logger = logging.getLogger(__name__)

PLUGIN_VERSION = "jev-plugin-v1"
JevMode = Literal["off", "shadow", "on"]
JEV_MODES: frozenset[str] = frozenset({"off", "shadow", "on"})
# rank_i is an expected score in 0..2; below this the passage counts as "rank 0" (irrelevant).
DROP_BELOW = 0.5
SUFFICIENT_AT = 0.7
INSUFFICIENT_AT = 0.3
LOCAL_RULE = (
    "Answer only from the passages. CampusPilot never invents university facts, URLs, "
    "contacts, opening hours or locations."
)

Decision = Literal["sufficient", "insufficient", "clarify", "unknown"]


def parse_jev_mode(value: str) -> JevMode:
    if value not in JEV_MODES:
        raise ValueError("Invalid Jev mode")
    return value  # type: ignore[return-value]


class JevDecider(Protocol):
    """What the plugin needs from a Jev client (JevShadowClient, or a fake in tests)."""

    @property
    def timeout_seconds(self) -> float: ...

    async def evaluate(
        self,
        question: str,
        candidates: tuple[RetrievalHit, ...],
        *,
        public_fixture: bool,
        budget: EvaluationBudget,
        rule_summary: str = "",
        online: bool = False,
    ) -> ShadowResult: ...


@dataclass(frozen=True)
class JevAssessment:
    status: str  # ok | unsure | unknown | budget | timeout | error
    decision: Decision
    local: str
    original_ids: tuple[str, ...]
    ranked_ids: tuple[str, ...] = ()
    dropped_ids: tuple[str, ...] = ()
    scores: tuple[tuple[str, float], ...] = ()
    answer_mode: str = "unknown"
    sufficient_probability: float | None = None
    latency_ms: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.status == "ok"

    def record(self, mode: str, applied: str = "none") -> dict[str, JsonValue]:
        return {
            "plugin": PLUGIN_VERSION,
            "mode": mode,
            "status": self.status,
            "decision": self.decision,
            "local_grounding": self.local,
            "answer_mode": self.answer_mode,
            "sufficient_probability": self.sufficient_probability,
            "scores": {cid: round(score, 4) for cid, score in self.scores},
            "ranked_ids": list(self.ranked_ids),
            "dropped_ids": list(self.dropped_ids),
            "applied": applied,
            "latency_ms": round(self.latency_ms, 1),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reason": self.reason,
        }


def combine(result: ShadowResult, local: str, original: tuple[str, ...]) -> JevAssessment:
    """Map one validated Jev result plus the local grounding decision to a turn decision."""
    base = JevAssessment(
        status=result.status,
        decision="unknown",
        local=local,
        original_ids=original,
        answer_mode=result.answer_mode,
        sufficient_probability=result.sufficient_probability,
        scores=result.chunk_scores,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        reason=result.reason,
    )
    if result.status != "ok":
        return base
    scored = dict(result.chunk_scores)
    # Unscored candidates were withheld as injection-looking; they are not kept either.
    ranked = tuple(
        cid
        for cid, _ in sorted(
            ((c, scored[c]) for c in original if c in scored), key=lambda p: (-p[1], p[0])
        )
        if scored[cid] >= DROP_BELOW
    )
    dropped = tuple(c for c in original if c not in ranked)
    p = result.sufficient_probability
    decision: Decision = "unknown"
    reason = ""
    if p is None:
        reason = "no_sufficiency"
    elif p >= SUFFICIENT_AT:
        decision = "sufficient"
    elif result.answer_mode == "clarify":
        decision = "clarify"
    elif p <= INSUFFICIENT_AT:
        if local == "grounded" and ranked:
            # Local similarity and Jev's own ranking both find support: disagree, fail open.
            reason = "local_grounding_disagrees"
        else:
            decision = "insufficient"
    else:
        reason = "sufficiency_uncertain"
    return replace(
        base,
        decision=decision,
        ranked_ids=ranked,
        dropped_ids=dropped,
        reason=reason or base.reason,
    )


@dataclass
class JevPlugin:
    client: JevDecider
    budget: EvaluationBudget
    mode: JevMode = "shadow"
    snapshots: SnapshotStore | None = None

    def resolve(self, rows: Sequence[dict[str, JsonValue]]) -> tuple[RetrievalHit, ...]:
        """Tool hit rows -> RetrievalHit from the current approved snapshot (unknown ids drop)."""
        retriever = self.snapshots.acquire() if self.snapshots is not None else None
        if retriever is None:
            return ()
        snapshot = retriever.snapshot
        chunks = {c.chunk_id: c for c in snapshot.chunks}
        sources = {s.source_id: s for s in snapshot.sources}
        hits: list[RetrievalHit] = []
        for row in rows:
            chunk = chunks.get(str(row.get("chunk_id")))
            if chunk is None or chunk.source_id not in sources:
                continue
            score = row.get("score")
            hits.append(
                RetrievalHit(
                    knowledge_version=snapshot.version,
                    chunk=chunk,
                    source=sources[chunk.source_id],
                    score=float(score) if isinstance(score, (int, float)) else 0.0,
                )
            )
        return tuple(hits)

    def turn(self) -> JevTurn:
        return JevTurn(self)


@dataclass
class JevTurn:
    """Per-turn cache: the reranker and the policy share one Jev request."""

    plugin: JevPlugin
    _cache: dict[tuple[str, tuple[str, ...], str], JevAssessment] = field(default_factory=dict)

    async def assess(
        self, query: str, candidates: tuple[RetrievalHit, ...], local: str = "unassessed"
    ) -> JevAssessment:
        original = tuple(dict.fromkeys(h.chunk.chunk_id for h in candidates))
        key = (query, original, local)
        if key in self._cache:
            return self._cache[key]
        client = self.plugin.client
        try:
            async with asyncio.timeout(client.timeout_seconds + 0.5):
                result = await client.evaluate(
                    query,
                    candidates,
                    public_fixture=False,
                    online=True,
                    budget=self.plugin.budget,
                    rule_summary=LOCAL_RULE,
                )
            assessment = combine(result, local, original)
        except BudgetExhausted:
            assessment = JevAssessment("budget", "unknown", local, original, reason="budget")
        except TimeoutError:
            assessment = JevAssessment("timeout", "unknown", local, original, reason="timeout")
        except Exception as exc:  # fail open on any client fault
            assessment = JevAssessment(
                "error", "unknown", local, original, reason=type(exc).__name__
            )
        logger.info(
            "jev mode=%s status=%s decision=%s local=%s dropped=%d",
            self.plugin.mode,
            assessment.status,
            assessment.decision,
            local,
            len(assessment.dropped_ids),
        )
        self._cache[key] = assessment
        return assessment


class JevReranker:
    """`rag.Reranker`: order by Jev's per-chunk rank score, dropping rank-0 chunks.

    Fails open to the original order when Jev is not usable for this turn.
    """

    def __init__(self, turn: JevTurn, local: str = "unassessed") -> None:
        self.turn = turn
        self.local = local

    async def rank(
        self, query: str, candidates: tuple[RetrievalHit, ...], top_k: int = 4
    ) -> tuple[str, ...]:
        assessment = await self.turn.assess(query, candidates, self.local)
        if not assessment.usable or not assessment.ranked_ids:
            return assessment.original_ids[:top_k]
        return assessment.ranked_ids[:top_k]


class JevSufficiencyPolicy:
    """`rag.DecisionPolicy`: sufficient / insufficient / clarify / unknown (fail open)."""

    def __init__(self, turn: JevTurn, local: str = "unassessed") -> None:
        self.turn = turn
        self.local = local

    async def decide(self, query: str, candidates: tuple[RetrievalHit, ...]) -> str:
        return (await self.turn.assess(query, candidates, self.local)).decision


def build_plugin(
    mode: JevMode, budget_dir: str, snapshots: SnapshotStore | None
) -> JevPlugin | None:
    """Production wiring: key/price/model from CAMPUSPILOT_JEV_* (see migration_config)."""
    if mode == "off":
        return None
    if not budget_dir:
        raise ValueError("CAMPUSPILOT_JEV_BUDGET_DIR is required when CAMPUSPILOT_JEV is on")
    from pathlib import Path

    from campuspilot.migration_config import shadow_client

    return JevPlugin(
        client=shadow_client(),
        budget=EvaluationBudget(Path(budget_dir), "phase2"),
        mode=mode,
        snapshots=snapshots,
    )
