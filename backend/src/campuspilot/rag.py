"""Versioned public evidence and small, provider-independent retrieval contracts."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, Protocol, Self

from pydantic import Field, model_validator

from campuspilot.contracts import Contract
from campuspilot.knowledge import official_url


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class RagSource(Contract):
    source_id: str
    title: str
    url: str
    publisher: str
    applicability: str
    temporal_status: Literal["unknown", "historical", "superseded", "current"] = "unknown"
    content_scope: str = "curated_paraphrase_not_full_text"
    # "pending" exists only for candidate snapshots awaiting review; publish() refuses them.
    verification_status: Literal["verified", "official_document", "pending"]
    reviewer: str
    verified_at: date | None

    @model_validator(mode="after")
    def source_scope(self) -> Self:
        official_url(self.url, wechat=True)
        if not all((self.source_id, self.title, self.publisher)):
            raise ValueError("Incomplete source provenance")
        if self.verification_status != "pending" and not (self.reviewer and self.verified_at):
            raise ValueError("Incomplete source provenance")
        if self.verification_status == "pending" and (self.reviewer or self.verified_at):
            raise ValueError("Pending sources cannot carry a review")
        return self


class RagChunk(Contract):
    chunk_id: str
    source_id: str
    topic_id: str
    title: str
    text: Annotated[str, Field(min_length=1, max_length=8000)]
    locator: str
    aliases: str = ""
    kind: Literal["fact", "historical", "index_only", "deprecated", "limitation"] = "fact"
    text_sha256: str
    verification_status: Literal["verified", "official_document", "pending"]
    reviewer: str
    verified_at: date | None
    approval_id: str
    audiences: tuple[str, ...] = ("all",)
    academic_year: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    enabled: bool = True
    # Source flagged as possibly out of date: down-weighted and cited with a warning.
    stale: bool = False

    @model_validator(mode="after")
    def approved_content(self) -> Self:
        if digest(self.text.encode()) != self.text_sha256:
            raise ValueError("Changed body requires renewed review")
        if not all((self.chunk_id, self.locator, self.approval_id)):
            raise ValueError("Incomplete chunk review")
        pending = self.verification_status == "pending"
        if pending and (self.reviewer or self.verified_at):
            raise ValueError("Pending chunks cannot carry a review")
        if not pending and not (self.reviewer and self.verified_at):
            raise ValueError("Incomplete chunk review")
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError("Reversed applicability dates")
        return self


class KnowledgeSnapshot(Contract):
    schema_version: Literal[1] = 1
    version: Annotated[str, Field(pattern=r"^kb-[a-f0-9]{16}$")]
    source_package_sha256: str
    sources: tuple[RagSource, ...]
    chunks: tuple[RagChunk, ...]

    @model_validator(mode="after")
    def integrity(self) -> Self:
        ids = {s.source_id for s in self.sources}
        if len(ids) != len(self.sources) or len({c.chunk_id for c in self.chunks}) != len(
            self.chunks
        ):
            raise ValueError("Duplicate stable evidence ID")
        if len(self.chunks) > 10_000 or any(c.source_id not in ids for c in self.chunks):
            raise ValueError("Invalid snapshot references or size")
        body = snapshot_body(self.model_dump(mode="json", exclude={"version"}))
        if self.version != "kb-" + digest(canonical(body))[:16]:
            raise ValueError("Snapshot version does not match content")
        return self

    @property
    def pending(self) -> bool:
        return any(s.verification_status == "pending" for s in self.sources) or any(
            c.verification_status == "pending" for c in self.chunks
        )


def snapshot_body(body: dict[str, Any]) -> dict[str, Any]:
    """Hash body; optional fields at their default are omitted so older versions keep IDs."""
    for chunk in body["chunks"]:
        if chunk.get("stale") is False:
            del chunk["stale"]
    return body


def make_snapshot(
    sources: tuple[RagSource, ...], chunks: tuple[RagChunk, ...], package_hash: str
) -> KnowledgeSnapshot:
    body = {
        "schema_version": 1,
        "source_package_sha256": package_hash,
        "sources": [s.model_dump(mode="json") for s in sorted(sources, key=lambda s: s.source_id)],
        "chunks": [c.model_dump(mode="json") for c in sorted(chunks, key=lambda c: c.chunk_id)],
    }
    hashed = snapshot_body(json.loads(canonical(body)))
    return KnowledgeSnapshot.model_validate_json(
        canonical({**body, "version": "kb-" + digest(canonical(hashed))[:16]})
    )


class RetrievalFilters(Contract):
    today: date
    audience: str = "all"
    academic_year: str | None = None
    historical: bool = False
    current_only: bool = False


class RetrievalHit(Contract):
    knowledge_version: str
    chunk: RagChunk
    source: RagSource
    score: float


class Retriever(Protocol):
    def search(
        self, query: str, filters: RetrievalFilters, top_k: int = 12
    ) -> tuple[RetrievalHit, ...]: ...


class Reranker(Protocol):
    async def rank(
        self, query: str, candidates: tuple[RetrievalHit, ...], top_k: int = 4
    ) -> tuple[str, ...]: ...


class DecisionPolicy(Protocol):
    async def decide(self, query: str, candidates: tuple[RetrievalHit, ...]) -> str: ...


class VectorIndexBinding(Contract):
    knowledge_version: Annotated[str, Field(pattern=r"^kb-[a-f0-9]{16}$")]
    embedding_model_version: Annotated[str, Field(min_length=1)]
    dimensions: Annotated[int, Field(gt=0)]


class VectorRetriever(Retriever, Protocol):
    """Future implementation shares approved fragment IDs and evidence contracts."""

    binding: VectorIndexBinding


class CandidateDecisionPolicy(Protocol):
    """Future closed-set Skill/tool advice remains outside permission decisions."""

    async def choose(
        self, query: str, option_ids: tuple[str, ...], candidates: tuple[RetrievalHit, ...]
    ) -> tuple[str, ...]: ...


class SnapshotStore:
    """Load immutable snapshots; a request holds one retriever through publication.

    The retriever follows the retrieval flag (lexical / vector / hybrid). A vector index is
    read from the same version directory as the snapshot (``vectors.sqlite``) or, for the
    bootstrap snapshot, ``bootstrap.vectors.sqlite``; a missing or mismatched index leaves
    vector search disabled and hybrid degrades to BM25.
    """

    def __init__(
        self,
        root: Path,
        retrieval_mode: str = "lexical",
        embedder: QueryEmbedder | None = None,
        embedding_model: str = "@cf/baai/bge-m3",
        bundled: str = "",
    ) -> None:
        self.root = root
        # Optional in-repo approved candidate (e.g. "approved-20261011") replacing bootstrap.json
        # when no live pointer is published; snapshot.json + vectors.sqlite in that directory.
        if bundled and not re.fullmatch(r"approved-\d{8}", bundled):
            raise ValueError("Invalid bundled knowledge name")
        self.bundled = bundled
        self.retrieval_mode = retrieval_mode
        self.embedder = embedder
        self.embedding_model = embedding_model
        self.index_error = ""
        self._cached: HybridRetriever | None = None
        self._key = ""

    def acquire(self) -> HybridRetriever | None:
        from campuspilot.retrieval.hybrid import HybridRetriever
        from campuspilot.retrieval.vector import INDEX_NAME, VectorIndex

        pointer = self.root / "current.json"
        if pointer.exists():
            raw = json.loads(pointer.read_bytes())
            version = raw["version"]
            if not isinstance(version, str) or not re.fullmatch(r"kb-[a-f0-9]{16}", version):
                raise ValueError("Invalid knowledge pointer")
            path = self.root / "versions" / version / "snapshot.json"
            index_path = path.parent / INDEX_NAME
            key = version + ":" + raw["sha256"]
        elif self.bundled:
            path = self.root / self.bundled / "snapshot.json"
            index_path = self.root / self.bundled / INDEX_NAME
            if not path.exists():
                raise ValueError("Bundled knowledge snapshot missing")
            key = digest(path.read_bytes())
        else:
            path = self.root / "bootstrap.json"
            index_path = self.root / ("bootstrap." + INDEX_NAME)
            if not path.exists():
                return None
            key = digest(path.read_bytes())
        if self._cached is not None and key == self._key:
            return self._cached
        data = path.read_bytes()
        if len(data) > 20_000_000 or (pointer.exists() and digest(data) != raw["sha256"]):
            raise ValueError("Knowledge snapshot checksum mismatch")
        snapshot = KnowledgeSnapshot.model_validate_json(data)
        if snapshot.pending:
            raise ValueError("Pending knowledge cannot be served")
        if pointer.exists() and snapshot.version != version:
            raise ValueError("Knowledge pointer version mismatch")
        index = None
        self.index_error = ""
        if self.retrieval_mode != "lexical":
            try:
                index = VectorIndex.load(index_path, snapshot, self.embedding_model)
            except (OSError, ValueError, sqlite3.Error) as exc:
                self.index_error = str(exc)
        embedder = self.embedder
        self._cached = HybridRetriever(
            snapshot,
            mode=self.retrieval_mode,  # type: ignore[arg-type]
            index=index,
            query_vector=embedder.cached if embedder is not None else None,
        )
        self._key = key
        return self._cached


class QueryEmbedder(Protocol):
    def cached(self, text: str) -> list[float] | None: ...


if TYPE_CHECKING:
    from campuspilot.retrieval.bm25 import BM25Retriever
    from campuspilot.retrieval.bm25 import terms as terms
    from campuspilot.retrieval.hybrid import HybridRetriever

    LexicalRetriever = BM25Retriever


def __getattr__(name: str) -> object:
    # Backward-compatible names; BM25 now lives in campuspilot.retrieval.bm25.
    if name in {"LexicalRetriever", "terms"}:
        from campuspilot.retrieval import bm25

        return bm25.BM25Retriever if name == "LexicalRetriever" else bm25.terms
    raise AttributeError(name)
