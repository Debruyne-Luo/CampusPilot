"""Vector index bound to one knowledge snapshot, stored as a single SQLite file.

The file records the snapshot version, embedding model and dimensions, and per chunk its
`text_sha256`; loading rejects any mismatch so a stale index can never serve another
version. Queries use sqlite-vec when the extension loads, else numpy, else pure Python.
"""

from __future__ import annotations

import math
import os
import sqlite3
import struct
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from campuspilot.rag import KnowledgeSnapshot, RetrievalFilters, RetrievalHit
from campuspilot.retrieval.bm25 import eligible_chunks

INDEX_NAME = "vectors.sqlite"
Backend = Literal["sqlite-vec", "numpy", "python"]


def pack(vector: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def chunk_text(title: str, aliases: str, text: str) -> str:
    """The exact text embedded for a chunk (title and aliases carry key terms)."""
    return "\n".join(part for part in (title, aliases, text) if part)


def build_index(
    path: Path,
    snapshot: KnowledgeSnapshot,
    embed: Callable[[Sequence[str]], list[list[float]]],
    model: str,
    dimensions: int,
) -> int:
    """Embed every chunk and atomically write the index file; returns row count."""
    chunks = list(snapshot.chunks)
    vectors = embed([chunk_text(c.title, c.aliases, c.text) for c in chunks]) if chunks else []
    if len(vectors) != len(chunks) or any(len(v) != dimensions for v in vectors):
        raise ValueError("Embedding count or dimension mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".vectors-", suffix=".sqlite", dir=path.parent)
    os.close(fd)
    try:
        with sqlite3.connect(temporary) as conn:
            conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute(
                "CREATE TABLE vectors (chunk_id TEXT PRIMARY KEY, text_sha256 TEXT NOT NULL,"
                " embedding BLOB NOT NULL)"
            )
            conn.executemany(
                "INSERT INTO meta VALUES (?, ?)",
                [
                    ("knowledge_version", snapshot.version),
                    ("embedding_model", model),
                    ("dimensions", str(dimensions)),
                ],
            )
            conn.executemany(
                "INSERT INTO vectors VALUES (?, ?, ?)",
                [
                    (c.chunk_id, c.text_sha256, pack(v))
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )
        conn.close()
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return len(chunks)


def _load_sqlite_vec(conn: sqlite3.Connection) -> bool:
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except (ImportError, AttributeError, sqlite3.Error):
        return False


class VectorIndex:
    def __init__(
        self,
        snapshot: KnowledgeSnapshot,
        vectors: dict[str, list[float]],
        model: str,
        dimensions: int,
        conn: sqlite3.Connection | None = None,
        backend: Backend = "python",
    ) -> None:
        self.snapshot = snapshot
        self.sources = {s.source_id: s for s in snapshot.sources}
        self.vectors = vectors
        self.model = model
        self.dimensions = dimensions
        self._conn = conn
        self.backend: Backend = backend
        self._norms = {k: math.sqrt(sum(x * x for x in v)) or 1.0 for k, v in vectors.items()}

    @classmethod
    def load(
        cls,
        path: Path,
        snapshot: KnowledgeSnapshot,
        model: str,
        prefer: Backend | None = None,
    ) -> VectorIndex:
        if not path.is_file() or path.is_symlink():
            raise ValueError("Vector index missing")
        conn = sqlite3.connect(
            "file:" + quote(str(path), safe=":/\\") + "?mode=ro", uri=True, check_same_thread=False
        )
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        if meta.get("knowledge_version") != snapshot.version:
            raise ValueError("Vector index bound to another knowledge version")
        if meta.get("embedding_model") != model:
            raise ValueError("Vector index built with another embedding model")
        dimensions = int(meta.get("dimensions", "0"))
        hashes = {c.chunk_id: c.text_sha256 for c in snapshot.chunks}
        vectors: dict[str, list[float]] = {}
        for chunk_id, text_hash, blob in conn.execute(
            "SELECT chunk_id, text_sha256, embedding FROM vectors"
        ):
            if hashes.get(chunk_id) != text_hash:
                raise ValueError("Vector index does not match approved chunk bodies")
            vector = unpack(blob)
            if len(vector) != dimensions:
                raise ValueError("Vector dimension mismatch")
            vectors[chunk_id] = vector
        if set(vectors) != set(hashes):
            raise ValueError("Vector index does not cover the snapshot")
        backend: Backend = "python"
        if prefer in (None, "sqlite-vec") and _load_sqlite_vec(conn):
            backend = "sqlite-vec"
        elif prefer in (None, "numpy"):
            try:
                import numpy  # noqa: F401

                backend = "numpy"
            except ImportError:
                backend = "python"
        if backend != "sqlite-vec":
            conn.close()
            return cls(snapshot, vectors, model, dimensions, None, backend)
        return cls(snapshot, vectors, model, dimensions, conn, backend)

    def close(self) -> None:
        """Release SQLite handles after a reader is no longer used (not during a turn)."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self.backend = "python"

    def similarities(self, query: Sequence[float], ids: Sequence[str]) -> dict[str, float]:
        if len(query) != self.dimensions:
            raise ValueError("Query dimension mismatch")
        if not ids:
            return {}
        if self.backend == "sqlite-vec" and self._conn is not None:
            marks = ",".join("?" * len(ids))
            rows = self._conn.execute(
                "SELECT chunk_id, vec_distance_cosine(embedding, ?) FROM vectors"
                f" WHERE chunk_id IN ({marks})",
                (pack(query), *ids),
            ).fetchall()
            return {str(k): 1.0 - float(d) for k, d in rows}
        if self.backend == "numpy":
            import numpy as np

            matrix = np.asarray([self.vectors[i] for i in ids], dtype=np.float32)
            q = np.asarray(query, dtype=np.float32)
            norms = np.linalg.norm(matrix, axis=1) * (float(np.linalg.norm(q)) or 1.0)
            scores = matrix @ q / np.where(norms == 0, 1.0, norms)
            return {i: float(s) for i, s in zip(ids, scores, strict=True)}
        q_norm = math.sqrt(sum(x * x for x in query)) or 1.0
        return {
            i: sum(a * b for a, b in zip(self.vectors[i], query, strict=True))
            / (self._norms[i] * q_norm)
            for i in ids
        }

    def search(
        self,
        query_vector: Sequence[float],
        filters: RetrievalFilters,
        top_k: int = 12,
        min_similarity: float = 0.35,
    ) -> tuple[RetrievalHit, ...]:
        if not 1 <= top_k <= 100:
            raise ValueError("Invalid candidate limit")
        chunks = {c.chunk_id: c for c in eligible_chunks(self.snapshot, self.sources, filters)}
        scores = self.similarities(query_vector, sorted(chunks))
        hits = [
            RetrievalHit(
                knowledge_version=self.snapshot.version,
                chunk=chunks[i],
                source=self.sources[chunks[i].source_id],
                score=s,
            )
            for i, s in scores.items()
            if s >= min_similarity
        ]
        return tuple(sorted(hits, key=lambda h: (-h.score, h.chunk.chunk_id))[:top_k])
