"""Lexical / vector / hybrid retrieval behind a feature flag, fused with weighted RRF.

Hard filters run inside each retriever before fusion. If the query vector is unavailable
(provider failure or cache miss on the synchronous path), hybrid degrades to BM25-only and
records `degraded=True` on the retriever's last-search state.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from campuspilot.rag import KnowledgeSnapshot, RetrievalFilters, RetrievalHit
from campuspilot.retrieval.bm25 import BM25Retriever
from campuspilot.retrieval.vector import VectorIndex
from campuspilot.service_links import LinkCatalog

RetrievalMode = Literal["lexical", "vector", "hybrid"]
RETRIEVAL_MODES: frozenset[str] = frozenset({"lexical", "vector", "hybrid"})
# Tuned on evaluation/dev-colloquial-20261011 only (see docs/RETRIEVAL.zh-CN.md).
RRF_K = 10
RRF_WEIGHTS = (1.0, 1.25)  # (lexical, vector)
QueryVector = Callable[[str], Sequence[float] | None]


STALE_WEIGHT = 0.85


def downweight_stale(
    hits: Sequence[RetrievalHit], weight: float = STALE_WEIGHT
) -> tuple[RetrievalHit, ...]:
    """Possibly-outdated chunks keep their place in the candidate set at reduced weight."""
    if not any(h.chunk.stale for h in hits):
        return tuple(hits)
    weighted = [
        h.model_copy(update={"score": h.score * weight}) if h.chunk.stale else h for h in hits
    ]
    return tuple(sorted(weighted, key=lambda h: (-h.score, h.chunk.chunk_id)))


def rrf(
    rankings: Sequence[Sequence[RetrievalHit]],
    k: int = RRF_K,
    weights: Sequence[float] | None = None,
) -> list[RetrievalHit]:
    """Weighted Reciprocal Rank Fusion; the fused score replaces the per-retriever score."""
    scores: dict[str, float] = {}
    first: dict[str, RetrievalHit] = {}
    for i, ranking in enumerate(rankings):
        w = 1.0 if weights is None else weights[i]
        for rank, hit in enumerate(ranking, start=1):
            key = hit.chunk.chunk_id
            scores[key] = scores.get(key, 0.0) + w / (k + rank)
            first.setdefault(key, hit)
    ordered = sorted(scores, key=lambda key: (-scores[key], key))
    return [first[key].model_copy(update={"score": scores[key]}) for key in ordered]


@dataclass(frozen=True)
class ChannelResult:
    """One search: fused hits and each channel's own ranking (``dense`` None when unused)."""

    hits: tuple[RetrievalHit, ...]
    lexical: tuple[RetrievalHit, ...]
    dense: tuple[RetrievalHit, ...] | None


class HybridRetriever:
    """Retriever protocol (`snapshot`, `search`) shared with BM25Retriever."""

    def __init__(
        self,
        snapshot: KnowledgeSnapshot,
        mode: RetrievalMode = "hybrid",
        index: VectorIndex | None = None,
        query_vector: QueryVector | None = None,
        candidates: int = 20,
        rrf_k: int = RRF_K,
        weights: Sequence[float] = RRF_WEIGHTS,
        stale_weight: float = STALE_WEIGHT,
        min_similarity: float | None = None,
        service_links: LinkCatalog | None = None,
    ) -> None:
        if mode not in RETRIEVAL_MODES:
            raise ValueError("Invalid retrieval mode")
        self.snapshot = snapshot
        self.mode: RetrievalMode = mode
        self.lexical = BM25Retriever(snapshot)
        self.index = index
        self.query_vector = query_vector
        self.candidates = candidates
        self.degraded = False
        self.rrf_k = rrf_k
        self.weights = tuple(weights)
        self.stale_weight = stale_weight
        self.min_similarity = min_similarity
        self.service_links = service_links or {}

    def _vector(self, query: str) -> Sequence[float] | None:
        if self.index is None or self.query_vector is None:
            return None
        try:
            return self.query_vector(query)
        except Exception:  # provider errors must never break retrieval
            return None

    def search(
        self,
        query: str,
        filters: RetrievalFilters,
        top_k: int = 12,
        query_vector: Sequence[float] | None = None,
    ) -> tuple[RetrievalHit, ...]:
        return self.search_channels(query, filters, top_k, query_vector).hits

    def search_channels(
        self,
        query: str,
        filters: RetrievalFilters,
        top_k: int = 12,
        query_vector: Sequence[float] | None = None,
    ) -> ChannelResult:
        """Fused hits plus the per-channel rankings they came from (for grounding checks)."""
        hits, lexical, dense = self._channels(query, filters, top_k, query_vector)
        return ChannelResult(
            hits=downweight_stale(hits, self.stale_weight), lexical=lexical, dense=dense
        )

    def _search(
        self,
        query: str,
        filters: RetrievalFilters,
        top_k: int = 12,
        query_vector: Sequence[float] | None = None,
    ) -> tuple[RetrievalHit, ...]:
        """Fused hits before the stale down-weight."""
        return self._channels(query, filters, top_k, query_vector)[0]

    def _channels(
        self,
        query: str,
        filters: RetrievalFilters,
        top_k: int = 12,
        query_vector: Sequence[float] | None = None,
    ) -> tuple[tuple[RetrievalHit, ...], tuple[RetrievalHit, ...], tuple[RetrievalHit, ...] | None]:
        if not 1 <= top_k <= 100:
            raise ValueError("Invalid candidate limit")
        self.degraded = False
        depth = max(top_k, self.candidates)
        if self.mode == "lexical":
            sparse = self.lexical.search(query, filters, depth)
            return sparse[:top_k], sparse, None
        vector = query_vector if query_vector is not None else self._vector(query)
        if vector is None or self.index is None:
            self.degraded = True
            sparse = self.lexical.search(query, filters, depth)
            return sparse[:top_k], sparse, None
        dense = (
            self.index.search(vector, filters, depth)
            if self.min_similarity is None
            else self.index.search(vector, filters, depth, self.min_similarity)
        )
        if self.mode == "vector":
            return dense[:top_k], (), dense
        sparse = self.lexical.search(query, filters, depth)
        return tuple(rrf([sparse, dense], self.rrf_k, self.weights)[:top_k]), sparse, dense
