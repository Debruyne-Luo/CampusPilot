"""Deterministic local "no-grounding" decision over one hybrid search (no model, no network).

A hit is *grounded* when its query-vector cosine similarity is high on its own
(``>= STRONG_SIMILARITY``), or moderately high (``>= FLOOR_SIMILARITY``) **and** both channels
agree on it (BM25 rank and vector rank each ``<= AGREE_RANK``). A search with no grounded hit
among the shown candidates is ``insufficient``: callers must answer with the honest
no-basis message instead of excerpting or citing those chunks.

Thresholds were chosen on the dev sets only (evaluation/dev-colloquial-20261011 plus
evaluation/refusal-20261011/dev.jsonl); see docs/RETRIEVAL.zh-CN.md. Query term coverage and
the fused RRF score are recorded as signals but are not used in the decision: on the dev set
neither separated out-of-KB questions from answerable ones beyond what similarity + channel
agreement already did.

Without a query vector (lexical mode, embedder outage) the decision is ``unassessed`` and
callers keep their previous behaviour; refusing every degraded turn would be worse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from campuspilot.rag import RetrievalHit
from campuspilot.retrieval.bm25 import GENERIC, terms
from campuspilot.retrieval.hybrid import ChannelResult

POLICY_VERSION = "local-grounding-v1"
STRONG_SIMILARITY = 0.60
FLOOR_SIMILARITY = 0.52
AGREE_RANK = 3
SHOWN = 4  # matches the search_knowledge default top_k

Decision = Literal["grounded", "insufficient", "unassessed"]


@dataclass(frozen=True)
class HitSignals:
    chunk_id: str
    similarity: float | None
    lexical_rank: int | None
    vector_rank: int | None
    coverage: float
    fused: float
    grounded: bool


@dataclass(frozen=True)
class GroundingDecision:
    decision: Decision
    signals: tuple[HitSignals, ...]

    @property
    def grounded_ids(self) -> frozenset[str]:
        return frozenset(s.chunk_id for s in self.signals if s.grounded)


def coverage(query: str, hit: RetrievalHit) -> float:
    """Share of the query's (non-generic) 2/3-gram terms that occur in the chunk."""
    wanted = terms(query)
    for generic in GENERIC:
        for token in terms(generic):
            wanted.pop(token, None)
    if not wanted:
        return 0.0
    chunk = hit.chunk
    have = terms(chunk.title + " " + chunk.aliases + " " + chunk.text)
    return sum(1 for t in wanted if t in have) / len(wanted)


def is_grounded(
    similarity: float | None, lexical_rank: int | None, vector_rank: int | None
) -> bool:
    if similarity is None:
        return False
    if similarity >= STRONG_SIMILARITY:
        return True
    agree = (
        lexical_rank is not None
        and vector_rank is not None
        and lexical_rank <= AGREE_RANK
        and vector_rank <= AGREE_RANK
    )
    return similarity >= FLOOR_SIMILARITY and agree


def assess(query: str, result: ChannelResult, shown: int = SHOWN) -> GroundingDecision:
    hits = result.hits[:shown]
    lexical = {h.chunk.chunk_id: i for i, h in enumerate(result.lexical, start=1)}
    if result.dense is None:
        signals = tuple(
            HitSignals(
                h.chunk.chunk_id,
                None,
                lexical.get(h.chunk.chunk_id),
                None,
                round(coverage(query, h), 4),
                h.score,
                True,
            )
            for h in hits
        )
        return GroundingDecision("unassessed", signals)
    dense = {h.chunk.chunk_id: (i, h.score) for i, h in enumerate(result.dense, start=1)}
    rows = []
    for h in hits:
        cid = h.chunk.chunk_id
        rank, sim = dense.get(cid, (None, None))
        lrank = lexical.get(cid)
        rows.append(
            HitSignals(
                cid,
                None if sim is None else round(sim, 4),
                lrank,
                rank,
                round(coverage(query, h), 4),
                h.score,
                is_grounded(sim, lrank, rank),
            )
        )
    signals = tuple(rows)
    return GroundingDecision(
        "grounded" if any(s.grounded for s in signals) else "insufficient", signals
    )


class LocalGroundingPolicy:
    """`rag.DecisionPolicy` bound to one search's channel rankings."""

    def __init__(self, result: ChannelResult) -> None:
        self.result = result

    async def decide(self, query: str, candidates: tuple[RetrievalHit, ...]) -> str:
        shown = ChannelResult(candidates, self.result.lexical, self.result.dense)
        return assess(query, shown, len(candidates) or SHOWN).decision
