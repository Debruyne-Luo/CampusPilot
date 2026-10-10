"""Explicit knowledge releases: approved bodies, drift checks and atomic pointers."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

from campuspilot.rag import KnowledgeSnapshot, RagChunk, RagSource, canonical, digest, make_snapshot

APPROVED_FILES = (
    "data/sources.json",
    "data/chunks.jsonl",
    "data/candidate_offices.json",
    "data/topics.json",
    "data/source_register.csv",
    "data/source_evidence_for_import.json",
    "data/source_id_dedup_map.json",
)


def inherit_owner(path: str | Path, metadata: os.stat_result) -> None:
    owner, effective_uid = getattr(os, "chown", None), getattr(os, "geteuid", None)
    if callable(owner) and callable(effective_uid) and effective_uid() == 0:
        owner(path, metadata.st_uid, metadata.st_gid)


def atomic_write(path: Path, data: bytes, metadata: os.stat_result | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".knowledge-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if metadata is not None:
            os.chmod(name, stat.S_IMODE(metadata.st_mode) & 0o666)
            inherit_owner(name, metadata)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def publication_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".publication.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink()


def import_approved_archive(archive: Path) -> tuple[KnowledgeSnapshot, dict[str, bytes]]:
    if archive.stat().st_size > 20_000_000:
        raise ValueError("Approved archive too large")
    files: dict[str, bytes] = {}
    with ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist()) > 20_000_000:
            raise ValueError("Expanded archive too large")
        for info in z.infolist():
            parts = PurePosixPath(info.filename).parts
            if info.is_dir():
                continue
            if len(parts) < 2 or any(p in {"..", "."} for p in parts):
                raise ValueError("Unsafe archive entry")
            name = "/".join(parts[1:])
            if name not in (*APPROVED_FILES, "APPROVAL_RECORD.json", "KNOWLEDGE_NOTES.md"):
                continue  # Never execute or import reference code from an archive.
            if name in files:
                raise ValueError("Duplicate archive entry")
            files[name] = z.read(info)
    approval = json.loads(files["APPROVAL_RECORD.json"])
    if approval.get("status") != "approved_by_product_owner":
        raise ValueError("Missing approval record")
    for name in APPROVED_FILES:
        if digest(files[name]) != approval["file_sha256"][name]:
            raise ValueError("Approved file checksum mismatch")
    raw_sources = json.loads(files["data/sources.json"])
    raw_chunks = [
        json.loads(line) for line in files["data/chunks.jsonl"].splitlines() if line.strip()
    ]
    offices = json.loads(files["data/candidate_offices.json"])
    scope = approval["scope"]
    if (len(raw_sources), len(raw_chunks), len(offices)) != (
        scope["source_records"],
        scope["chunks"],
        scope["candidate_offices"],
    ):
        raise ValueError("Approval counts mismatch")
    sources = tuple(
        RagSource.model_validate_json(
            canonical(
                {
                    "source_id": s["source_id"],
                    "title": s["title"],
                    "url": s["url"],
                    "publisher": s["publisher"],
                    "applicability": s["applicability"],
                    "temporal_status": s["temporal_status"],
                    "content_scope": s["content_scope"],
                    "verification_status": s["verification_status"],
                    "reviewer": s["reviewer"],
                    "verified_at": s["verified_at"],
                }
            )
        )
        for s in raw_sources
    )
    chunks: list[RagChunk] = []
    for c in raw_chunks:
        if c["approval_id"] != approval["approval_id"]:
            raise ValueError("Chunk approval batch mismatch")
        data = {
            key: c[key]
            for key in (
                "chunk_id",
                "source_id",
                "topic_id",
                "title",
                "text",
                "locator",
                "aliases",
                "kind",
                "text_sha256",
                "verification_status",
                "reviewer",
                "verified_at",
                "approval_id",
            )
        }
        # Only explicit labels establish audience; never expand undergraduate aliases to graduates.
        data["audiences"] = ["undergraduate"] if "本科" in c["title"] else ["all"]
        chunks.append(RagChunk.model_validate_json(canonical(data)))
    for office in offices:
        if office["approval_id"] != approval["approval_id"]:
            raise ValueError("Office approval batch mismatch")
        text = (
            f"{office['department']}{office['name']}；资料记载地点：{office['location']}；"
            f"公开电话：{office['public_phone']}；职责：{office['responsibilities']}。"
            + office["notes"]
        )
        chunks.append(
            RagChunk.model_validate_json(
                canonical(
                    {
                        "chunk_id": office["candidate_id"],
                        "source_id": office["source_id"],
                        "topic_id": "offices",
                        "title": office["department"] + office["name"],
                        "text": text,
                        "locator": office["locator"],
                        "aliases": office["name"],
                        "kind": "fact",
                        "text_sha256": digest(text.encode()),
                        "verification_status": office["verification_status"],
                        "reviewer": office["reviewer"],
                        "verified_at": office["verified_at"],
                        "approval_id": office["approval_id"],
                    }
                )
            )
        )
    return make_snapshot(sources, tuple(chunks), digest(archive.read_bytes())), files


def write_candidate(
    directory: Path,
    snapshot: KnowledgeSnapshot,
    raw: dict[str, bytes] | None = None,
    exclusions: list[dict[str, str]] | None = None,
) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    data = snapshot.model_dump_json(indent=2).encode()
    files = {"snapshot.json": data, **{f"raw/{k}": v for k, v in (raw or {}).items()}}
    manifest = {
        "schema_version": 1,
        "version": snapshot.version,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_package_sha256": snapshot.source_package_sha256,
        "files_sha256": {name: digest(content) for name, content in files.items()},
        "included": [c.chunk_id for c in snapshot.chunks if c.enabled],
        "excluded": exclusions or [],
        "counts": {"sources": len(snapshot.sources), "chunks": len(snapshot.chunks)},
    }
    for name, content in files.items():
        target = directory / name
        if not target.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Unsafe candidate path")
        atomic_write(target, content)
    atomic_write(directory / "manifest.json", canonical(manifest))


def read_candidate(directory: Path) -> KnowledgeSnapshot:
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if manifest.get("schema_version") != 1 or "snapshot.json" not in manifest["files_sha256"]:
        raise ValueError("Incomplete candidate manifest")
    if directory.is_symlink():
        raise ValueError("Release directory cannot be a symbolic link")
    for name, checksum in manifest["files_sha256"].items():
        path = directory / name
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Unsafe release path")
        if digest(path.read_bytes()) != checksum:
            raise ValueError("Candidate checksum mismatch")
    snapshot = KnowledgeSnapshot.model_validate_json((directory / "snapshot.json").read_bytes())
    if snapshot.version != manifest["version"]:
        raise ValueError("Candidate version mismatch")
    if manifest["counts"] != {"sources": len(snapshot.sources), "chunks": len(snapshot.chunks)}:
        raise ValueError("Candidate counts mismatch")
    included = [c.chunk_id for c in snapshot.chunks if c.enabled]
    if (
        manifest["included"] != included
        or snapshot.source_package_sha256 != manifest["source_package_sha256"]
    ):
        raise ValueError("Candidate evidence mapping mismatch")
    return snapshot


def current_version(root: Path) -> str | None:
    path = root / "current.json"
    if not path.exists():
        return None
    version = json.loads(path.read_bytes())["version"]
    if not isinstance(version, str) or not re.fullmatch(r"kb-[a-f0-9]{16}", version):
        raise ValueError("Invalid active knowledge version")
    return version


def preview(candidate: Path, root: Path) -> dict[str, object]:
    new = read_candidate(candidate)
    old_version = current_version(root)
    old = read_candidate(root / "versions" / old_version) if old_version else None
    old_chunks = {c.chunk_id: c for c in old.chunks} if old else {}
    new_chunks = {c.chunk_id: c for c in new.chunks}
    return {
        "before": old_version,
        "after": new.version,
        "added": sorted(new_chunks.keys() - old_chunks.keys()),
        "removed": sorted(old_chunks.keys() - new_chunks.keys()),
        "changed": sorted(
            k for k in old_chunks.keys() & new_chunks.keys() if old_chunks[k] != new_chunks[k]
        ),
    }


def publish(candidate: Path, root: Path, expected_current: str | None) -> str:
    with publication_lock(root):
        if current_version(root) != expected_current:
            raise ValueError("Published knowledge drifted; preview again")
        snapshot = read_candidate(candidate)
        reference = root / "current.json"
        if not reference.exists():
            reference = root / "bootstrap.json"
        read_metadata = reference.stat() if reference.exists() else root.stat()
        # Empty stores inherit root's read bits; deployed stores preserve a proven reader.
        version_dir = root / "versions" / snapshot.version
        if not version_dir.exists():
            # Build a complete directory before making even the immutable version visible.
            manifest = json.loads((candidate / "manifest.json").read_bytes())
            versions = (root / "versions").resolve()
            if not versions.exists():
                root_metadata = root.stat()
                versions.mkdir(parents=True)
                os.chmod(versions, stat.S_IMODE(root_metadata.st_mode))
                inherit_owner(versions, root_metadata)
            directory_metadata = versions.stat()
            if not version_dir.resolve().is_relative_to(versions):
                raise ValueError("Unsafe version destination")
            with tempfile.TemporaryDirectory(prefix=".candidate-", dir=versions) as temporary:
                staged = Path(temporary).resolve()
                if not staged.is_relative_to(versions):
                    raise ValueError("Unsafe temporary version")
                for name in (*manifest["files_sha256"], "manifest.json"):
                    atomic_write(staged / name, (candidate / name).read_bytes(), read_metadata)
                read_candidate(staged)
                for folder in (staged, *(p for p in staged.rglob("*") if p.is_dir())):
                    if not folder.resolve().is_relative_to(staged):
                        raise ValueError("Unsafe staged directory")
                    os.chmod(folder, stat.S_IMODE(directory_metadata.st_mode))
                    inherit_owner(folder, directory_metadata)
                os.replace(staged, version_dir)
        read_candidate(version_dir)
        atomic_write(
            root / "current.json",
            canonical(
                {
                    "version": snapshot.version,
                    "sha256": digest((version_dir / "snapshot.json").read_bytes()),
                }
            ),
            read_metadata,
        )
        return snapshot.version


def rollback(root: Path, version: str, expected_current: str | None) -> str:
    if not re.fullmatch(r"kb-[a-f0-9]{16}", version):
        raise ValueError("Invalid rollback version")
    return publish(root / "versions" / version, root, expected_current)


def compile_dify(snapshot: dict[str, Any], sidecar: dict[str, Any]) -> KnowledgeSnapshot:
    """Every enabled segment needs an approved, hash-bound mapping or explicit exclusion."""
    if sidecar["snapshot_sha256"] != digest(canonical(snapshot)):
        raise ValueError("Sidecar belongs to a different Dify snapshot")
    base = KnowledgeSnapshot.model_validate_json(canonical(sidecar["knowledge"]))
    mappings = sidecar["bindings"]
    mapped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in mappings:
        key = (item["dataset_id"], item["document_id"], item["segment_id"])
        if key in mapped:
            raise ValueError("Duplicate Dify binding")
        mapped[key] = item
    chunks = {c.chunk_id: c for c in base.chunks}
    used: set[str] = set()
    exported: list[RagChunk] = []
    for dataset in snapshot["datasets"]:
        for document in dataset["documents"]:
            doc = document["detail"]
            document_active = doc.get("enabled") is True and doc.get("archived") is False
            if document_active and doc.get("indexing_status") != "completed":
                raise ValueError("Enabled document has not finished indexing")
            for segment in document["segments"]:
                if segment.get("child_chunks"):
                    raise ValueError(
                        "Hierarchical child chunks need an explicit reviewed normalization"
                    )
                key = (dataset["id"], doc["id"], segment["id"])
                active = document_active and segment.get("enabled") is True
                if active and segment.get("status") != "completed":
                    raise ValueError("Enabled segment has not finished indexing")
                binding = mapped.pop(key, None)
                if binding is None:
                    if active:
                        raise ValueError("Enabled Dify segment lacks review mapping")
                    continue
                if binding.get("review_required") is True:
                    raise ValueError("Dify mapping still requires review")
                if binding.get("exclude_reason"):
                    continue
                ident = binding["chunk_id"]
                chunk = chunks[ident]
                if ident in used:
                    raise ValueError("Multiple segments mapped to the same stable chunk")
                used.add(ident)
                if digest(segment["content"].encode()) != chunk.text_sha256:
                    raise ValueError("Dify body changed; previous review is invalid")
                exported.append(chunk.model_copy(update={"enabled": active}))
    if mapped:
        raise ValueError("Sidecar contains missing Dify segments")
    # Preserve local-only evidence explicitly; never silently resurrect disabled Dify content.
    local_ids = set(sidecar.get("local_only_chunk_ids", []))
    if local_ids - chunks.keys() or local_ids & used:
        raise ValueError("Invalid local-only evidence mapping")
    exported.extend(chunks[i] for i in sorted(local_ids))
    source_ids = {c.source_id for c in exported}
    return make_snapshot(
        tuple(s for s in base.sources if s.source_id in source_ids),
        tuple(exported),
        digest(canonical(snapshot)),
    )


def sidecar_template(snapshot: dict[str, Any], knowledge: KnowledgeSnapshot) -> dict[str, Any]:
    """Suggest only exact body matches; a template never grants new source approval."""
    by_hash: dict[str, list[str]] = {}
    for chunk in knowledge.chunks:
        by_hash.setdefault(chunk.text_sha256, []).append(chunk.chunk_id)
    bindings: list[dict[str, Any]] = []
    for dataset in snapshot["datasets"]:
        for document in dataset["documents"]:
            doc = document["detail"]
            for segment in document["segments"]:
                checksum = digest(segment["content"].encode())
                options = by_hash.get(checksum, [])
                binding: dict[str, Any] = {
                    "dataset_id": dataset["id"],
                    "document_id": doc["id"],
                    "segment_id": segment["id"],
                    "text_sha256": checksum,
                    "candidate_chunk_ids": options,
                    "review_required": True,
                }
                if len(options) == 1:
                    binding["chunk_id"] = options[0]
                bindings.append(binding)
    return {
        "schema_version": 1,
        "snapshot_sha256": digest(canonical(snapshot)),
        "knowledge": knowledge.model_dump(mode="json"),
        "bindings": bindings,
        "local_only_chunk_ids": [],
    }
