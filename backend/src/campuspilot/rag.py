"""Versioned public evidence and small, provider-independent retrieval contracts."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

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
    verification_status: Literal["verified", "official_document"]
    reviewer: str
    verified_at: date

    @model_validator(mode="after")
    def source_scope(self) -> Self:
        official_url(self.url, wechat=True)
        if not all((self.source_id, self.title, self.publisher, self.reviewer)):
            raise ValueError("Incomplete source provenance")
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
    verification_status: Literal["verified", "official_document"]
    reviewer: str
    verified_at: date
    approval_id: str
    audiences: tuple[str, ...] = ("all",)
    academic_year: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def approved_content(self) -> Self:
        if digest(self.text.encode()) != self.text_sha256:
            raise ValueError("Changed body requires renewed review")
        if not all((self.chunk_id, self.locator, self.reviewer, self.approval_id)):
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
        body = self.model_dump(mode="json", exclude={"version"})
        if self.version != "kb-" + digest(canonical(body))[:16]:
            raise ValueError("Snapshot version does not match content")
        return self


def make_snapshot(
    sources: tuple[RagSource, ...], chunks: tuple[RagChunk, ...], package_hash: str
) -> KnowledgeSnapshot:
    body = {
        "schema_version": 1,
        "source_package_sha256": package_hash,
        "sources": [s.model_dump(mode="json") for s in sorted(sources, key=lambda s: s.source_id)],
        "chunks": [c.model_dump(mode="json") for c in sorted(chunks, key=lambda c: c.chunk_id)],
    }
    return KnowledgeSnapshot.model_validate_json(
        canonical({**body, "version": "kb-" + digest(canonical(body))[:16]})
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


def terms(text: str) -> Counter[str]:
    text = text.casefold()
    result: Counter[str] = Counter(re.findall(r"[a-z0-9]+", text))
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        for width in (2, 3):
            result.update(run[i : i + width] for i in range(len(run) - width + 1))
    return result


class LexicalRetriever:
    """Weighted n-gram TF/IDF, not a confidence score or full BM25."""

    def __init__(self, snapshot: KnowledgeSnapshot) -> None:
        self.snapshot = snapshot
        self.sources = {s.source_id: s for s in snapshot.sources}
        self.fields = {
            c.chunk_id: (terms(c.title + " " + c.aliases), terms(c.text)) for c in snapshot.chunks
        }
        self.df: Counter[str] = Counter()
        for title, body in self.fields.values():
            self.df.update(title.keys() | body.keys())

    def search(
        self, query: str, filters: RetrievalFilters, top_k: int = 12
    ) -> tuple[RetrievalHit, ...]:
        if not 1 <= top_k <= 100:
            raise ValueError("Invalid candidate limit")
        tokens = terms(query)
        for generic in ("请问", "如何", "怎么", "什么", "哪里", "你好", "谢谢", "是否"):
            for token in terms(generic):
                tokens.pop(token, None)
        found: list[RetrievalHit] = []
        for c in self.snapshot.chunks:
            source = self.sources[c.source_id]
            if not c.enabled:
                continue
            expired = bool(c.valid_until and c.valid_until < filters.today)
            historical = (
                c.kind in {"historical", "deprecated"}
                or source.temporal_status in {"historical", "superseded"}
                or expired
            )
            if historical and not filters.historical:
                continue
            if c.valid_from and c.valid_from > filters.today:
                continue
            if filters.current_only and (historical or source.temporal_status != "current"):
                continue
            if filters.audience != "all" and "all" not in c.audiences:
                if filters.audience not in c.audiences:
                    continue
            if filters.academic_year and c.academic_year not in (None, filters.academic_year):
                continue
            title, body = self.fields[c.chunk_id]
            score = sum(
                math.log(1 + (len(self.fields) - self.df[t] + 0.5) / (self.df[t] + 0.5))
                * min(qf, 2)
                * (3.4 * min(title[t], 3) + min(body[t], 3))
                for t, qf in tokens.items()
                if t in title or t in body
            )
            # Require useful overlap; a single generic character never triggers retrieval.
            matched = tokens.keys() & (title.keys() | body.keys())
            if score > 0.5 and matched:
                found.append(
                    RetrievalHit(
                        knowledge_version=self.snapshot.version, chunk=c, source=source, score=score
                    )
                )
        return tuple(sorted(found, key=lambda h: (-h.score, h.chunk.chunk_id))[:top_k])


class SnapshotStore:
    """Load immutable snapshots; a request holds one retriever through publication."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cached: LexicalRetriever | None = None
        self._key = ""

    def acquire(self) -> LexicalRetriever | None:
        pointer = self.root / "current.json"
        if pointer.exists():
            raw = json.loads(pointer.read_bytes())
            version = raw["version"]
            if not isinstance(version, str) or not re.fullmatch(r"kb-[a-f0-9]{16}", version):
                raise ValueError("Invalid knowledge pointer")
            path = self.root / "versions" / version / "snapshot.json"
            key = version + ":" + raw["sha256"]
        else:
            path = self.root / "bootstrap.json"
            if not path.exists():
                return None
            key = digest(path.read_bytes())
        if self._cached is not None and key == self._key:
            return self._cached
        data = path.read_bytes()
        if len(data) > 20_000_000 or (pointer.exists() and digest(data) != raw["sha256"]):
            raise ValueError("Knowledge snapshot checksum mismatch")
        snapshot = KnowledgeSnapshot.model_validate_json(data)
        if pointer.exists() and snapshot.version != version:
            raise ValueError("Knowledge pointer version mismatch")
        self._cached = LexicalRetriever(snapshot)
        self._key = key
        return self._cached
