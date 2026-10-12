"""P2 hybrid retrieval: BM25, vector index binding, RRF fusion, embeddings (network mocked)."""

import asyncio
import hashlib
import json
import sqlite3
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import httpx
import pytest
from campuspilot.config import Settings
from campuspilot.knowledge_release import embed_candidate, publish, read_candidate, write_candidate
from campuspilot.llm.embedding import CloudflareEmbedder, EmbeddingUnavailable
from campuspilot.rag import KnowledgeSnapshot, LexicalRetriever, RetrievalFilters, SnapshotStore
from campuspilot.retrieval.bm25 import BM25Retriever
from campuspilot.retrieval.hybrid import HybridRetriever, rrf
from campuspilot.retrieval.vector import INDEX_NAME, VectorIndex, build_index, chunk_text

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"
SNAPSHOT = KnowledgeSnapshot.model_validate_json((DATA / "rag/bootstrap.json").read_bytes())
TODAY = RetrievalFilters(today=date(2026, 10, 11))
MODEL = "synthetic-embedding-model"
DIMS = 8
ACCOUNT = "0123456789abcdef"
TOKEN = "synthetic-token-never-real"


def fake_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    return [b / 255 - 0.5 for b in digest[:DIMS]]


def fake_embed(texts: Sequence[str]) -> list[list[float]]:
    return [fake_vector(t) for t in texts]


def built_index(tmp_path: Path) -> Path:
    path = tmp_path / INDEX_NAME
    assert build_index(path, SNAPSHOT, fake_embed, MODEL, DIMS) == len(SNAPSHOT.chunks)
    return path


def chunk_vector(chunk_id: str) -> list[float]:
    chunk = next(c for c in SNAPSHOT.chunks if c.chunk_id == chunk_id)
    return fake_vector(chunk_text(chunk.title, chunk.aliases, chunk.text))


# --- BM25 -------------------------------------------------------------------------------


def test_lexical_alias_is_bm25_and_ranks_matching_title_first() -> None:
    assert LexicalRetriever is BM25Retriever
    hits = BM25Retriever(SNAPSHOT).search("学生邮箱激活步骤", TODAY, 5)
    assert hits and "邮箱" in hits[0].chunk.title
    assert all(a.score >= b.score for a, b in zip(hits, hits[1:], strict=False))
    assert BM25Retriever(SNAPSHOT).search("你好谢谢", TODAY) == ()
    with pytest.raises(ValueError):
        BM25Retriever(SNAPSHOT).search("x", TODAY, 0)


def test_bm25_applies_hard_filters() -> None:
    retriever = BM25Retriever(SNAPSHOT)
    for audience in ("undergraduate", "graduate"):
        filters = RetrievalFilters(today=date(2026, 10, 11), audience=audience)
        for hit in retriever.search("证明 申请 成绩", filters, 50):
            assert "all" in hit.chunk.audiences or audience in hit.chunk.audiences
    for hit in retriever.search("寒假 开放 时间", TODAY, 50):
        assert hit.chunk.kind not in {"historical", "deprecated"}


# --- RRF --------------------------------------------------------------------------------


def test_rrf_fuses_by_reciprocal_rank() -> None:
    a = BM25Retriever(SNAPSHOT).search("图书馆", TODAY, 3)
    assert len(a) == 3
    fused = rrf([a, tuple(reversed(a))], k=60)
    expected = {h.chunk.chunk_id: 0.0 for h in a}
    for ranking in (a, tuple(reversed(a))):
        for rank, hit in enumerate(ranking, start=1):
            expected[hit.chunk.chunk_id] += 1 / (60 + rank)
    assert {h.chunk.chunk_id: h.score for h in fused} == pytest.approx(expected)
    single = rrf([a])
    assert [h.chunk.chunk_id for h in single] == [h.chunk.chunk_id for h in a]


# --- Vector index binding ----------------------------------------------------------------


@pytest.mark.parametrize("backend", ["sqlite-vec", "numpy", "python"])
def test_vector_backends_agree_and_find_exact_chunk(tmp_path: Path, backend: str) -> None:
    index = VectorIndex.load(built_index(tmp_path), SNAPSHOT, MODEL, prefer=backend)  # type: ignore[arg-type]
    assert index.backend == backend
    target = next(c.chunk_id for c in SNAPSHOT.chunks if c.enabled and "all" in c.audiences)
    hits = index.search(chunk_vector(target), TODAY, 5, min_similarity=-1)
    assert hits[0].chunk.chunk_id == target and hits[0].score == pytest.approx(1, abs=1e-5)


def test_vector_index_rejects_other_version_model_or_changed_body(tmp_path: Path) -> None:
    path = built_index(tmp_path)
    with pytest.raises(ValueError):
        VectorIndex.load(path, SNAPSHOT, "other-model")
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE meta SET value='kb-0000000000000000' WHERE key='knowledge_version'")
    conn.close()
    with pytest.raises(ValueError):
        VectorIndex.load(path, SNAPSHOT, MODEL)
    path = built_index(tmp_path / "b")
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE vectors SET text_sha256='x' WHERE rowid=1")
    conn.close()
    with pytest.raises(ValueError):
        VectorIndex.load(path, SNAPSHOT, MODEL)
    with pytest.raises(ValueError):
        VectorIndex.load(tmp_path / "missing.sqlite", SNAPSHOT, MODEL)
    with pytest.raises(ValueError):
        build_index(tmp_path / "c.sqlite", SNAPSHOT, lambda t: [[0.0]] * len(t), MODEL, DIMS)


# --- Hybrid -----------------------------------------------------------------------------


def test_hybrid_modes_and_degradation(tmp_path: Path) -> None:
    index = VectorIndex.load(built_index(tmp_path), SNAPSHOT, MODEL)
    target = next(c for c in SNAPSHOT.chunks if "邮箱" in c.title)
    query = "学生邮箱激活步骤"
    vec = chunk_vector(target.chunk_id)
    lexical = HybridRetriever(SNAPSHOT, "lexical", index).search(query, TODAY, 5)
    assert lexical == BM25Retriever(SNAPSHOT).search(query, TODAY, 5)
    vector = HybridRetriever(SNAPSHOT, "vector", index).search(query, TODAY, 5, query_vector=vec)
    assert vector[0].chunk.chunk_id == target.chunk_id
    hybrid = HybridRetriever(SNAPSHOT, "hybrid", index)
    fused = hybrid.search(query, TODAY, 5, query_vector=vec)
    assert fused[0].chunk.chunk_id == target.chunk_id and not hybrid.degraded
    # No vector (cache miss / provider failure): BM25 only, flagged degraded.
    assert hybrid.search(query, TODAY, 5) == lexical and hybrid.degraded

    def failing(_: str) -> list[float]:
        raise EmbeddingUnavailable("unavailable")

    broken = HybridRetriever(SNAPSHOT, "hybrid", index, query_vector=failing)
    assert broken.search(query, TODAY, 5) == lexical and broken.degraded
    with pytest.raises(ValueError):
        HybridRetriever(SNAPSHOT, "other")


def test_hard_filters_apply_before_fusion(tmp_path: Path) -> None:
    index = VectorIndex.load(built_index(tmp_path), SNAPSHOT, MODEL)
    restricted = [c for c in SNAPSHOT.chunks if "all" not in c.audiences]
    if not restricted:
        pytest.skip("snapshot has no audience-restricted chunk")
    chunk = restricted[0]
    other = next(a for a in ("undergraduate", "graduate", "staff") if a not in chunk.audiences)
    filters = RetrievalFilters(today=date(2026, 10, 11), audience=other)
    hits = HybridRetriever(SNAPSHOT, "hybrid", index).search(
        chunk.title, filters, 20, query_vector=chunk_vector(chunk.chunk_id)
    )
    assert chunk.chunk_id not in {h.chunk.chunk_id for h in hits}


# --- Embedding client (mocked network) ----------------------------------------------------


def cf_reply(texts: list[str], dims: int = 1024) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "success": True,
            "result": {"shape": [len(texts), dims], "data": [[0.1] * dims for _ in texts]},
        },
    )


def test_embedder_success_cache_retry_and_errors() -> None:
    calls: list[httpx.Request] = []
    statuses = [500, 200]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        status = statuses.pop(0) if statuses else 200
        if status != 200:
            return httpx.Response(status)
        return cf_reply(json.loads(request.content)["text"])

    embedder = CloudflareEmbedder(ACCOUNT, TOKEN, transport=httpx.MockTransport(handler))
    assert TOKEN not in repr(embedder) and ACCOUNT not in repr(embedder)
    vector = embedder.embed_query("校园卡补办")
    assert len(vector) == 1024 and len(calls) == 2  # one retry after 500
    assert calls[0].headers["Authorization"] == "Bearer " + TOKEN
    assert str(calls[0].url).endswith(f"/accounts/{ACCOUNT}/ai/run/@cf/baai/bge-m3")
    assert embedder.embed_query("校园卡补办") == vector and len(calls) == 2  # cached
    assert embedder.cached(" 校园卡补办 ") == vector

    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=TOKEN)

    bad = CloudflareEmbedder(ACCOUNT, TOKEN, transport=httpx.MockTransport(unauthorized))
    with pytest.raises(EmbeddingUnavailable) as exc:
        bad.embed(["x"])
    assert TOKEN not in str(exc.value)

    def wrong_dims(request: httpx.Request) -> httpx.Response:
        return cf_reply(["x"], dims=3)

    with pytest.raises(EmbeddingUnavailable):
        CloudflareEmbedder(ACCOUNT, TOKEN, transport=httpx.MockTransport(wrong_dims)).embed(["x"])
    with pytest.raises(ValueError):
        CloudflareEmbedder("", TOKEN)
    with pytest.raises(ValueError):
        CloudflareEmbedder("../evil", TOKEN)


def test_embedder_lru_and_batching() -> None:
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["text"]
        sizes.append(len(texts))
        return cf_reply(texts)

    embedder = CloudflareEmbedder(
        ACCOUNT, TOKEN, cache_size=2, transport=httpx.MockTransport(handler)
    )
    assert len(embedder.embed([f"t{i}" for i in range(120)])) == 120 and sizes == [50, 50, 20]
    for text in ("a", "b", "c"):
        embedder.embed_query(text)
    assert embedder.cached("a") is None and embedder.cached("c") is not None


def test_async_prefetch_fills_cache_and_fails_soft() -> None:
    async def ok(request: httpx.Request) -> httpx.Response:
        return cf_reply(json.loads(request.content)["text"])

    async def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("synthetic")

    good = CloudflareEmbedder(ACCOUNT, TOKEN, async_transport=httpx.MockTransport(ok))
    assert asyncio.run(good.prefetch("图书馆")) is not None and good.cached("图书馆")
    bad = CloudflareEmbedder(ACCOUNT, TOKEN, retries=1, async_transport=httpx.MockTransport(down))
    assert asyncio.run(bad.prefetch("图书馆")) is None and bad.cached("图书馆") is None


# --- Release binding and store ----------------------------------------------------------------


def test_embed_candidate_publishes_index_atomically_with_snapshot(tmp_path: Path) -> None:
    candidate, store = tmp_path / "candidate", tmp_path / "store"
    write_candidate(candidate, SNAPSHOT)
    assert embed_candidate(candidate, fake_embed, MODEL, DIMS) == len(SNAPSHOT.chunks)
    manifest = json.loads((candidate / "manifest.json").read_bytes())
    assert INDEX_NAME in manifest["files_sha256"] and manifest["vector_index"]["model"] == MODEL
    read_candidate(candidate)
    version = publish(candidate, store, None)
    assert (store / "versions" / version / INDEX_NAME).is_file()
    snapshots = SnapshotStore(store, retrieval_mode="hybrid", embedding_model=MODEL)
    retriever = snapshots.acquire()
    assert retriever is not None and retriever.index is not None and not snapshots.index_error
    # Tampering with the published index is caught by the candidate checksum.
    (candidate / INDEX_NAME).write_bytes(b"tampered")
    with pytest.raises(ValueError):
        read_candidate(candidate)


def test_snapshot_store_without_index_degrades(tmp_path: Path) -> None:
    store = tmp_path / "rag"
    store.mkdir()
    (store / "bootstrap.json").write_bytes((DATA / "rag/bootstrap.json").read_bytes())
    snapshots = SnapshotStore(store, retrieval_mode="hybrid", embedding_model=MODEL)
    retriever = snapshots.acquire()
    assert retriever is not None and retriever.index is None and snapshots.index_error
    assert retriever.search("学生邮箱激活", TODAY, 3) and retriever.degraded
    lexical = SnapshotStore(store).acquire()
    assert lexical is not None and lexical.mode == "lexical"


def test_committed_bootstrap_index_matches_snapshot() -> None:
    index = VectorIndex.load(
        DATA / "rag" / ("bootstrap." + INDEX_NAME), SNAPSHOT, "@cf/baai/bge-m3"
    )
    assert index.dimensions == 1024 and set(index.vectors) == {c.chunk_id for c in SNAPSHOT.chunks}


# --- Settings, tool and web wiring --------------------------------------------------------------


def test_settings_retrieval_fields_are_masked() -> None:
    settings = Settings.from_env(
        {"CF_ACCOUNT_ID": ACCOUNT, "CF_API_TOKEN": TOKEN, "CAMPUSPILOT_RETRIEVAL_MODE": "vector"}
    )
    assert settings.retrieval_mode == "vector" and settings.embeddings_configured
    assert TOKEN not in repr(settings) and ACCOUNT not in repr(settings)
    assert Settings.from_env({}).retrieval_mode == "hybrid"
    with pytest.raises(ValueError):
        Settings.from_env({"CAMPUSPILOT_RETRIEVAL_MODE": "dense"})


def test_search_knowledge_tool_uses_hybrid_snapshot() -> None:
    from campuspilot.directory.repository import DirectoryRepository
    from campuspilot.knowledge import KnowledgeStore
    from campuspilot.tools import default_registry

    index = VectorIndex.load(
        DATA / "rag" / ("bootstrap." + INDEX_NAME), SNAPSHOT, "@cf/baai/bge-m3"
    )
    target = next(c for c in SNAPSHOT.chunks if "邮箱" in c.title)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"success": True, "result": {"data": [index.vectors[target.chunk_id]]}}
        )

    embedder = CloudflareEmbedder(ACCOUNT, TOKEN, transport=httpx.MockTransport(handler))
    registry = default_registry(
        DirectoryRepository.load(DATA),
        KnowledgeStore.load(DATA / "knowledge.json"),
        SnapshotStore(DATA / "rag", retrieval_mode="hybrid", embedder=embedder),
        embedder,
    )
    result = registry.call("search_knowledge", {"query": "学生邮箱怎么激活"})
    assert result["result_status"] == "success" and result["retrieval_mode"] == "hybrid"
    assert result["degraded"] is False and result["knowledge_version"] == SNAPSHOT.version
    hits = result["hits"]
    assert isinstance(hits, list) and isinstance(hits[0], dict)
    assert hits[0]["chunk_id"] == target.chunk_id and str(hits[0]["url"]).startswith("https://")


def test_phase2_chat_prefetches_embedding_and_survives_provider_outage() -> None:
    from campuspilot.web import create_web_app
    from fastapi.testclient import TestClient

    headers = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}
    seen: list[str] = []

    async def down(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["text"][0])
        return httpx.Response(503)

    embedder = CloudflareEmbedder(
        ACCOUNT, TOKEN, retries=0, async_transport=httpx.MockTransport(down)
    )
    app = create_web_app(data_dir=DATA, runtime_mode="phase2", embedder=embedder)
    with TestClient(app) as client:
        client.post("/api/session", headers=headers)
        response = client.post("/api/chat", json={"message": "学生邮箱怎么激活"}, headers=headers)
        assert response.status_code == 200 and response.json()["result_status"] == "limited"
        assert TOKEN not in response.text
    assert seen == ["学生邮箱怎么激活"]
