"""Versioned public evidence and small, provider-independent retrieval contracts."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import struct
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
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
    # Text recognised from an official image (screenshot); cited with "图片识别，请以原文为准".
    ocr: bool = False
    # v2 evidence identity. Unknown legacy applicability is never inferred from prose.
    document_id: str | None = None
    revision_id: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None
    campuses: tuple[str, ...] = ("unknown",)
    section_id: str | None = None
    parent_chunk_id: str | None = None
    heading_path: tuple[str, ...] = ()
    clause_number: str | None = None
    conditions: tuple[str, ...] = ()
    exceptions: tuple[str, ...] = ()
    applicability_evidence: dict[str, str] = Field(default_factory=dict)
    table_headers: tuple[str, ...] = ()
    footnotes: tuple[str, ...] = ()

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
        if bool(self.document_id) != bool(self.revision_id):
            raise ValueError("Document and revision identity must be bound together")
        if not self.campuses or len(set(self.campuses)) != len(self.campuses):
            raise ValueError("Invalid campus applicability")
        if (self.section_id or self.parent_chunk_id) and not self.revision_id:
            raise ValueError("Section context requires revision identity")
        return self


class KnowledgeSnapshot(Contract):
    schema_version: Literal[1, 2] = 1
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
        by_id = {c.chunk_id: c for c in self.chunks}
        for chunk in self.chunks:
            if chunk.parent_chunk_id:
                parent = by_id.get(chunk.parent_chunk_id)
                if parent is None or parent.chunk_id == chunk.chunk_id or (
                    parent.source_id, parent.document_id
                ) != (chunk.source_id, chunk.document_id):
                    raise ValueError("Invalid parent evidence scope")
                # Stable upserts may retain an old child while its parent is revised. Its
                # old relationship remains provenance, never expandable in the new revision.
                if parent.revision_id != chunk.revision_id:
                    continue
                if not compatible_scope(parent, chunk):
                    raise ValueError("Invalid parent applicability")
                seen = {chunk.chunk_id}
                while parent is not None:
                    if parent.chunk_id in seen:
                        raise ValueError("Cyclic parent evidence")
                    seen.add(parent.chunk_id)
                    parent = by_id.get(parent.parent_chunk_id or "")
        body = snapshot_body(self.model_dump(mode="json", exclude={"version"}))
        if self.version != "kb-" + digest(canonical(body))[:16]:
            raise ValueError("Snapshot version does not match content")
        return self

    @property
    def pending(self) -> bool:
        return any(s.verification_status == "pending" for s in self.sources) or any(
            c.verification_status == "pending" for c in self.chunks
        )


def compatible_scope(left: RagChunk, right: RagChunk) -> bool:
    """A universal rule can have a scoped exception; disjoint scopes cannot share context."""
    return all("all" in a or "all" in b or bool(set(a) & set(b)) for a, b in (
        (left.campuses, right.campuses), (left.audiences, right.audiences),
    )) and (not left.academic_year or not right.academic_year
            or left.academic_year == right.academic_year)


def snapshot_body(body: dict[str, Any]) -> dict[str, Any]:
    """Hash body; optional fields at their default are omitted so older versions keep IDs."""
    for chunk in body["chunks"]:
        for flag in ("stale", "ocr"):
            if chunk.get(flag) is False:
                del chunk[flag]
        if body["schema_version"] == 1:
            for name, default in V2_CHUNK_DEFAULTS.items():
                if chunk.get(name, default) != default:
                    raise ValueError("Enriched evidence requires snapshot schema v2")
                chunk.pop(name, None)
    return body


V2_CHUNK_DEFAULTS: dict[str, Any] = {
    "document_id": None, "revision_id": None, "campuses": ["unknown"],
    "section_id": None, "parent_chunk_id": None, "heading_path": [],
    "clause_number": None, "conditions": [], "exceptions": [],
    "applicability_evidence": {}, "table_headers": [], "footnotes": [],
}


def make_snapshot(
    sources: tuple[RagSource, ...], chunks: tuple[RagChunk, ...], package_hash: str
) -> KnowledgeSnapshot:
    body = {
        "schema_version": 2 if any(
            any(c.model_dump(mode="json")[key] != default
                for key, default in V2_CHUNK_DEFAULTS.items()) for c in chunks
        ) else 1,
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
    campus: str = "chengdu"


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
    vector search disabled and hybrid degrades to BM25. Invalid new snapshots preserve
    the last successful retriever. Cold recovery uses only ``last_good.json``, whose
    explicit location and hashes are checked; it never guesses a version from disk.
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
        if bundled and not re.fullmatch(r"approved-\d{8}[a-z]?", bundled):
            raise ValueError("Invalid bundled knowledge name")
        self.bundled = bundled
        self.retrieval_mode = retrieval_mode
        self.embedder = embedder
        self.embedding_model = embedding_model
        self.index_error = ""
        self.load_error = ""
        self._cached: HybridRetriever | None = None
        self._key = ""
        self._had_current = False
        self._application_snapshot: tuple[HybridRetriever | None] | None = None
        # A tuple distinguishes a pinned empty store from no request scope. ContextVar
        # isolates concurrent requests and follows asyncio.to_thread's copied context.
        self._pinned: ContextVar[tuple[HybridRetriever | None] | None] = ContextVar(
            "campuspilot_snapshot_pin", default=None
        )

    @contextmanager
    def pin(self, retriever: HybridRetriever | None) -> Iterator[None]:
        """Keep one acquired version for this request; reload checks resume on exit."""
        token = self._pinned.set((retriever,))
        try:
            yield
        finally:
            self._pinned.reset(token)

    def acquire(self) -> HybridRetriever | None:
        pinned = self._pinned.get()
        if pinned is not None:
            return pinned[0]
        if self._application_snapshot is not None:
            return self._application_snapshot[0]
        pointer = self.root / "current.json"
        fallback = self.root / "last_good.json"
        try:
            if pointer.is_symlink():
                raise ValueError("Unsafe active knowledge pointer")
            if pointer.exists():
                self._had_current = True
                raw = json.loads(pointer.read_bytes())
                if not isinstance(raw, dict) or raw.get("kind", "published") != "published":
                    raise ValueError("Invalid active knowledge pointer")
                result = self._load_reference(raw)
            elif self._had_current and self._cached is not None:
                self.load_error = "Knowledge load failed (FileNotFoundError)"
                return self._cached
            elif fallback.exists():
                if fallback.is_symlink():
                    raise ValueError("Unsafe fallback pointer")
                result = self._load_reference(json.loads(fallback.read_bytes()), recovery=True)
            elif self.bundled:
                result = self._load_reference({"kind": "bundled", "bundle": self.bundled})
            else:
                if not (self.root / "bootstrap.json").exists():
                    return self._cached
                result = self._load_reference({"kind": "bootstrap"})
            self.load_error = ""
            return result
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            self.load_error = f"Knowledge load failed ({type(exc).__name__})"
            if self._cached is not None:
                return self._cached
            if (pointer.exists() or pointer.is_symlink()) and fallback.exists():
                try:
                    if fallback.is_symlink():
                        raise ValueError("Unsafe fallback pointer")
                    return self._load_reference(json.loads(fallback.read_bytes()), recovery=True)
                except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
                    pass
            raise

    def bind_directory(self, base: Path) -> Path:
        """Bind the application directory and RAG together until the next app restart.

        Standalone stores retain hot reload. An application cannot combine a newly
        published index with the previous process's already-loaded structured tools.
        """
        reader = self.acquire()
        self._application_snapshot = (reader,)
        if reader is None:
            return base
        version = self.root / "versions" / reader.snapshot.version
        manifest_path = version / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_bytes())
            if manifest.get("directory_binding"):
                return version / "directory"
        return base

    def _load_reference(
        self, raw: dict[str, Any], *, recovery: bool = False
    ) -> HybridRetriever:
        from campuspilot.knowledge_release import load_candidate_index, read_candidate
        from campuspilot.retrieval.hybrid import HybridRetriever
        from campuspilot.retrieval.vector import INDEX_NAME, VectorIndex
        from campuspilot.service_links import load_link_catalog

        if not isinstance(raw, dict) or (recovery and "kind" not in raw):
            raise ValueError("Invalid knowledge reference")
        kind = raw.get("kind", "published")
        if kind == "published" or recovery:
            if not isinstance(raw.get("sha256"), str) or not re.fullmatch(
                r"[a-f0-9]{64}", raw["sha256"]
            ):
                raise ValueError("Invalid knowledge checksum")
            if not isinstance(raw.get("version"), str) or not re.fullmatch(
                r"kb-[a-f0-9]{16}", raw["version"]
            ):
                raise ValueError("Invalid knowledge pointer")
        if kind == "published":
            version = raw["version"]
            path = self.root / "versions" / version / "snapshot.json"
            index_path = path.parent / INDEX_NAME
        elif kind == "bundled":
            bundle = raw.get("bundle")
            if not isinstance(bundle, str) or not re.fullmatch(r"approved-\d{8}[a-z]?", bundle):
                raise ValueError("Invalid bundled knowledge pointer")
            path = self.root / bundle / "snapshot.json"
            index_path = path.parent / INDEX_NAME
        elif kind == "bootstrap":
            path = self.root / "bootstrap.json"
            index_path = self.root / ("bootstrap." + INDEX_NAME)
        else:
            raise ValueError("Invalid knowledge reference kind")
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("Unsafe knowledge reference path")
        if kind == "bootstrap" and path.is_symlink():
            raise ValueError("Unsafe bootstrap path")
        data = path.read_bytes()
        snapshot_hash = digest(data)
        if len(data) > 20_000_000 or (
            (kind == "published" or recovery) and snapshot_hash != raw["sha256"]
        ):
            raise ValueError("Knowledge snapshot checksum mismatch")
        manifest = None
        manifest_hash = "bootstrap"
        if kind != "bootstrap":
            manifest_data = (path.parent / "manifest.json").read_bytes()
            manifest_hash = digest(manifest_data)
            if (recovery or "manifest_sha256" in raw) and (
                manifest_hash != raw.get("manifest_sha256")
            ):
                raise ValueError("Knowledge manifest checksum mismatch")
            snapshot = read_candidate(path.parent, check_index=False)
            manifest = json.loads(manifest_data)
        else:
            snapshot = KnowledgeSnapshot.model_validate_json(data)
        if snapshot.pending:
            raise ValueError("Pending knowledge cannot be served")
        if (kind == "published" or recovery) and snapshot.version != raw["version"]:
            raise ValueError("Knowledge pointer version mismatch")
        index = None
        self.index_error = ""
        index_hash = "lexical"
        if self.retrieval_mode != "lexical":
            try:
                if index_path.is_symlink() or not index_path.resolve().is_relative_to(
                    self.root.resolve()
                ):
                    raise ValueError("Unsafe index path")
                index_hash = digest(index_path.read_bytes())
                key = snapshot_hash + ":" + manifest_hash + ":" + index_hash
                if self._cached is not None and key == self._key:
                    return self._cached
                if manifest is None:
                    index = VectorIndex.load(index_path, snapshot, self.embedding_model)
                else:
                    index = load_candidate_index(
                        path.parent, snapshot, manifest, model=self.embedding_model
                    )
            except (
                OSError, ValueError, sqlite3.Error, struct.error, TypeError, OverflowError
            ) as exc:
                self.index_error = str(exc)
                index_hash = "degraded"
        key = snapshot_hash + ":" + manifest_hash + ":" + index_hash
        if self._cached is not None and key == self._key:
            if index is not None:
                index.close()
            return self._cached
        embedder = self.embedder
        retriever = HybridRetriever(
            snapshot,
            mode=self.retrieval_mode,  # type: ignore[arg-type]
            index=index,
            query_vector=embedder.cached if embedder is not None else None,
            service_links=load_link_catalog(path.parent, snapshot, manifest)
            if manifest is not None else None,
        )
        self._cached = retriever
        self._key = key
        return retriever


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
