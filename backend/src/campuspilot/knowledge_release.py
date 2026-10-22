"""Explicit knowledge releases: approved bodies, drift checks and atomic pointers."""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import stat
import struct
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote
from zipfile import ZipFile

from campuspilot.rag import KnowledgeSnapshot, RagChunk, RagSource, canonical, digest, make_snapshot

if TYPE_CHECKING:
    from campuspilot.retrieval.vector import VectorIndex

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


def read_candidate(directory: Path, *, check_index: bool = True) -> KnowledgeSnapshot:
    """Validate a release; runtime may isolate an index failure for BM25 fallback."""
    from campuspilot.retrieval.vector import INDEX_NAME

    if directory.is_symlink() or (directory / "manifest.json").is_symlink():
        raise ValueError("Unsafe release manifest")
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or not isinstance(manifest.get("files_sha256"), dict)
        or "snapshot.json" not in manifest["files_sha256"]
    ):
        raise ValueError("Incomplete candidate manifest")
    for name, checksum in manifest["files_sha256"].items():
        # All vector-specific faults are checked separately so runtime can still use BM25.
        if name == INDEX_NAME:
            continue
        if (
            not isinstance(name, str)
            or "\\" in name
            or ":" in name
            or any(part in {"", ".", ".."} for part in name.split("/"))
            or not isinstance(checksum, str)
            or not re.fullmatch(r"[a-f0-9]{64}", checksum)
        ):
            raise ValueError("Unsafe release path or checksum")
        path = directory / name
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Unsafe release path")
        if digest(path.read_bytes()) != checksum:
            raise ValueError("Candidate checksum mismatch")
    data = (directory / "snapshot.json").read_bytes()
    if len(data) > 20_000_000:
        raise ValueError("Knowledge snapshot too large")
    snapshot = KnowledgeSnapshot.model_validate_json(data)
    if snapshot.version != manifest.get("version"):
        raise ValueError("Candidate version mismatch")
    if manifest.get("counts") != {"sources": len(snapshot.sources), "chunks": len(snapshot.chunks)}:
        raise ValueError("Candidate counts mismatch")
    included = [c.chunk_id for c in snapshot.chunks if c.enabled]
    if (
        manifest.get("included") != included
        or snapshot.source_package_sha256 != manifest.get("source_package_sha256")
    ):
        raise ValueError("Candidate evidence mapping mismatch")
    if "directory_binding" in manifest:
        from campuspilot.directory.repository import DirectoryRepository

        binding = manifest["directory_binding"]
        if (not isinstance(binding, dict) or binding.get("path") != "directory"
            or binding.get("directory_schema_version") != 2
            or binding.get("publication_mode") != "whole_release_required"
            or not isinstance(binding.get("files"), dict)):
            raise ValueError("Invalid structured directory binding")
        for name, checksum in binding["files"].items():
            if manifest["files_sha256"].get("directory/" + name) != checksum:
                raise ValueError("Structured directory checksum binding mismatch")
        # Repository.load reads optional JSON files when present too. Every consumed file
        # must belong to the bound set, otherwise an unlisted teacher/place file could leak in.
        for path in (directory / "directory").glob("*.json"):
            if path.name not in binding["files"]:
                raise ValueError("Unbound structured directory file")
        if not {"services.json", "offices.json", "sources.json"} <= binding["files"].keys():
            raise ValueError("Incomplete structured directory binding")
        structured_repository = DirectoryRepository.load(directory / "directory")
        if len(structured_repository.services()) != binding.get("services"):
            raise ValueError("Structured directory counts mismatch")
    if check_index and (INDEX_NAME in manifest["files_sha256"] or "vector_index" in manifest):
        load_candidate_index(directory, snapshot, manifest, prefer="python")
    return snapshot


def load_candidate_index(
    directory: Path,
    snapshot: KnowledgeSnapshot,
    manifest: dict[str, Any],
    *,
    model: str | None = None,
    prefer: Literal["python"] | None = None,
) -> VectorIndex:
    """Check the file checksum and its model, version, dimensions and exact coverage."""
    from campuspilot.retrieval.vector import INDEX_NAME, VectorIndex, unpack

    binding = manifest.get("vector_index")
    checksum = manifest["files_sha256"].get(INDEX_NAME)
    if (
        not isinstance(binding, dict)
        or not isinstance(checksum, str)
        or not re.fullmatch(r"[a-f0-9]{64}", checksum)
        or not isinstance(binding.get("model"), str)
        or not binding["model"]
        or type(binding.get("dimensions")) is not int
        or binding["dimensions"] <= 0
        or type(binding.get("rows")) is not int
        or binding["rows"] != len(snapshot.chunks)
    ):
        raise ValueError("Incomplete candidate index binding")
    if model is not None and binding["model"] != model:
        raise ValueError("Vector index built with another embedding model")
    path = directory / INDEX_NAME
    if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Unsafe index path")
    if digest(path.read_bytes()) != checksum:
        raise ValueError("Vector index checksum mismatch")
    try:
        # Close even malformed SQLite files before publication renames the staged directory.
        with closing(
            sqlite3.connect("file:" + quote(str(path), safe=":/\\") + "?mode=ro", uri=True)
        ) as connection:
            metadata = dict(connection.execute("SELECT key, value FROM meta").fetchall())
            rows = connection.execute(
                "SELECT chunk_id, text_sha256, embedding FROM vectors"
            ).fetchall()
        if metadata.get("knowledge_version") != snapshot.version:
            raise ValueError("Vector index bound to another knowledge version")
        if metadata.get("embedding_model") != binding["model"]:
            raise ValueError("Vector index built with another embedding model")
        dimensions = int(metadata.get("dimensions", "0"))
        hashes = {chunk.chunk_id: chunk.text_sha256 for chunk in snapshot.chunks}
        vectors: dict[str, list[float]] = {}
        for chunk_id, text_hash, blob in rows:
            if hashes.get(chunk_id) != text_hash:
                raise ValueError("Vector index does not match approved chunk bodies")
            vector = unpack(blob)
            if len(vector) != dimensions:
                raise ValueError("Vector dimension mismatch")
            vectors[chunk_id] = vector
    except (sqlite3.Error, struct.error, TypeError, OverflowError) as exc:
        raise ValueError("Invalid candidate vector index") from exc
    if (
        dimensions != binding["dimensions"]
        or len(rows) != binding["rows"]
        or len(vectors) != binding["rows"]
        or set(vectors) != set(hashes)
        or any(not math.isfinite(value) for vector in vectors.values() for value in vector)
    ):
        raise ValueError("Candidate index counts or dimensions mismatch")
    if prefer == "python":
        return VectorIndex(snapshot, vectors, binding["model"], dimensions)
    return VectorIndex.load(path, snapshot, binding["model"])


def release_reference(directory: Path, *, kind: str = "published") -> dict[str, str]:
    """A durable reference binds one previously validated location, never a directory scan."""
    snapshot = read_candidate(directory)
    if snapshot.pending:
        raise ValueError("Pending knowledge cannot be a fallback")
    reference = {
        "kind": kind,
        "version": snapshot.version,
        "sha256": digest((directory / "snapshot.json").read_bytes()),
        "manifest_sha256": digest((directory / "manifest.json").read_bytes()),
    }
    if kind == "bundled":
        if not re.fullmatch(r"approved-\d{8}[a-z]?", directory.name):
            raise ValueError("Invalid fallback bundle")
        reference["bundle"] = directory.name
    elif kind != "published" or directory.name != snapshot.version:
        raise ValueError("Invalid release reference kind")
    return reference


def current_version(root: Path) -> str | None:
    path = root / "current.json"
    if path.is_symlink():
        raise ValueError("Unsafe active knowledge pointer")
    if not path.exists():
        return None
    pointer = json.loads(path.read_bytes())
    if not isinstance(pointer, dict) or pointer.get("kind", "published") != "published":
        raise ValueError("Invalid active knowledge pointer")
    version = pointer.get("version")
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


def publish(
    candidate: Path,
    root: Path,
    expected_current: str | None,
    *,
    fallback_bundle: str = "",
    quality_report: Path | None = None,
) -> str:
    with publication_lock(root):
        if current_version(root) != expected_current:
            raise ValueError("Published knowledge drifted; preview again")
        snapshot = read_candidate(candidate)
        candidate_manifest = json.loads((candidate / "manifest.json").read_bytes())
        if snapshot.pending:
            raise ValueError("Pending knowledge cannot be published; review and approve first")
        if candidate_manifest.get("directory_binding"):
            if quality_report is None:
                raise ValueError("Structured knowledge requires a whole-package release")
            acceptance = json.loads(quality_report.read_bytes())
            gate = acceptance.get("release_gate", {})
            if (acceptance.get("knowledge_version") != snapshot.version
                or gate.get("passed") is not True or gate.get("blockers") != []
                or gate.get("holdout_total_required") != 60
                or type(gate.get("holdout_passed")) is not int
                or gate["holdout_passed"] < 54
                or acceptance.get("suite", {}).get("total") != 120):
                raise ValueError("Whole-package quality acceptance incomplete or mismatched")
            # Keep the exact acceptance artifact with the immutable whole release.
            relative = "acceptance/quality.json"
            body = quality_report.read_bytes()
            if candidate_manifest["files_sha256"].get(relative) != digest(body):
                if candidate.resolve().is_relative_to((root / "versions").resolve()):
                    raise ValueError("Published versions are immutable")
                atomic_write(candidate / relative, body)
                candidate_manifest["files_sha256"][relative] = digest(body)
                atomic_write(candidate / "manifest.json", canonical(candidate_manifest))
        if snapshot.pending:
            raise ValueError("Pending knowledge cannot be published; review and approve first")
        reference = root / "current.json"
        if not reference.exists():
            reference = root / "bootstrap.json"
        read_metadata = reference.stat() if reference.exists() else root.stat()
        previous: dict[str, str] | None = None
        if expected_current:
            previous_directory = root / "versions" / expected_current
            if not previous_directory.resolve().is_relative_to(root.resolve()):
                raise ValueError("Unsafe active knowledge directory")
            previous = release_reference(previous_directory)
            pointer = json.loads((root / "current.json").read_bytes())
            if pointer.get("sha256") != previous["sha256"] or (
                pointer.get("manifest_sha256", previous["manifest_sha256"])
                != previous["manifest_sha256"]
            ):
                raise ValueError("Active knowledge checksum mismatch")
        elif fallback_bundle:
            if not isinstance(fallback_bundle, str) or not re.fullmatch(
                r"approved-\d{8}[a-z]?", fallback_bundle
            ):
                raise ValueError("Invalid fallback bundle")
            bundle = root / fallback_bundle
            if not bundle.resolve().is_relative_to(root.resolve()):
                raise ValueError("Unsafe fallback bundle")
            previous = release_reference(bundle, kind="bundled")
        elif (root / "bootstrap.json").exists() or (root / "bootstrap.json").is_symlink():
            bootstrap_path = root / "bootstrap.json"
            if bootstrap_path.is_symlink():
                raise ValueError("Unsafe bootstrap fallback")
            bootstrap = bootstrap_path.read_bytes()
            if len(bootstrap) > 20_000_000:
                raise ValueError("Bootstrap fallback too large")
            baseline = KnowledgeSnapshot.model_validate_json(bootstrap)
            if baseline.pending:
                raise ValueError("Pending bootstrap cannot be a fallback")
            previous = {
                "kind": "bootstrap", "version": baseline.version, "sha256": digest(bootstrap)
            }
        # Empty stores inherit root's read bits; deployed stores preserve a proven reader.
        version_dir = root / "versions" / snapshot.version
        if not version_dir.resolve().is_relative_to(root.resolve()):
            raise ValueError("Unsafe version destination")
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
        next_reference = release_reference(version_dir)
        if previous is not None:
            atomic_write(root / "last_good.json", canonical(previous), read_metadata)
        atomic_write(
            root / "current.json",
            canonical(next_reference),
            read_metadata,
        )
        if previous is None:
            # The pointer commit succeeded. A backup-write failure cannot undo that commit
            # or report a failed publication after changing the active version.
            try:
                atomic_write(root / "last_good.json", canonical(next_reference), read_metadata)
            except OSError:
                pass
        return snapshot.version


def rollback(root: Path, version: str, expected_current: str | None) -> str:
    if not re.fullmatch(r"kb-[a-f0-9]{16}", version):
        raise ValueError("Invalid rollback version")
    candidate = root / "versions" / version
    acceptance = candidate / "acceptance/quality.json"
    return publish(candidate, root, expected_current,
                   quality_report=acceptance if acceptance.is_file() else None)


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


def embed_candidate(
    candidate: Path,
    embed: Callable[[Sequence[str]], list[list[float]]],
    model: str,
    dimensions: int,
) -> int:
    """Build ``vectors.sqlite`` inside a candidate and bind it through the manifest.

    The index is listed in ``files_sha256``, so publish() copies it into the immutable
    version directory together with the snapshot and the pointer switch stays atomic.
    """
    from campuspilot.retrieval.vector import INDEX_NAME, build_index

    snapshot = read_candidate(candidate)
    target = candidate / INDEX_NAME
    if target.is_symlink():
        raise ValueError("Unsafe index path")
    count = build_index(target, snapshot, embed, model, dimensions)
    manifest = json.loads((candidate / "manifest.json").read_bytes())
    manifest["files_sha256"][INDEX_NAME] = digest(target.read_bytes())
    manifest["vector_index"] = {"model": model, "dimensions": dimensions, "rows": count}
    atomic_write(candidate / "manifest.json", canonical(manifest))
    read_candidate(candidate)
    return count
