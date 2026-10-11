"""BM25 over Chinese 2/3-gram and ASCII word terms, with a weighted title field.

Hard filters (enabled, validity window, historical, audience, academic year) are applied in
`eligible()`, shared by every retriever so fusion only ever sees admissible chunks.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from campuspilot.rag import KnowledgeSnapshot, RagChunk, RagSource, RetrievalFilters, RetrievalHit

GENERIC = ("请问", "如何", "怎么", "什么", "哪里", "你好", "谢谢", "是否")
TITLE_WEIGHT = 3.4
K1 = 1.2
B = 0.75


def terms(text: str) -> Counter[str]:
    text = text.casefold()
    result: Counter[str] = Counter(re.findall(r"[a-z0-9]+", text))
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        for width in (2, 3):
            result.update(run[i : i + width] for i in range(len(run) - width + 1))
    return result


def query_terms(query: str) -> Counter[str]:
    tokens = terms(query)
    for generic in GENERIC:
        for token in terms(generic):
            tokens.pop(token, None)
    return tokens


def eligible(chunk: RagChunk, source: RagSource, filters: RetrievalFilters) -> bool:
    if not chunk.enabled:
        return False
    expired = bool(chunk.valid_until and chunk.valid_until < filters.today)
    historical = (
        chunk.kind in {"historical", "deprecated"}
        or source.temporal_status in {"historical", "superseded"}
        or expired
    )
    if historical and not filters.historical:
        return False
    if chunk.valid_from and chunk.valid_from > filters.today:
        return False
    if filters.current_only and (historical or source.temporal_status != "current"):
        return False
    if filters.audience != "all" and "all" not in chunk.audiences:
        if filters.audience not in chunk.audiences:
            return False
    if filters.academic_year and chunk.academic_year not in (None, filters.academic_year):
        return False
    return True


def eligible_chunks(
    snapshot: KnowledgeSnapshot, sources: dict[str, RagSource], filters: RetrievalFilters
) -> list[RagChunk]:
    return [c for c in snapshot.chunks if eligible(c, sources[c.source_id], filters)]


class BM25Retriever:
    """Okapi BM25 with a title-weighted term frequency (BM25F-style single field)."""

    def __init__(self, snapshot: KnowledgeSnapshot) -> None:
        self.snapshot = snapshot
        self.sources = {s.source_id: s for s in snapshot.sources}
        self.fields = {
            c.chunk_id: (terms(c.title + " " + c.aliases), terms(c.text)) for c in snapshot.chunks
        }
        self.df: Counter[str] = Counter()
        self.lengths: dict[str, float] = {}
        for chunk_id, (title, body) in self.fields.items():
            self.df.update(title.keys() | body.keys())
            self.lengths[chunk_id] = TITLE_WEIGHT * sum(title.values()) + sum(body.values())
        self.avg_length = (sum(self.lengths.values()) / len(self.lengths)) if self.lengths else 1.0

    def idf(self, term: str) -> float:
        n = len(self.fields)
        return math.log(1 + (n - self.df[term] + 0.5) / (self.df[term] + 0.5))

    def score(self, chunk_id: str, tokens: Counter[str]) -> float:
        title, body = self.fields[chunk_id]
        norm = K1 * (1 - B + B * self.lengths[chunk_id] / (self.avg_length or 1.0))
        total = 0.0
        for term, qf in tokens.items():
            tf = TITLE_WEIGHT * title[term] + body[term]
            if tf:
                total += self.idf(term) * min(qf, 2) * tf * (K1 + 1) / (tf + norm)
        return total

    def search(
        self, query: str, filters: RetrievalFilters, top_k: int = 12
    ) -> tuple[RetrievalHit, ...]:
        if not 1 <= top_k <= 100:
            raise ValueError("Invalid candidate limit")
        tokens = query_terms(query)
        found: list[RetrievalHit] = []
        for chunk in eligible_chunks(self.snapshot, self.sources, filters):
            score = self.score(chunk.chunk_id, tokens)
            # Require useful overlap; a single generic character never triggers retrieval.
            if score > 0.5:
                found.append(
                    RetrievalHit(
                        knowledge_version=self.snapshot.version,
                        chunk=chunk,
                        source=self.sources[chunk.source_id],
                        score=score,
                    )
                )
        return tuple(sorted(found, key=lambda h: (-h.score, h.chunk.chunk_id))[:top_k])
