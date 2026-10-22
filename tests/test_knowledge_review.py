"""Review artifacts bind structured data and reuse only equivalent embedding inputs."""

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from campuspilot.knowledge_release import publish, read_candidate, write_candidate
from campuspilot.knowledge_review import (
    enrich_prior_evidence,
    prepare_candidate,
    reuse_vectors,
    review_archive,
)
from campuspilot.rag import make_snapshot

ROOT = Path(__file__).resolve().parents[1]
DONOR = ROOT / "data/cdut/rag/versions/kb-229ee34eba99ef34"


def test_metadata_only_candidate_rebinds_all_vectors_without_provider(tmp_path: Path) -> None:
    result = prepare_candidate(DONOR, ROOT / "data/cdut", tmp_path / "candidate")
    candidate = read_candidate(tmp_path / "candidate")
    old = read_candidate(DONOR)
    assert candidate.schema_version == 2 and candidate.version != old.version
    assert result["vector_index"]["external_calls"] == 0
    assert result["vector_index"]["reused_rows"] == len(candidate.chunks)
    assert [(c.chunk_id, c.text_sha256) for c in candidate.chunks] == [
        (c.chunk_id, c.text_sha256) for c in old.chunks]
    assert any(c.applicability_evidence.get("audiences") for c in candidate.chunks)
    assert any(c.applicability_evidence.get("academic_year") for c in candidate.chunks)
    assert not result["release_ready"] and not result["published"]
    manifest = json.loads((tmp_path / "candidate/manifest.json").read_bytes())
    assert manifest["directory_binding"]["publication_mode"] == "whole_release_required"
    with pytest.raises(ValueError, match="whole-package release"):
        publish(tmp_path / "candidate", tmp_path / "isolated-store", None)
    assert not (tmp_path / "isolated-store/current.json").exists()


def test_changed_title_cannot_borrow_vector_even_when_body_hash_matches(tmp_path: Path) -> None:
    old = read_candidate(DONOR)
    changed = old.chunks[0].model_copy(update={"title": "SYNTHETIC changed embedding input"})
    new = make_snapshot(old.sources, (changed, *old.chunks[1:]), old.source_package_sha256)
    candidate = tmp_path / "candidate"
    write_candidate(candidate, new)
    result = reuse_vectors(candidate, DONOR)
    assert result["status"] == "embedding_required"
    assert result["missing_chunk_ids"] == [changed.chunk_id]
    assert not (candidate / "vectors.sqlite").exists()
    calls: list[str] = []

    def synthetic_embed(texts: Sequence[str]) -> list[list[float]]:
        calls.extend(texts)
        return [[0.1] * 1024 for _ in texts]

    with pytest.raises(ValueError, match="exactly match"):
        reuse_vectors(candidate, DONOR, embed_missing=synthetic_embed, embedding_model="wrong")
    assert not calls
    result = reuse_vectors(candidate, DONOR, embed_missing=synthetic_embed,
                           embedding_model="@cf/baai/bge-m3")
    assert calls == ["SYNTHETIC changed embedding input\n" + changed.aliases + "\n" + changed.text]
    assert result["embedded_rows"] == 1 and result["reused_rows"] == len(old.chunks) - 1
    read_candidate(candidate)


def test_archive_detects_structured_tampering_and_preserves_active_pointer(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    pointer = (ROOT / "data/cdut/rag/current.json").read_bytes()
    prepare_candidate(DONOR, ROOT / "data/cdut", candidate)
    archive = tmp_path / "review.zip"
    assert review_archive(candidate, archive)["published"] is False
    assert (ROOT / "data/cdut/rag/current.json").read_bytes() == pointer
    (candidate / "directory/services.json").write_bytes(b"[]")
    with pytest.raises(ValueError, match="checksum"):
        review_archive(candidate, tmp_path / "corrupt.zip")


def test_unbound_optional_structured_file_is_never_loaded(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    prepare_candidate(DONOR, ROOT / "data/cdut", candidate)
    (candidate / "directory/unlisted.json").write_bytes(b"[]")
    with pytest.raises(ValueError, match="Unbound structured"):
        read_candidate(candidate)


def test_partial_new_document_revision_keeps_untouched_clause_original_binding() -> None:
    old = read_candidate(DONOR)
    provenance = json.loads((DONOR / "raw/official/provenance.json").read_bytes())
    document_id, document = next(
        (key, value) for key, value in provenance["documents"].items()
        if len(value["versions"][value["current_revision"]]["clauses"]) > 1
    )
    old_revision = document["current_revision"]
    original = document["versions"][old_revision]
    untouched = original["clauses"][1]["chunk_id"]
    document["current_revision"] = "f" * 64
    document["versions"]["f" * 64] = {**original, "clauses": original["clauses"][:1]}
    migrated = enrich_prior_evidence(old, {
        "official/provenance.json": json.dumps(provenance).encode(),
    })
    item = next(c for c in migrated.chunks if c.chunk_id == untouched)
    assert item.document_id == document_id and item.revision_id == old_revision
