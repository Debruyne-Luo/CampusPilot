"""Retrieval tuning: colloquial expansion, stale down-weighting, weighted RRF, exclusions."""

import json
from datetime import date
from pathlib import Path

from campuspilot.rag import KnowledgeSnapshot, RetrievalFilters
from campuspilot.retrieval.bm25 import BM25Retriever, eligible, expand
from campuspilot.retrieval.hybrid import HybridRetriever, rrf

BUNDLE = Path(__file__).resolve().parents[1] / "data/cdut/rag/approved-20261011b"
TODAY = RetrievalFilters(today=date(2026, 10, 11))


def snapshot() -> KnowledgeSnapshot:
    return KnowledgeSnapshot.model_validate_json((BUNDLE / "snapshot.json").read_bytes())


def test_colloquial_expansion_appends_official_terms() -> None:
    assert expand("饭卡丢了咋冻结").startswith("饭卡丢了咋冻结") and "校园卡" in expand("饭卡丢了")
    assert expand("图书馆借书") == "图书馆借书"


def test_stale_facts_stay_candidates_but_historical_kinds_do_not() -> None:
    snap = snapshot()
    sources = {s.source_id: s for s in snap.sources}
    for chunk in snap.chunks:
        source = sources[chunk.source_id]
        ok = eligible(chunk, source, TODAY)
        if chunk.kind in {"historical", "deprecated"} or source.temporal_status == "superseded":
            assert not ok
        elif chunk.stale and source.temporal_status == "historical" and chunk.enabled:
            assert ok == (not chunk.valid_until or chunk.valid_until >= TODAY.today)
    hits = BM25Retriever(snap).search("宿舍空调欠费断电了", TODAY)
    assert hits and any(h.chunk.stale for h in hits[:3])


def test_stale_hits_are_downweighted() -> None:
    snap = snapshot()
    plain = HybridRetriever(snap, mode="lexical", stale_weight=1.0).search("军训服装费", TODAY)
    weighted = HybridRetriever(snap, mode="lexical", stale_weight=0.5).search("军训服装费", TODAY)
    stale = {h.chunk.chunk_id: h.score for h in plain if h.chunk.stale}
    assert stale
    for h in weighted:
        if h.chunk.chunk_id in stale:
            assert abs(h.score - 0.5 * stale[h.chunk.chunk_id]) < 1e-9


def test_weighted_rrf_prefers_the_heavier_ranking() -> None:
    hits = BM25Retriever(snapshot()).search("校园卡挂失", TODAY)[:2]
    a, b = hits[0], hits[1]
    assert rrf([[a, b], [b, a]], 10, (1.0, 1.25))[0].chunk.chunk_id == b.chunk.chunk_id
    assert rrf([[a, b], [b, a]], 10, (1.25, 1.0))[0].chunk.chunk_id == a.chunk.chunk_id


def test_excluded_package_chunks_never_reach_the_index() -> None:
    raw = [
        json.loads(line)
        for line in (BUNDLE / "raw/package/chunks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    excluded = {c["chunk_id"] for c in raw if c.get("excluded_from_retrieval")}
    ids = {c.chunk_id for c in snapshot().chunks}
    assert not excluded & ids
