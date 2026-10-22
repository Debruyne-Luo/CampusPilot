"""Official knowledge search through the unified Tool interface."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, JsonValue

from campuspilot.contracts import Contract
from campuspilot.knowledge import KnowledgeQuery, KnowledgeStore, campus_today
from campuspilot.llm.embedding import CloudflareEmbedder, EmbeddingUnavailable
from campuspilot.rag import RetrievalFilters, SnapshotStore
from campuspilot.retrieval.applicability import conditional_text, evidence_metadata, query_filters
from campuspilot.retrieval.context import (
    context_complete,
    context_dependency,
    section_context,
    withheld_context,
)
from campuspilot.retrieval.grounding import POLICY_VERSION, GroundingMode, assess
from campuspilot.service_links import hit_service_links


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
    campus: Literal["chengdu", "yibin", "emei", "all", "unknown"] = "chengdu"


class HybridKnowledgeTool:
    """search_knowledge over the approved snapshot with lexical / vector / hybrid retrieval."""

    name = "search_knowledge"
    description = (
        "混合检索（BM25 + 向量，RRF 融合）已审核的学校官方资料片段，"
        "先按校区、对象、学年、时效过滤；返回片段原文、同章节条件、来源修订与知识版本。"
    )
    params_model: type[BaseModel] = SnapshotQuery

    def __init__(
        self,
        snapshots: SnapshotStore,
        embedder: CloudflareEmbedder | None,
        grounding: GroundingMode = "flag",
    ) -> None:
        self._snapshots = snapshots
        self._embedder = embedder
        self.grounding = grounding
        self._turn_scope: ContextVar[RetrievalFilters | None] = ContextVar(
            "campuspilot_tool_retrieval_scope", default=None
        )
        self._entry_lookup: ContextVar[bool] = ContextVar("campuspilot_entry_lookup", default=False)

    @contextmanager
    def pin_scope(self, filters: RetrievalFilters, *, entry_only: bool = False) -> Iterator[None]:
        """Application-owned user scope survives model query rewrites and async workers."""
        token = self._turn_scope.set(filters)
        entry_token = self._entry_lookup.set(entry_only)
        try:
            yield
        finally:
            self._turn_scope.reset(token)
            self._entry_lookup.reset(entry_token)

    @property
    def snapshot_store(self) -> SnapshotStore:
        """The application-owned store shared with the turn and optional judge."""
        return self._snapshots

    def run(self, params: Any) -> dict[str, JsonValue]:
        retriever = self._snapshots.acquire()
        if retriever is None:
            return {"result_status": "empty", "answer": "", "hits": []}
        vector = None
        if (not self._entry_lookup.get() and self._embedder is not None
                and retriever.mode != "lexical"):
            try:
                vector = self._embedder.embed_query(params.query)
            except (EmbeddingUnavailable, ValueError):
                vector = None
        turn_scope = self._turn_scope.get()
        if turn_scope:
            filters = turn_scope.model_copy(update={"today": campus_today()})
        else:
            filters = query_filters(
                params.query, campus_today(), audience=params.audience,
                academic_year=params.academic_year, campus=params.campus,
            )
        searched = retriever.search_channels(
            params.query, filters, params.top_k, query_vector=vector
        )
        hits = searched.hits
        context = section_context(retriever.snapshot, hits, filters)
        if not context_complete(retriever.snapshot, hits, context, filters):
            return withheld_context(retriever.snapshot.version)
        evidence_hits = (*hits, *context)
        rows: list[JsonValue] = [
            {
                "chunk_id": h.chunk.chunk_id,
                "source_id": h.source.source_id,
                "title": h.chunk.title,
                "text": h.chunk.text,
                "url": h.source.url,
                "source_title": h.source.title,
                "publisher": h.source.publisher,
                "temporal_status": h.source.temporal_status,
                "stale": h.chunk.stale,
                "ocr": h.chunk.ocr,
                **evidence_metadata(h.chunk, filters),
                "verification_status": h.chunk.verification_status,
                "service_links": hit_service_links(h, retriever.service_links),
                "applicability": {
                    "audiences": list(h.chunk.audiences),
                    "campuses": list(h.chunk.campuses),
                    "conditions": list(h.chunk.conditions),
                    "exceptions": list(h.chunk.exceptions),
                    "evidence_quotes": dict(h.chunk.applicability_evidence),
                    "academic_year": h.chunk.academic_year,
                    "valid_from": h.chunk.valid_from.isoformat() if h.chunk.valid_from else None,
                    "valid_until": h.chunk.valid_until.isoformat() if h.chunk.valid_until else None,
                    "source_scope": h.source.applicability,
                },
                "score": round(h.score, 6),
                "context_of": [anchor.chunk.chunk_id for anchor in hits
                               if context_dependency(anchor.chunk, h.chunk)
                ] if h in context else [],
            }
            for h in evidence_hits
        ]
        result: dict[str, JsonValue] = {
            "result_status": "success" if hits else "empty",
            "answer": "\n".join(conditional_text(h.chunk, filters) for h in hits[:3]),
            "hits": rows[:len(hits)],
            "context": rows[len(hits):],
            "context_complete": True,
            "applicability_notice": (
                "按每条资料的适用条件分别说明；未提供身份或学年且影响结论时先澄清。"
                "来源适用范围未确认是资料缺口，不得推定适用，不向用户索取来源缺失信息。"
            ),
            "knowledge_version": retriever.snapshot.version,
            "retrieval_mode": retriever.mode,
            "degraded": retriever.degraded,
        }
        if self.grounding == "off":
            return result
        grounding = assess(params.query, searched, len(hits))
        grounded = grounding.grounded_ids  # every hit when unassessed (no query vector)
        for row, h in zip(rows[:len(hits)], hits, strict=True):
            assert isinstance(row, dict)
            row["grounded"] = h.chunk.chunk_id in grounded
        for row in rows[len(hits):]:
            assert isinstance(row, dict)
            parents = row.get("context_of")
            row["grounded"] = isinstance(parents, list) and any(p in grounded for p in parents)
        if self.grounding == "block":
            result["context"] = [row for row in rows[len(hits):]
                                 if isinstance(row, dict) and row.get("grounded")]
        if self.grounding == "block":
            result["answer"] = "\n".join(
                [conditional_text(h.chunk, filters) for h in hits
                 if h.chunk.chunk_id in grounded][:3]
            )
        result["grounding"] = {
            "policy": POLICY_VERSION,
            "mode": self.grounding,
            "decision": grounding.decision if hits else "insufficient",
        }
        return result
