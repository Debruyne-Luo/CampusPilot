"""Build reviewable, jointly bound directory/RAG candidates without publishing them."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge_release import (
    atomic_write,
    load_candidate_index,
    read_candidate,
    write_candidate,
)
from campuspilot.rag import KnowledgeSnapshot, canonical, digest, make_snapshot
from campuspilot.retrieval.vector import INDEX_NAME, build_index, chunk_text

DIRECTORY_FILES = ("services.json", "offices.json", "sources.json", "places.json",
                   "teachers.json", "teachers_roster.json", "knowledge.json")


def enrich_prior_evidence(base: KnowledgeSnapshot, raw: dict[str, bytes]) -> KnowledgeSnapshot:
    """Migrate only already checked clause bindings; never infer new policy applicability."""
    provenance = json.loads(raw.get("official/provenance.json", b'{"documents":{}}'))
    by_id = {chunk.chunk_id: chunk for chunk in base.chunks}
    updates = {}
    for document_id, document in provenance["documents"].items():
        # A partial new revision does not repeal untouched old clauses. Locate their own
        # reviewed revision by approval binding instead of relabelling them as the newest.
        for revision_id, revision in document["versions"].items():
            for clause in revision["clauses"]:
                existing = by_id.get(clause["chunk_id"])
                if (existing is None or existing.revision_id
                    or existing.approval_id != clause.get("approval_id")
                    or existing.source_id != clause["source_id"]):
                    continue
                app = clause.get("applicability", {})
                campuses = []
                for campus in app.get("campuses", []):
                    if campus in {"成都校区", "成都", "chengdu"}:
                        campuses.append("chengdu")
                    elif campus in {"宜宾校区", "宜宾", "yibin"}:
                        campuses.append("yibin")
                    elif campus in {"全校", "各校区", "all"}:
                        campuses.append("all")
                updates[clause["chunk_id"]] = {
                    "document_id": document_id, "revision_id": revision_id,
                    "campuses": tuple(sorted(set(campuses))) or ("unknown",),
                    "conditions": tuple(app.get("conditions", [])),
                    "exceptions": tuple(app.get("exceptions", [])),
                    "applicability_evidence": {
                        **app.get("evidence_quotes", {}),
                        **({"audiences": app["audience_quote"]}
                           if app.get("audience_quote") else {}),
                    },
                }
    chunks = tuple(c.model_copy(update=updates[c.chunk_id]) if c.chunk_id in updates else c
                   for c in base.chunks)
    return make_snapshot(base.sources, chunks, base.source_package_sha256)


def reuse_vectors(
    candidate: Path, donor: Path, *,
    embed_missing: Callable[[Sequence[str]], list[list[float]]] | None = None,
    embedding_model: str | None = None,
) -> dict[str, Any]:
    """Reuse only identical embedding inputs from a verified index of the same model.

    Metadata-only changes require a new version binding, not a paid embedding request.
    A new/changed title, alias or body cannot borrow a different input's vector.
    """
    target = read_candidate(candidate, check_index=False)
    old = read_candidate(donor)
    old_manifest = json.loads((donor / "manifest.json").read_bytes())
    index = load_candidate_index(donor, old, old_manifest, prefer="python")
    if embed_missing is not None and embedding_model != index.model:
        raise ValueError("Embedding model must exactly match the donor")
    vectors = {
        chunk_text(c.title, c.aliases, c.text): index.vectors[c.chunk_id] for c in old.chunks
    }
    needed = [chunk_text(c.title, c.aliases, c.text) for c in target.chunks]
    missing = [c.chunk_id for c, text in zip(target.chunks, needed, strict=True)
               if text not in vectors]
    if missing and embed_missing is None:
        return {"status": "embedding_required", "missing_chunk_ids": missing,
                "reusable_rows": len(needed) - len(missing), "reused_rows": 0,
                "external_calls": 0}
    new_inputs = list(dict.fromkeys(text for text in needed if text not in vectors))
    if new_inputs and embed_missing is not None:
        import math

        new_vectors = embed_missing(new_inputs)
        if len(new_vectors) != len(new_inputs) or any(
            len(vector) != index.dimensions or not all(math.isfinite(v) for v in vector)
            for vector in new_vectors
        ):
            raise ValueError("New embeddings do not match the donor model dimensions")
        vectors.update(zip(new_inputs, new_vectors, strict=True))
    rows = build_index(candidate / INDEX_NAME, target,
                       lambda texts: [vectors[text] for text in texts],
                       index.model, index.dimensions)
    manifest = json.loads((candidate / "manifest.json").read_bytes())
    manifest["files_sha256"][INDEX_NAME] = digest((candidate / INDEX_NAME).read_bytes())
    manifest["vector_index"] = {
        "model": index.model, "dimensions": index.dimensions, "rows": rows,
    }
    atomic_write(candidate / "manifest.json", canonical(manifest))
    read_candidate(candidate)
    return {"status": "matched", "reused_rows": rows - len(missing),
            "embedded_rows": len(missing), "new_embedding_inputs": len(new_inputs),
            "external_calls": int(bool(new_inputs)),
            "donor_version": old.version, "model": index.model}


def prepare_candidate(
    base: Path, directory: Path, output: Path, *, vector_donor: Path | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise ValueError("candidate_output_exists")
    old = read_candidate(base)
    repository = DirectoryRepository.load(directory)
    original_manifest = json.loads((base / "manifest.json").read_bytes())
    raw = {name[4:]: (base / name).read_bytes() for name in original_manifest["files_sha256"]
           if name.startswith("raw/")}
    migrated = enrich_prior_evidence(old, raw)
    structured = {name: (directory / name).read_bytes() for name in DIRECTORY_FILES
                  if (directory / name).exists()}
    # Preserve evidence for new structured records, not just their normalized JSON fields.
    for name in ("baseline-service-review.json", "directory-report.json", "scope-report.json"):
        if (directory / name).is_file():
            structured[name] = (directory / name).read_bytes()
    raw_directory = directory / "raw"
    if raw_directory.is_dir():
        for path in sorted(raw_directory.rglob("*")):
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError("unsafe_structured_evidence")
            if path.is_file():
                if path.stat().st_size > 20_000_000:
                    raise ValueError("structured_evidence_too_large")
                structured[path.relative_to(directory).as_posix()] = path.read_bytes()
    package_hash = digest(canonical({
        "base_package": old.source_package_sha256, "migration": "checked-evidence-v2",
        "directory": {name: digest(data) for name, data in structured.items()},
    }))
    snapshot = make_snapshot(migrated.sources, migrated.chunks, package_hash)
    write_candidate(output, snapshot, raw)
    manifest = json.loads((output / "manifest.json").read_bytes())
    for name, data in structured.items():
        relative = "directory/" + name
        atomic_write(output / relative, data)
        manifest["files_sha256"][relative] = digest(data)
    manifest["directory_binding"] = {
        "path": "directory", "directory_schema_version": 2,
        "services": len(repository.services()),
        "publication_mode": "whole_release_required",
        "files": {name: digest(data) for name, data in structured.items()},
    }
    atomic_write(output / "manifest.json", canonical(manifest))
    vectors = reuse_vectors(output, vector_donor or base)
    report = {
        "base_version": old.version, "candidate_version": snapshot.version,
        "schema_version": snapshot.schema_version,
        "sources": len(snapshot.sources), "chunks": len(snapshot.chunks),
        "enriched_chunks": sum(bool(c.revision_id) for c in snapshot.chunks),
        "structured_services": len(repository.services()), "vector_index": vectors,
        "published": False, "release_ready": False,
        "remaining_gates": [
            *(["matching_vector_index"] if vectors["status"] != "matched" else []),
            "source_gold_review", "frozen_answer_acceptance", "source_recollection_gaps",
        ],
    }
    atomic_write(output / "review-status.json", canonical(report))
    return report


def review_archive(candidate: Path, archive: Path) -> dict[str, Any]:
    snapshot = read_candidate(candidate)
    DirectoryRepository.load(candidate / "directory")
    manifest = json.loads((candidate / "manifest.json").read_bytes())
    names = [*manifest["files_sha256"], "manifest.json", "review-status.json"]
    if archive.exists():
        raise ValueError("archive_exists")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive, "x", compression=ZIP_DEFLATED) as bundle:
        for name in sorted(names):
            bundle.writestr(name, (candidate / name).read_bytes())
    with ZipFile(archive) as bundle:
        if any(digest(bundle.read(n)) != sha for n, sha in manifest["files_sha256"].items()):
            raise ValueError("archive_checksum_mismatch")
    return {"version": snapshot.version, "archive_sha256": digest(archive.read_bytes()),
            "files": len(names), "published": False, "release_ready": False}
