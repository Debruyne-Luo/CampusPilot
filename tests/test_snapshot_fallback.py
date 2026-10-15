"""Synthetic fault cases for explicit, hash-bound last-success recovery."""

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import pytest
from campuspilot.knowledge_release import (
    atomic_write,
    current_version,
    embed_candidate,
    publish,
    read_candidate,
    rollback,
    write_candidate,
)
from campuspilot.rag import (
    KnowledgeSnapshot,
    RagChunk,
    RagSource,
    RetrievalFilters,
    SnapshotStore,
    canonical,
    digest,
    make_snapshot,
)
from campuspilot.retrieval.vector import INDEX_NAME


def synthetic_snapshot(label: str = "one", *, pending: bool = False) -> KnowledgeSnapshot:
    status: Literal["pending", "official_document"] = "pending" if pending else "official_document"
    source = RagSource(
        source_id="SYNTHETIC:source",
        title="SYNTHETIC fixture",
        url="https://www.cdut.edu.cn/SYNTHETIC-fixture",
        publisher="SYNTHETIC fixture publisher",
        applicability="SYNTHETIC graduate fixture",
        temporal_status="current",
        verification_status=status,
        reviewer="" if pending else "SYNTHETIC fixture validator",
        verified_at=None if pending else date(2026, 10, 14),
    )
    text = "SYNTHETIC graduate guideline " + label
    chunk = RagChunk(
        chunk_id="SYNTHETIC:clause",
        source_id=source.source_id,
        topic_id="SYNTHETIC",
        title="SYNTHETIC graduate guideline",
        text=text,
        locator="SYNTHETIC paragraph 1",
        text_sha256=digest(text.encode()),
        verification_status=status,
        reviewer=source.reviewer,
        verified_at=source.verified_at,
        approval_id="SYNTHETIC approval",
        audiences=("graduate",),
        academic_year="2026-2027",
        valid_from=date(2026, 10, 14),
        valid_until=date(2026, 10, 15),
    )
    return make_snapshot((source,), (chunk,), digest(label.encode()))


def publish_pair(tmp_path: Path) -> tuple[Path, KnowledgeSnapshot, KnowledgeSnapshot]:
    root = tmp_path / "store"
    first, second = synthetic_snapshot(), synthetic_snapshot("two")
    for value in (first, second):
        candidate = tmp_path / value.version
        write_candidate(candidate, value, {"SYNTHETIC.txt": b"SYNTHETIC evidence"})
        publish(candidate, root, None if value == first else first.version)
    return root, first, second


@pytest.mark.parametrize(
    "fault", ["json", "shape", "version", "checksum", "body", "evidence", "manifest_shape"]
)
def test_hot_invalid_new_snapshot_keeps_last_success(tmp_path: Path, fault: str) -> None:
    root, first, second = publish_pair(tmp_path)
    rollback(root, first.version, second.version)
    store = SnapshotStore(root)
    good = store.acquire()
    assert good is not None and good.snapshot == first
    publish(root / "versions" / second.version, root, first.version)
    pointer = root / "current.json"
    if fault == "json":
        pointer.write_bytes(b"SYNTHETIC malformed JSON")
    elif fault == "shape":
        pointer.write_bytes(b"[]")
    elif fault in {"version", "checksum"}:
        raw = json.loads(pointer.read_bytes())
        raw["version" if fault == "version" else "sha256"] = "../SYNTHETIC"
        pointer.write_bytes(canonical(raw))
    elif fault == "manifest_shape":
        target = root / "versions" / second.version / "manifest.json"
        target.write_bytes(b"[]")
        raw = json.loads(pointer.read_bytes())
        raw.pop("manifest_sha256")  # Older pointers must still validate the full manifest.
        pointer.write_bytes(canonical(raw))
    else:
        target = root / "versions" / second.version
        (target / ("snapshot.json" if fault == "body" else "raw/SYNTHETIC.txt")).write_bytes(
            b"SYNTHETIC damaged evidence"
        )
    assert store.acquire() is good and store.load_error


@pytest.mark.parametrize("fault", ["pointer", "snapshot", "manifest", "missing_pointer"])
def test_cold_invalid_current_uses_only_explicit_last_good(tmp_path: Path, fault: str) -> None:
    root, first, second = publish_pair(tmp_path)
    if fault == "pointer":
        (root / "current.json").write_bytes(b"SYNTHETIC invalid")
    elif fault == "missing_pointer":
        (root / "current.json").unlink()
    else:
        (root / "versions" / second.version / (fault + ".json")).write_bytes(b"SYNTHETIC bad")
    store = SnapshotStore(root)
    acquired = store.acquire()
    assert acquired is not None and acquired.snapshot == first
    if fault != "missing_pointer":
        assert store.load_error


def test_cold_reader_never_scans_versions_or_trusts_pending_fallback(tmp_path: Path) -> None:
    root, first, second = publish_pair(tmp_path)
    (root / "current.json").write_bytes(b"SYNTHETIC invalid")
    (root / "last_good.json").unlink()
    with pytest.raises(ValueError):
        SnapshotStore(root).acquire()
    pending = synthetic_snapshot("pending", pending=True)
    directory = root / "versions" / pending.version
    write_candidate(directory, pending)
    fallback = {
        "kind": "published",
        "version": pending.version,
        "sha256": digest((directory / "snapshot.json").read_bytes()),
        "manifest_sha256": digest((directory / "manifest.json").read_bytes()),
    }
    (root / "last_good.json").write_bytes(canonical(fallback))
    with pytest.raises(ValueError):
        SnapshotStore(root).acquire()
    assert (root / "versions" / first.version).is_dir()
    assert (root / "versions" / second.version).is_dir()


def test_first_publication_records_explicit_bundled_fallback(tmp_path: Path) -> None:
    first, second = synthetic_snapshot(), synthetic_snapshot("two")
    bundle = tmp_path / "approved-20261014"
    candidate = tmp_path / "candidate"
    write_candidate(bundle, first)
    write_candidate(candidate, second)
    publish(candidate, tmp_path, None, fallback_bundle=bundle.name)
    fallback = json.loads((tmp_path / "last_good.json").read_bytes())
    assert fallback["kind"] == "bundled" and fallback["bundle"] == bundle.name
    (tmp_path / "versions" / second.version / "snapshot.json").write_bytes(b"SYNTHETIC bad")
    acquired = SnapshotStore(tmp_path).acquire()
    assert acquired is not None and acquired.snapshot == first


def test_hot_missing_pointer_keeps_current_in_memory(tmp_path: Path) -> None:
    root, _, second = publish_pair(tmp_path)
    store = SnapshotStore(root)
    acquired = store.acquire()
    assert acquired is not None and acquired.snapshot == second
    (root / "current.json").unlink()
    assert store.acquire() is acquired and store.load_error


def test_old_current_pointer_still_validates_non_index_evidence(tmp_path: Path) -> None:
    root, _, second = publish_pair(tmp_path)
    pointer = root / "current.json"
    raw = json.loads(pointer.read_bytes())
    raw.pop("kind")
    raw.pop("manifest_sha256")
    pointer.write_bytes(canonical(raw))
    store = SnapshotStore(root)
    acquired = store.acquire()
    assert acquired is not None and acquired.snapshot == second
    (root / "versions" / second.version / "raw/SYNTHETIC.txt").write_bytes(b"SYNTHETIC changed")
    assert store.acquire() is acquired and store.load_error
    cold = SnapshotStore(root).acquire()
    assert cold is not None and cold.snapshot.version != second.version


@pytest.mark.parametrize("fault", ["kind", "path", "snapshot_hash", "manifest_hash", "version"])
def test_cold_recovery_rejects_invalid_record_without_guessing(tmp_path: Path, fault: str) -> None:
    root, _, _ = publish_pair(tmp_path)
    (root / "current.json").write_bytes(b"SYNTHETIC invalid current")
    fallback = json.loads((root / "last_good.json").read_bytes())
    if fault == "kind":
        fallback["kind"] = "SYNTHETIC unsupported"
    elif fault == "path":
        fallback.update(kind="bundled", bundle="../SYNTHETIC")
    elif fault == "snapshot_hash":
        fallback["sha256"] = "0" * 64
    elif fault == "manifest_hash":
        fallback["manifest_sha256"] = "0" * 64
    else:
        fallback["version"] = "kb-" + "0" * 16
    (root / "last_good.json").write_bytes(canonical(fallback))
    with pytest.raises(ValueError):
        SnapshotStore(root).acquire()


@pytest.mark.parametrize("fault", ["missing", "corrupt", "wrong_binding", "binding_dimensions"])
@pytest.mark.parametrize("hot", [False, True])
def test_published_index_failure_keeps_body_and_degrades_to_bm25(
    tmp_path: Path, fault: str, hot: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    if hot:
        # Exercise the supported connection-free backend so files can be damaged on Windows.
        monkeypatch.setattr("campuspilot.retrieval.vector._load_sqlite_vec", lambda conn: False)
    value = synthetic_snapshot()
    candidate, root = tmp_path / "candidate", tmp_path / "store"
    write_candidate(candidate, value)
    embed_candidate(candidate, lambda texts: [[1.0, 0.0] for _ in texts], "SYNTHETIC-model", 2)
    publish(candidate, root, None)
    store = SnapshotStore(root, "hybrid", embedding_model="SYNTHETIC-model")
    cached = store.acquire() if hot else None
    if hot:
        assert cached is not None and cached.index is not None
    target = root / "versions" / value.version / INDEX_NAME
    if fault == "missing":
        target.unlink()
    elif fault == "corrupt":
        target.write_bytes(b"SYNTHETIC invalid sqlite")
    elif fault == "wrong_binding":
        with sqlite3.connect(target) as connection:
            connection.execute(
                "UPDATE meta SET value='SYNTHETIC wrong' WHERE key='knowledge_version'"
            )
    else:
        manifest_path = target.parent / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["vector_index"]["dimensions"] = 0
        manifest_path.write_bytes(canonical(manifest))
        pointer = json.loads((root / "current.json").read_bytes())
        pointer["manifest_sha256"] = digest(manifest_path.read_bytes())
        (root / "current.json").write_bytes(canonical(pointer))
    acquired = store.acquire()
    assert acquired is not None and acquired.snapshot == value and acquired.index is None
    assert acquired is not cached
    assert store.index_error and not store.load_error
    assert acquired.search("graduate guideline", RetrievalFilters(today=date(2026, 10, 14)))
    assert acquired.degraded


def test_manifest_hash_cannot_approve_an_index_for_another_snapshot(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate, synthetic_snapshot())
    embed_candidate(candidate, lambda texts: [[1.0, 0.0] for _ in texts], "SYNTHETIC-model", 2)
    with sqlite3.connect(candidate / INDEX_NAME) as connection:
        connection.execute("UPDATE meta SET value='SYNTHETIC wrong' WHERE key='knowledge_version'")
    manifest = json.loads((candidate / "manifest.json").read_bytes())
    manifest["files_sha256"][INDEX_NAME] = digest((candidate / INDEX_NAME).read_bytes())
    (candidate / "manifest.json").write_bytes(canonical(manifest))
    with pytest.raises(ValueError, match="another knowledge"):
        read_candidate(candidate)
    with pytest.raises(ValueError):
        publish(candidate, tmp_path / "store", None)
    assert current_version(tmp_path / "store") is None


def test_backup_failure_and_embedding_failure_do_not_switch_current(tmp_path: Path) -> None:
    root, first, second = publish_pair(tmp_path)
    before = (root / "current.json").read_bytes()

    def broken(path: Path, data: bytes, metadata: object = None) -> None:
        if path.name == "last_good.json":
            raise OSError("SYNTHETIC failed backup")
        atomic_write(path, data)

    with patch("campuspilot.knowledge_release.atomic_write", side_effect=broken):
        with pytest.raises(OSError):
            rollback(root, first.version, second.version)
    assert (root / "current.json").read_bytes() == before
    candidate = tmp_path / "embedding-failure"
    write_candidate(candidate, synthetic_snapshot("three"))
    with pytest.raises(ValueError):
        embed_candidate(candidate, lambda texts: [], "SYNTHETIC-model", 2)
    assert not (candidate / INDEX_NAME).exists()
    assert (root / "current.json").read_bytes() == before


def test_date_audience_and_academic_year_boundaries(tmp_path: Path) -> None:
    value = synthetic_snapshot()
    write_candidate(tmp_path / "candidate", value)
    publish(tmp_path / "candidate", tmp_path / "store", None)
    acquired = SnapshotStore(tmp_path / "store").acquire()
    assert acquired is not None
    for today, audience, year, expected in (
        (date(2026, 10, 13), "graduate", "2026-2027", False),
        (date(2026, 10, 14), "graduate", "2026-2027", True),
        (date(2026, 10, 15), "graduate", "2026-2027", True),
        (date(2026, 10, 16), "graduate", "2026-2027", False),
        (date(2026, 10, 14), "undergraduate", "2026-2027", False),
        (date(2026, 10, 14), "graduate", "2025-2026", False),
    ):
        hits = acquired.search(
            "graduate guideline",
            RetrievalFilters(today=today, audience=audience, academic_year=year),
        )
        assert bool(hits) is expected
        for hit in hits:
            assert hit.knowledge_version == value.version
            assert hit.chunk.locator == "SYNTHETIC paragraph 1"
