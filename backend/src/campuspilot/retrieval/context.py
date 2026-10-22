"""Bounded expansion of already retrieved evidence, without changing retrieval rankings."""

from __future__ import annotations

from pydantic import JsonValue

from campuspilot.rag import (
    KnowledgeSnapshot,
    RagChunk,
    RetrievalFilters,
    RetrievalHit,
    compatible_scope,
)
from campuspilot.retrieval.bm25 import eligible

CONTEXT_BUDGET_REASON = "evidence_context_budget_exceeded"
CONTEXT_BUDGET_NOTICE = "资料及同章节条件超出证据预算，本次未能核验完整要求。"


def withheld_context(version: str) -> dict[str, JsonValue]:
    return {
        "result_status": "unavailable", "answer": "", "hits": [], "context": [],
        "context_complete": False, "withheld": True, "reason": CONTEXT_BUDGET_REASON,
        "limitation": CONTEXT_BUDGET_NOTICE, "knowledge_version": version,
    }


def context_dependency(anchor: RagChunk, related: RagChunk) -> bool:
    """One relationship check for selecting context and retaining it after reranking."""
    return bool(anchor.revision_id and (
        anchor.source_id, anchor.document_id, anchor.revision_id,
    ) == (
        related.source_id, related.document_id, related.revision_id,
    ) and (
        anchor.section_id and related.section_id == anchor.section_id
        and related.heading_path == anchor.heading_path
        or related.chunk_id == anchor.parent_chunk_id
    ) and compatible_scope(related, anchor))


def section_context(
    snapshot: KnowledgeSnapshot, hits: tuple[RetrievalHit, ...], filters: RetrievalFilters,
    *, max_chunks: int = 8, max_chars: int = 12000,
) -> tuple[RetrievalHit, ...]:
    """Only checked same-revision/same-scope relatives; retain each original citation."""
    if not 0 <= max_chunks <= 32 or not 0 <= max_chars <= 64000:
        raise ValueError("Invalid context budget")
    sources = {s.source_id: s for s in snapshot.sources}
    selected = {h.chunk.chunk_id for h in hits}
    result: list[RetrievalHit] = []
    remaining = max_chars
    for hit in hits:
        anchor = hit.chunk
        if not anchor.revision_id or not (anchor.section_id or anchor.parent_chunk_id):
            continue
        related = [c for c in snapshot.chunks if c.chunk_id not in selected
                   and context_dependency(anchor, c) and eligible(c, sources[c.source_id], filters)]
        # Parent and explicit exceptions precede other same-section siblings.
        related.sort(key=lambda c: (
            c.chunk_id != anchor.parent_chunk_id, not bool(c.exceptions), c.chunk_id
        ))
        for chunk in related:
            if len(result) >= max_chunks:
                return tuple(result)
            if len(chunk.text) > remaining:
                continue  # never truncate evidence or silently change a text hash
            result.append(RetrievalHit(
                knowledge_version=hit.knowledge_version, chunk=chunk,
                source=sources[chunk.source_id], score=hit.score,
            ))
            selected.add(chunk.chunk_id)
            remaining -= len(chunk.text)
    return tuple(result)


def context_complete(
    snapshot: KnowledgeSnapshot, hits: tuple[RetrievalHit, ...],
    context: tuple[RetrievalHit, ...], filters: RetrievalFilters,
) -> bool:
    """An exhausted context budget is a missing condition, never evidence of no exception."""
    sources = {s.source_id: s for s in snapshot.sources}
    selected = {h.chunk.chunk_id for h in (*hits, *context)}
    return not any(
        chunk.chunk_id not in selected
        and any(context_dependency(h.chunk, chunk) for h in hits)
        and eligible(chunk, sources[chunk.source_id], filters)
        for chunk in snapshot.chunks
    )
