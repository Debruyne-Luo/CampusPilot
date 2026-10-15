"""Immutable publication, review invalidation and Dify export drift."""

import asyncio
import json
import os
import sqlite3
import struct
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

import httpx
import pytest
from campuspilot.dify_knowledge import DifyKnowledgeClient
from campuspilot.knowledge_release import (
    atomic_write,
    compile_dify,
    current_version,
    embed_candidate,
    import_approved_archive,
    preview,
    publish,
    read_candidate,
    rollback,
    sidecar_template,
    write_candidate,
)
from campuspilot.rag import KnowledgeSnapshot, SnapshotStore, canonical, digest, make_snapshot
from campuspilot.retrieval.vector import INDEX_NAME

DATA = Path(__file__).resolve().parents[1] / "data/cdut/rag"


def snapshot() -> KnowledgeSnapshot:
    return KnowledgeSnapshot.model_validate_json((DATA / "bootstrap.json").read_bytes())


def test_publish_atomic_version_switch_and_rollback_keep_request_pinned(tmp_path: Path) -> None:
    old = snapshot()
    new = make_snapshot(old.sources, old.chunks[:-1], old.source_package_sha256)
    a, b, root = tmp_path / "a", tmp_path / "b", tmp_path / "store"
    write_candidate(a, old)
    write_candidate(b, new)
    assert preview(a, root)["before"] is None
    assert publish(a, root, None) == old.version
    store = SnapshotStore(root)
    pinned = store.acquire()
    assert pinned is not None
    assert publish(b, root, old.version) == new.version
    assert pinned.snapshot.version == old.version
    acquired = store.acquire()
    assert acquired and acquired.snapshot.version == new.version
    with pytest.raises(ValueError):
        publish(a, root, old.version)
    assert rollback(root, old.version, new.version) == old.version
    assert current_version(root) == old.version


def test_publish_interruption_and_tampered_candidate_leave_active_pointer_unchanged(
    tmp_path: Path,
) -> None:
    value = snapshot()
    root, candidate = tmp_path / "live", tmp_path / "candidate"
    write_candidate(candidate, value)
    publish(candidate, root, None)
    new = make_snapshot(value.sources, value.chunks[:-1], value.source_package_sha256)
    changed = tmp_path / "changed"
    write_candidate(changed, new)
    from campuspilot.knowledge_release import atomic_write

    def broken(path: Path, data: bytes, metadata: os.stat_result | None = None) -> None:
        if path.name == "current.json":
            raise OSError("SYNTHETIC interrupted switch")
        atomic_write(path, data, metadata)

    with patch("campuspilot.knowledge_release.atomic_write", side_effect=broken):
        with pytest.raises(OSError):
            publish(changed, root, value.version)
    assert current_version(root) == value.version
    (changed / "snapshot.json").write_bytes(b"SYNTHETIC corrupt candidate")
    with pytest.raises(ValueError):
        publish(changed, root, value.version)
    assert current_version(root) == value.version


def test_concurrent_publish_has_one_winner_and_a_complete_snapshot(tmp_path: Path) -> None:
    old = snapshot()
    new = make_snapshot(old.sources, old.chunks[:-1], old.source_package_sha256)
    prior, candidate, root = tmp_path / "prior", tmp_path / "candidate", tmp_path / "store"
    write_candidate(prior, old)
    write_candidate(candidate, new)
    publish(prior, root, None)
    barrier = Barrier(2)

    def attempt() -> str:
        barrier.wait(timeout=10)
        try:
            return publish(candidate, root, old.version)
        except (FileExistsError, ValueError):
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == sorted([new.version, "conflict"])
    assert read_candidate(root / "versions" / new.version) == new
    assert current_version(root) == new.version
    assert not (root / ".publication.lock").exists()


def test_manifest_cannot_skip_snapshot_or_change_inclusion_mapping(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate, snapshot())
    file = candidate / "manifest.json"
    manifest = json.loads(file.read_bytes())
    del manifest["files_sha256"]["snapshot.json"]
    file.write_bytes(canonical(manifest))
    with pytest.raises(ValueError):
        read_candidate(candidate)


def test_copy_interruption_can_retry_without_partial_version(tmp_path: Path) -> None:
    value = snapshot()
    candidate, root = tmp_path / "candidate", tmp_path / "store"
    write_candidate(candidate, value, {"SYNTHETIC-evidence.txt": b"SYNTHETIC public test"})
    from campuspilot.knowledge_release import atomic_write

    def broken(path: Path, data: bytes, metadata: os.stat_result | None = None) -> None:
        if path.name == "SYNTHETIC-evidence.txt":
            raise OSError("SYNTHETIC interrupted copy")
        atomic_write(path, data, metadata)

    with patch("campuspilot.knowledge_release.atomic_write", side_effect=broken):
        with pytest.raises(OSError):
            publish(candidate, root, None)
    assert current_version(root) is None
    assert not (root / "versions" / value.version).exists()
    assert publish(candidate, root, None) == value.version


@pytest.mark.parametrize(
    "fault",
    [
        "model", "version", "dimensions", "coverage", "body", "blob", "nonfinite", "duplicates",
        "binding_model", "binding_dimensions", "binding_rows", "missing_binding", "missing_file",
    ],
)
def test_publication_checks_index_content_even_after_rehashing(tmp_path: Path, fault: str) -> None:
    candidate, root = tmp_path / "candidate", tmp_path / "store"
    value = snapshot()
    write_candidate(candidate, value)
    embed_candidate(candidate, lambda texts: [[1.0, 0.0] for _ in texts], "SYNTHETIC-model", 2)
    target = candidate / INDEX_NAME
    with closing(sqlite3.connect(target)) as connection:
        if fault in {"model", "version", "dimensions"}:
            key = {
                "model": "embedding_model",
                "version": "knowledge_version",
                "dimensions": "dimensions",
            }[fault]
            connection.execute("UPDATE meta SET value=? WHERE key=?", ("3", key))
        elif fault == "coverage":
            connection.execute("DELETE FROM vectors WHERE chunk_id=?", (value.chunks[0].chunk_id,))
        elif fault == "body":
            connection.execute("UPDATE vectors SET text_sha256='SYNTHETIC wrong'")
        elif fault in {"blob", "nonfinite"}:
            blob = b"x" if fault == "blob" else struct.pack("<ff", float("nan"), 0.0)
            connection.execute("UPDATE vectors SET embedding=?", (blob,))
        elif fault == "duplicates":
            connection.execute("ALTER TABLE vectors RENAME TO old_vectors")
            connection.execute("CREATE TABLE vectors AS SELECT * FROM old_vectors")
            connection.execute("INSERT INTO vectors SELECT * FROM old_vectors LIMIT 1")
            connection.execute("DROP TABLE old_vectors")
        connection.commit()
    manifest_path = candidate / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files_sha256"][INDEX_NAME] = digest(target.read_bytes())
    if fault.startswith("binding_"):
        key = fault.removeprefix("binding_")
        manifest["vector_index"][key] = "SYNTHETIC other" if key == "model" else 3
    elif fault == "missing_binding":
        del manifest["vector_index"]
    elif fault == "missing_file":
        del manifest["files_sha256"][INDEX_NAME]
    manifest_path.write_bytes(canonical(manifest))
    with pytest.raises(ValueError):
        read_candidate(candidate)
    # Semantic rejection must close SQLite before the directory can be renamed on Windows.
    renamed = tmp_path / "renamed"
    candidate.rename(renamed)
    with pytest.raises(ValueError):
        publish(renamed, root, None)
    assert current_version(root) is None
    assert not (root / "last_good.json").exists()


def test_publication_records_checked_previous_reference_before_current_commit(
    tmp_path: Path,
) -> None:
    value = snapshot()
    changed = make_snapshot(value.sources, value.chunks[:-1], value.source_package_sha256)
    old, new, root = tmp_path / "old", tmp_path / "new", tmp_path / "store"
    write_candidate(old, value)
    write_candidate(new, changed)
    publish(old, root, None)
    previous_pointer = (root / "current.json").read_bytes()

    def checked_switch(path: Path, data: bytes, metadata: os.stat_result | None = None) -> None:
        if path.name == "current.json":
            backup = json.loads((root / "last_good.json").read_bytes())
            assert backup == json.loads(previous_pointer)
            assert (root / "current.json").read_bytes() == previous_pointer
        atomic_write(path, data, metadata)

    with patch("campuspilot.knowledge_release.atomic_write", side_effect=checked_switch):
        publish(new, root, value.version)
    assert current_version(root) == changed.version
    backup = (root / "last_good.json").read_bytes()
    with pytest.raises(ValueError, match="drifted"):
        publish(old, root, value.version)
    assert (root / "last_good.json").read_bytes() == backup


def test_first_empty_store_backup_is_best_effort_after_successful_commit(tmp_path: Path) -> None:
    value = snapshot()
    candidate, root = tmp_path / "candidate", tmp_path / "store"
    write_candidate(candidate, value)

    def failed_backup(path: Path, data: bytes, metadata: os.stat_result | None = None) -> None:
        if path.name == "last_good.json":
            assert current_version(root) == value.version
            raise OSError("SYNTHETIC backup write failure")
        atomic_write(path, data, metadata)

    with patch("campuspilot.knowledge_release.atomic_write", side_effect=failed_backup):
        assert publish(candidate, root, None) == value.version
    assert not (root / "last_good.json").exists()
    acquired = SnapshotStore(root).acquire()
    assert acquired is not None and acquired.snapshot == value


def test_first_publication_binds_bootstrap_and_rejects_unsafe_bundle(tmp_path: Path) -> None:
    value = snapshot()
    changed = make_snapshot(value.sources, value.chunks[:-1], value.source_package_sha256)
    candidate, root = tmp_path / "candidate", tmp_path / "store"
    write_candidate(candidate, changed)
    root.mkdir()
    (root / "bootstrap.json").write_bytes(value.model_dump_json().encode())
    with pytest.raises(ValueError, match="fallback bundle"):
        publish(candidate, root, None, fallback_bundle="../SYNTHETIC")
    assert current_version(root) is None
    publish(candidate, root, None)
    backup = json.loads((root / "last_good.json").read_bytes())
    assert backup["kind"] == "bootstrap" and backup["version"] == value.version
    (root / "current.json").write_bytes(b"SYNTHETIC invalid pointer")
    acquired = SnapshotStore(root).acquire()
    assert acquired is not None and acquired.snapshot == value


def test_generated_sidecar_requires_explicit_review_even_for_exact_body_match() -> None:
    raw, existing = raw_and_sidecar()
    known = KnowledgeSnapshot.model_validate_json(canonical(existing["knowledge"]))
    template = sidecar_template(raw, known)
    assert template["bindings"][0]["chunk_id"] == known.chunks[0].chunk_id
    with pytest.raises(ValueError, match="requires review"):
        compile_dify(raw, template)
    template["bindings"][0]["review_required"] = False
    assert compile_dify(raw, template).chunks[0].chunk_id == known.chunks[0].chunk_id


def test_publication_applies_reader_permissions_before_atomic_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pointer = tmp_path / "current.json"
    pointer.write_bytes(b"SYNTHETIC previous pointer")
    events: list[str] = []
    original_replace = os.replace
    original_chmod = os.chmod
    metadata = os.stat_result((0o100640, 0, 0, 1, 1234, 4321, 0, 0, 0, 0))

    def owner(path: str | Path, uid: int, gid: int) -> None:
        assert uid == 1234 and gid == 4321
        events.append("owner")

    def mode(path: str | Path, value: int) -> None:
        assert value == 0o640
        events.append("mode")
        original_chmod(path, value)

    def switch(source: str | Path, destination: str | Path) -> None:
        assert pointer.read_bytes() == b"SYNTHETIC previous pointer"
        assert events == ["mode", "owner"]
        events.append("switch")
        original_replace(source, destination)

    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(os, "chown", owner, raising=False)
    monkeypatch.setattr(os, "chmod", mode)
    monkeypatch.setattr(os, "replace", switch)
    atomic_write(pointer, b"SYNTHETIC next pointer", metadata)
    assert events == ["mode", "owner", "switch"]


def test_approved_import_checks_raw_file_and_body_review_hashes(tmp_path: Path) -> None:
    files = {
        p.relative_to(DATA / "approved-20261010/raw").as_posix(): p.read_bytes()
        for p in (DATA / "approved-20261010/raw").rglob("*")
        if p.is_file()
    }
    archive = tmp_path / "approved.zip"
    with ZipFile(archive, "w") as output:
        for name, content in files.items():
            output.writestr("reviewed/" + name, content)
    imported, raw = import_approved_archive(archive)
    assert len(imported.sources) == 21 and len(imported.chunks) == 56 and raw == files
    files["data/chunks.jsonl"] += b"SYNTHETIC change"
    broken = tmp_path / "changed.zip"
    with ZipFile(broken, "w") as output:
        for name, content in files.items():
            output.writestr("reviewed/" + name, content)
    with pytest.raises(ValueError):
        import_approved_archive(broken)


def raw_and_sidecar() -> tuple[dict[str, object], dict[str, object]]:
    original = snapshot()
    chunk = original.chunks[0]
    base = make_snapshot(
        tuple(s for s in original.sources if s.source_id == chunk.source_id),
        (chunk,),
        original.source_package_sha256,
    )
    raw = {
        "schema_version": 1,
        "datasets": [
            {
                "id": "SYNTHETIC-dataset",
                "documents": [
                    {
                        "detail": {
                            "id": "SYNTHETIC-doc",
                            "enabled": True,
                            "archived": False,
                            "indexing_status": "completed",
                        },
                        "segments": [
                            {
                                "id": "SYNTHETIC-segment",
                                "enabled": True,
                                "status": "completed",
                                "content": chunk.text,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    sidecar: dict[str, object] = {
        "snapshot_sha256": digest(canonical(raw)),
        "knowledge": base.model_dump(mode="json"),
        "bindings": [
            {
                "dataset_id": "SYNTHETIC-dataset",
                "document_id": "SYNTHETIC-doc",
                "segment_id": "SYNTHETIC-segment",
                "chunk_id": chunk.chunk_id,
            }
        ],
    }
    return raw, sidecar


@pytest.mark.parametrize("fault", ["body", "unmapped", "unindexed", "archived", "children"])
def test_dify_mapping_changed_body_or_missing_review_never_publishes(fault: str) -> None:
    raw, sidecar = raw_and_sidecar()
    # JSON fixtures intentionally remain dictionaries, including nested public records.
    raw_value = json.loads(canonical(raw))
    document = raw_value["datasets"][0]["documents"][0]
    if fault == "body":
        document["segments"][0]["content"] += "SYNTHETIC unapproved"
    elif fault == "unmapped":
        sidecar["bindings"] = []
    elif fault == "unindexed":
        document["detail"]["indexing_status"] = "indexing"
    elif fault == "archived":
        document["detail"]["archived"] = True
    else:
        document["segments"][0]["child_chunks"] = [{"content": "SYNTHETIC child"}]
    sidecar["snapshot_sha256"] = digest(canonical(raw_value))
    if fault == "archived":
        compiled = compile_dify(raw_value, sidecar)
        assert not compiled.chunks[0].enabled
    else:
        with pytest.raises(ValueError):
            compile_dify(raw_value, sidecar)


def test_export_pages_preserve_activation_and_ignore_retrieval_counters() -> None:
    dataset, document, segment = (str(uuid4()) for _ in range(3))
    count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal count
        assert request.method == "GET"
        count += 1
        path = request.url.path
        if path.endswith("/segments"):
            value = {
                "data": [
                    {
                        "id": segment,
                        "content": "SYNTHETIC public source body",
                        "enabled": True,
                        "status": "completed",
                        "hit_count": count,
                    }
                ],
                "has_more": False,
            }
        elif path.endswith("/documents"):
            value = {
                "data": [
                    {
                        "id": document,
                        "enabled": True,
                        "archived": False,
                        "indexing_status": "completed",
                    }
                ],
                "has_more": False,
            }
        elif path.endswith("/" + document):
            value = {"id": document, "doc_form": "text_model"}
        elif path.endswith("/metadata"):
            value = {"doc_metadata": []}
        else:
            value = {"id": dataset, "indexing_technique": "economy"}
        return httpx.Response(200, json=value)

    client = DifyKnowledgeClient("SYNTHETIC-key", transport=httpx.MockTransport(handler))
    exported = asyncio.run(client.export((dataset,)))
    doc = exported["datasets"][0]["documents"][0]
    assert doc["detail"]["enabled"] is True and doc["detail"]["archived"] is False
    assert "hit_count" not in doc["segments"][0]


def test_export_changed_source_cancels_and_duplicate_pages_are_rejected() -> None:
    dataset, document = str(uuid4()), str(uuid4())
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path.endswith("/documents"):
            return httpx.Response(200, json={"data": [], "has_more": False})
        if request.url.path.endswith("/metadata"):
            return httpx.Response(200, json={"doc_metadata": []})
        calls += 1
        return httpx.Response(200, json={"id": dataset, "SYNTHETIC-revision": calls})

    client = DifyKnowledgeClient("SYNTHETIC-key", transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="changed"):
        asyncio.run(client.export((dataset,)))

    def duplicate(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": document}], "has_more": True})

    client = DifyKnowledgeClient("SYNTHETIC-key", transport=httpx.MockTransport(duplicate))

    async def read_pages() -> None:
        async with httpx.AsyncClient(transport=client.transport) as http:
            await client._pages(http, "/datasets/" + dataset + "/documents")

    with pytest.raises(ValueError):
        asyncio.run(read_pages())
