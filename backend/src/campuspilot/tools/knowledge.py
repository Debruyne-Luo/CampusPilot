"""Official knowledge search through the unified Tool interface."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, JsonValue

from campuspilot.contracts import Contract
from campuspilot.knowledge import KnowledgeQuery, KnowledgeStore, campus_today
from campuspilot.llm.embedding import CloudflareEmbedder, EmbeddingUnavailable
from campuspilot.rag import RetrievalFilters, SnapshotStore
from campuspilot.retrieval.grounding import POLICY_VERSION, assess


class KnowledgeSearchTool:
    """Legacy knowledge.json search; used when no snapshot store is wired."""

    name = "search_knowledge"
    description = "检索已收录的学校官方资料（按类别、对象、时效过滤），返回摘要与来源。"
    params_model: type[BaseModel] = KnowledgeQuery

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store

    def run(self, params: Any) -> dict[str, JsonValue]:
        response = self._store.response(params, campus_today())
        return {key: value for key, value in response.items()}  # type: ignore[misc]


class SnapshotQuery(Contract):
    query: Annotated[str, Field(min_length=1, max_length=500, pattern=r"\S")]
    audience: Literal["all", "undergraduate", "graduate", "staff"] = "all"
    academic_year: Annotated[str, Field(pattern=r"^\d{4}-\d{4}$")] | None = None
    top_k: Annotated[int, Field(ge=1, le=8)] = 4


class HybridKnowledgeTool:
    """search_knowledge over the approved snapshot with lexical / vector / hybrid retrieval."""

    name = "search_knowledge"
    description = (
        "混合检索（BM25 + 向量，RRF 融合）已审核的学校官方资料片段，"
        "先按对象、学年、时效过滤；返回片段原文、来源与知识版本。"
    )
    params_model: type[BaseModel] = SnapshotQuery

    def __init__(self, snapshots: SnapshotStore, embedder: CloudflareEmbedder | None) -> None:
        self._snapshots = snapshots
        self._embedder = embedder

    def run(self, params: Any) -> dict[str, JsonValue]:
        retriever = self._snapshots.acquire()
        if retriever is None:
            return {"result_status": "empty", "answer": "", "hits": []}
        vector = None
        if self._embedder is not None and retriever.mode != "lexical":
            try:
                vector = self._embedder.embed_query(params.query)
            except (EmbeddingUnavailable, ValueError):
                vector = None
        filters = RetrievalFilters(
            today=campus_today(), audience=params.audience, academic_year=params.academic_year
        )
        searched = retriever.search_channels(
            params.query, filters, params.top_k, query_vector=vector
        )
        hits = searched.hits
        grounding = assess(params.query, searched, len(hits))
        grounded = grounding.grounded_ids  # every hit when unassessed (no query vector)
        rows: list[JsonValue] = [
            {
                "chunk_id": h.chunk.chunk_id,
                "source_id": h.source.source_id,
                "title": h.chunk.title,
                "text": h.chunk.text,
                "source_title": h.source.title,
                "url": h.source.url,
                "publisher": h.source.publisher,
                "applicability": h.source.applicability,
                "stale": h.chunk.stale,
                "ocr": h.chunk.ocr,
                "score": round(h.score, 6),
                "grounded": h.chunk.chunk_id in grounded,
            }
            for h in hits
        ]
        return {
            "result_status": "success" if hits else "empty",
            "answer": "\n".join([h.chunk.text for h in hits if h.chunk.chunk_id in grounded][:3]),
            "hits": rows,
            "knowledge_version": retriever.snapshot.version,
            "retrieval_mode": retriever.mode,
            "degraded": retriever.degraded,
            "grounding": {
                "policy": POLICY_VERSION,
                "decision": grounding.decision if hits else "insufficient",
            },
        }
