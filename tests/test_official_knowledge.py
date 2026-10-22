"""SYNTHETIC official-export contract fixtures, never real university records."""

import io
import json
import runpy
import tempfile
from datetime import date
from pathlib import Path
from zipfile import ZipFile

import pytest
from campuspilot.knowledge_release import (
    embed_candidate,
    publish,
    read_candidate,
    rollback,
    write_candidate,
)
from campuspilot.official_knowledge import (
    PROVENANCE,
    attachment_format,
    build,
    extract,
    parse_attachment,
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
from campuspilot.retrieval.bm25 import eligible

SYNTHETIC_URL = "https://www.cdut.edu.cn/SYNTHETIC-export-contract"
BODY = (
    "SYNTHETIC 测试文件；并非任何大学事实或真实制度。\n\n"
    "适用于本科生。SYNTHETIC 测试条款：每人每学年最多三次。\n\n"
    "SYNTHETIC 2026—2027学年，2026年1月10日至2026年2月20日有效。"
    "SYNTHETIC 成都校区；仅通过测试渠道办理；不含测试例外对象。"
)


def base_snapshot() -> KnowledgeSnapshot:
    sources = tuple(RagSource(
        source_id=f"cdut:source:synthetic-legacy-{i}", title="SYNTHETIC legacy source",
        url=SYNTHETIC_URL, publisher="SYNTHETIC publisher", applicability="SYNTHETIC",
        verification_status="verified", reviewer="SYNTHETIC reviewer",
        verified_at=date(2026, 10, 10),
    ) for i in range(2))
    chunks = tuple(RagChunk(
        chunk_id=f"cdut:chunk:synthetic-legacy-{i}", source_id=s.source_id,
        topic_id="synthetic", title="SYNTHETIC legacy clause", text="SYNTHETIC old body",
        locator="SYNTHETIC old locator", text_sha256=digest(b"SYNTHETIC old body"),
        verification_status="verified", reviewer="SYNTHETIC reviewer",
        verified_at=date(2026, 10, 10), approval_id="SYNTHETIC old approval",
    ) for i, s in enumerate(sources))
    return make_snapshot(sources, chunks, "0" * 64)


def capture(tmp_path: Path) -> tuple[Path, dict[str, object], dict[str, object]]:
    package = tmp_path / "capture"
    package.mkdir()
    (package / "body.txt").write_bytes(BODY.encode())
    quote = "适用于本科生。SYNTHETIC 测试条款：每人每学年最多三次。"
    clause: dict[str, object] = {
        "clause_id": "stable", "topic_id": "synthetic", "quote": quote,
        "locator": {"file": "body.txt", "start": BODY.index(quote),
                    "end": BODY.index(quote) + len(quote)},
        "applicability": {"audiences": ["undergraduate"], "audience_quote": "适用于本科生。"},
        "review": {"checked_by": "SYNTHETIC validator", "checked_at": "2026-10-14",
                   "body_sha256": digest(BODY.encode())},
        "disposition": "adopt",
    }
    document: dict[str, object] = {
        "document_id": "synthetic", "url": SYNTHETIC_URL, "title": "SYNTHETIC document",
        "publisher": "SYNTHETIC issuer", "collected_at": "2026-10-14T10:00:00+08:00",
        "channel": "browser_dom", "body_file": "body.txt", "complete": True,
        "content_kind": "guide", "access_scope": "public", "published_on": None,
        "signed_on": None, "clauses": [clause], "attachments": [],
    }
    save(package, [document])
    return package, document, clause


def save(package: Path, documents: list[dict[str, object]]) -> None:
    (package / "manifest.json").write_bytes(canonical({"schema_version": 1,
                                                     "documents": documents}))


def test_adoption_binds_exact_body_preserves_other_sources_and_multi_id_mapping(
    tmp_path: Path,
) -> None:
    package, _, _ = capture(tmp_path)
    base = base_snapshot()
    snapshot, raw, report = build(package, base)
    assert len(snapshot.chunks) == 3 and len(snapshot.sources) == 3
    by_id = {c.chunk_id: c for c in snapshot.chunks}
    assert all(by_id[c.chunk_id] == c for c in base.chunks)
    new = next(c for c in snapshot.chunks if c.verification_status == "official_document")
    assert new.approval_id != base.chunks[0].approval_id
    assert new.audiences == ("undergraduate",) and not new.ocr
    source = next(s for s in snapshot.sources if s.source_id == new.source_id)
    assert source.temporal_status == "unknown"
    assert source.content_scope == "complete_official_browser_dom"
    provenance = json.loads(raw[PROVENANCE])["documents"]["synthetic"]
    assert len(provenance["legacy_source_ids"]) == 2
    version = provenance["versions"][provenance["current_revision"]]
    assert version["body_sha256"] == digest(BODY.encode())
    assert version["published_on"] is None and version["signed_on"] is None
    assert report["adopted_clauses"] == 1 and not report["failed"]


def test_v2_adoption_binds_revision_campus_and_checked_heading(tmp_path: Path) -> None:
    package, document, clause = capture(tmp_path)
    clause["structure"] = {"section_id": "synthetic-section", "heading_path": ["SYNTHETIC"]}
    app = clause["applicability"]
    assert isinstance(app, dict)
    app["campuses"] = ["成都校区"]
    save(package, [document])
    adopted, raw, report = build(package, base_snapshot())
    assert not report["failed"] and adopted.schema_version == 2
    checked = next(c for c in adopted.chunks if c.document_id == "synthetic")
    history = json.loads(raw[PROVENANCE])["documents"]["synthetic"]
    assert checked.revision_id == history["current_revision"]
    assert checked.campuses == ("chengdu",) and checked.section_id == "synthetic-section"
    assert checked.heading_path == ("SYNTHETIC",)
    clause["structure"] = {"section_id": "invented", "heading_path": ["SYNTHETIC not in source"]}
    save(package, [document])
    failed, preserved, report = build(package, adopted, prior_raw=raw)
    assert failed == adopted and preserved == raw
    assert report["failed"][0]["reason"] == "structure_not_supported"


def test_provider_extract_is_not_mislabelled_as_original_http_response(tmp_path: Path) -> None:
    package, document, _ = capture(tmp_path)
    document["channel"] = "http"
    original = b'{"SYNTHETIC":"provider response"}'
    (package / "response.json").write_bytes(original)
    document["original_file"] = "response.json"
    document["source_capture"] = {"provider": "firecrawl-v2", "response_sha256": digest(original)}
    save(package, [document])
    adopted, raw, report = build(package, base_snapshot())
    assert not report["failed"]
    checked = next(c for c in adopted.chunks if c.document_id == "synthetic")
    src = next(s for s in adopted.sources if s.source_id == checked.source_id)
    assert src.content_scope == "complete_provider_extracted_document"
    history = json.loads(raw[PROVENANCE])["documents"]["synthetic"]
    assert history["versions"][history["current_revision"]]["source_capture"]["provider"] == \
        "firecrawl-v2"


def test_explicit_retirement_requires_source_evidence_and_preserves_history(tmp_path: Path) -> None:
    package, document, clause = capture(tmp_path)
    adopted, raw, report = build(package, base_snapshot())
    assert not report["failed"]
    clause["disposition"] = "retire"
    clause["repeal_quote"] = "SYNTHETIC nonexistent repeal"
    save(package, [document])
    failed, preserved, report = build(package, adopted, prior_raw=raw)
    assert failed == adopted and preserved == raw
    assert report["failed"][0]["reason"] == "retirement_requires_explicit_evidence"
    new_body = BODY + "\nSYNTHETIC 测试条款停止执行。"
    (package / "body.txt").write_bytes(new_body.encode())
    document["collected_at"] = "2026-10-15T10:00:00+08:00"
    clause["review"] = {"checked_by": "SYNTHETIC validator", "checked_at": "2026-10-15",
                        "body_sha256": digest(new_body.encode())}
    clause["repeal_quote"] = "SYNTHETIC 测试条款停止执行。"
    save(package, [document])
    retired, history_raw, report = build(package, adopted, prior_raw=raw)
    assert not report["failed"]
    latest = next(c for c in retired.chunks if c.document_id == "synthetic")
    assert not latest.enabled and latest.kind == "deprecated"
    assert not eligible(latest, retired.sources[-1], RetrievalFilters(today=date(2026, 10, 15)))
    history = json.loads(history_raw[PROVENANCE])["documents"]["synthetic"]
    assert len(history["versions"]) == 2


def test_exact_offsets_and_applicability_dates_are_enforced(tmp_path: Path) -> None:
    package, document, clause = capture(tmp_path)
    app = clause["applicability"]
    assert isinstance(app, dict)
    app.update({"valid_from": "2026-01-10", "valid_until": "2026-02-20",
                "academic_year": "2026-2027", "campuses": ["成都校区"],
                "conditions": ["仅通过测试渠道办理"], "exceptions": ["不含测试例外对象"],
                "evidence_quotes": {"valid_from": "2026年1月10日",
                                    "valid_until": "2026年2月20日",
                                    "academic_year": "2026—2027学年"}})
    save(package, [document])
    snapshot, _, report = build(package, base_snapshot())
    assert not report["failed"]
    chunk = next(c for c in snapshot.chunks if c.verification_status == "official_document")
    assert chunk.valid_from == date(2026, 1, 10) and chunk.valid_until == date(2026, 2, 20)
    assert chunk.academic_year == "2026-2027"
    assert "仅通过测试渠道办理" in chunk.text and "例外条件" in chunk.text
    app["valid_until"] = "2026-02-21"
    save(package, [document])
    failed, _, report = build(package, base_snapshot())
    assert failed == base_snapshot() and report["failed"][0]["reason"] == "date_not_supported"


@pytest.mark.parametrize("mutation,reason", [
    ("quote", "quote_locator_mismatch"), ("hash", "review_body_hash_mismatch"),
    ("audience", "audience_not_supported"), ("conflict", "unresolved_conflict"),
    ("no_review", "missing_clause_review"), ("condition", "condition_not_supported"),
])
def test_untrusted_annotations_cannot_grant_authority(
    tmp_path: Path, mutation: str, reason: str,
) -> None:
    package, document, clause = capture(tmp_path)
    if mutation == "quote":
        clause["quote"] = "SYNTHETIC invented unsupported clause"
    elif mutation == "hash":
        clause["review"] = {"checked_by": "SYNTHETIC", "checked_at": "2026-10-14",
                            "body_sha256": "0" * 64}
    elif mutation == "audience":
        clause["applicability"] = {"audiences": ["graduate"], "audience_quote": "适用于本科生。"}
    elif mutation == "conflict":
        clause["unresolved_conflict"] = "SYNTHETIC irreconcilable evidence"
    elif mutation == "no_review":
        clause.pop("review")
    else:
        clause["applicability"] = {"audiences": ["undergraduate"],
                                  "audience_quote": "适用于本科生。",
                                  "conditions": ["SYNTHETIC fabricated condition"]}
    save(package, [document])
    snapshot, _, report = build(package, base_snapshot())
    assert snapshot == base_snapshot()
    assert report["failed"][0]["reason"] == reason


@pytest.mark.parametrize("kind,body,complete,reason", [
    ("guide", "", True, "empty_or_challenge_body"),
    ("guide", "SYNTHETIC 412 Precondition Failed $_ts challenge" * 2,
     True, "empty_or_challenge_body"),
    ("index", BODY, True, "not_document_body"),
    ("search_summary", BODY, True, "not_document_body"),
    ("guide", BODY, False, "incomplete_document"),
])
def test_blank_challenge_index_and_summary_never_replace_last_success(
    tmp_path: Path, kind: str, body: str, complete: bool, reason: str,
) -> None:
    package, document, _ = capture(tmp_path)
    document.update({"content_kind": kind, "complete": complete})
    (package / "body.txt").write_bytes(body.encode())
    save(package, [document])
    snapshot, _, report = build(package, base_snapshot())
    assert snapshot == base_snapshot() and report["failed"][0]["reason"] == reason


def test_extraction_remains_unapproved_and_quotes_exact_visible_text(tmp_path: Path) -> None:
    package, document, _ = capture(tmp_path)
    extracted = extract(package)
    assert extracted["authority"] == "candidate_only"
    candidates = extracted["documents"][0]["clauses"]
    for clause in candidates:
        assert clause["review_required"] is True
        locator = clause["locator"]
        assert BODY[locator["start"]:locator["end"]] == clause["quote"]
    document["clauses"] = candidates
    save(package, [document])
    snapshot, _, report = build(package, base_snapshot())
    assert snapshot == base_snapshot() and report["failed"]


def test_unknown_audience_has_explicit_limitation_never_all(tmp_path: Path) -> None:
    package, document, clause = capture(tmp_path)
    clause["applicability"] = {"audiences": []}
    save(package, [document])
    assert build(package, base_snapshot())[2]["failed"][0]["reason"] == (
        "unknown_audience_requires_limitation"
    )
    clause.update({"disposition": "limitation", "limitation": "SYNTHETIC audience unspecified"})
    save(package, [document])
    snapshot, _, report = build(package, base_snapshot())
    assert not report["failed"]
    chunk = next(c for c in snapshot.chunks if c.verification_status == "official_document")
    assert chunk.audiences == ("unknown",) and chunk.kind == "limitation"


def test_repeat_import_upserts_stable_clause_and_retains_success_history(tmp_path: Path) -> None:
    package, document, clause = capture(tmp_path)
    clause["clause_id"] = "cdut:chunk:synthetic-legacy-0"
    clause["source_id"] = "cdut:source:synthetic-legacy-0"
    save(package, [document])
    first, raw, _ = build(package, base_snapshot())
    repeated, repeated_raw, repeated_report = build(package, first, prior_raw=raw)
    assert repeated.version == first.version and repeated_raw == raw
    assert repeated_report["unchanged"] is True
    old_quote = clause["quote"]
    assert isinstance(old_quote, str)
    new_body = BODY.replace("最多三次", "最多四次")
    clause["quote"] = old_quote.replace("最多三次", "最多四次")
    clause["review"] = {"checked_by": "SYNTHETIC second validator",
                        "checked_at": "2026-10-14", "body_sha256": digest(new_body.encode())}
    (package / "body.txt").write_bytes(new_body.encode())
    save(package, [document])
    second, history_raw, _ = build(package, first, prior_raw=raw)
    assert len(second.chunks) == len(first.chunks) == 2
    history = json.loads(history_raw[PROVENANCE])["documents"]["synthetic"]
    assert len(history["versions"]) == 2
    assert history["versions"][history["current_revision"]]["previous_revision"]
    assert all(name in history_raw for name in raw if name != PROVENANCE)
    (package / "body.txt").write_bytes(b"SYNTHETIC failed capture")
    failed, final_raw, report = build(package, second, prior_raw=history_raw)
    assert failed == second and final_raw == history_raw and report["failed"]


def test_repeat_new_document_is_idempotent_and_does_not_become_a_legacy_source(
    tmp_path: Path,
) -> None:
    package, _, _ = capture(tmp_path)
    first, raw, _ = build(package, base_snapshot())
    repeated, repeated_raw, _ = build(package, first, prior_raw=raw)
    assert repeated.version == first.version and repeated_raw == raw
    assert len(json.loads(raw[PROVENANCE])["documents"]["synthetic"]["versions"]) == 1


def test_older_capture_does_not_overwrite_last_success_and_crlf_bytes_remain_exact(
    tmp_path: Path,
) -> None:
    package, document, clause = capture(tmp_path)
    body = BODY.replace("\n", "\r\n")
    (package / "body.txt").write_bytes(body.encode())
    quote = clause["quote"]
    assert isinstance(quote, str)
    clause["locator"] = {"file": "body.txt", "start": body.index(quote),
                         "end": body.index(quote) + len(quote)}
    clause["review"] = {"checked_by": "SYNTHETIC validator", "checked_at": "2026-10-14",
                        "body_sha256": digest(body.encode())}
    save(package, [document])
    snapshot, raw, report = build(package, base_snapshot())
    assert not report["failed"]
    assert any(content == body.encode() for name, content in raw.items()
               if name.endswith("body.txt"))
    document["collected_at"] = "2026-10-13T10:00:00+08:00"
    save(package, [document])
    unchanged, preserved_raw, failure = build(package, snapshot, prior_raw=raw)
    assert unchanged == snapshot and preserved_raw == raw
    assert failure["failed"][0]["reason"] == "older_collection_cannot_replace_last_success"


def test_older_same_day_timestamp_never_replaces_last_success(tmp_path: Path) -> None:
    package, document, clause = capture(tmp_path)
    document["collected_at"] = "2026-10-14T20:00:00+08:00"
    save(package, [document])
    first, raw, _ = build(package, base_snapshot())
    changed = BODY.replace("最多三次", "最多四次")
    (package / "body.txt").write_bytes(changed.encode())
    old_quote = clause["quote"]
    assert isinstance(old_quote, str)
    clause["quote"] = old_quote.replace("最多三次", "最多四次")
    clause["review"] = {"checked_by": "SYNTHETIC validator", "checked_at": "2026-10-14",
                        "body_sha256": digest(changed.encode())}
    document["collected_at"] = "2026-10-14T11:00:00+00:00"  # 19:00 China time, still older.
    save(package, [document])
    result, preserved, report = build(package, first, prior_raw=raw)
    assert result == first and preserved == raw and report["unchanged"]
    assert report["failed"][0]["reason"] == "older_collection_cannot_replace_last_success"
    document["collected_at"] = "2026-10-14T13:00:00+00:00"  # 21:00 China time, later.
    save(package, [document])
    result, _, report = build(package, first, prior_raw=raw)
    assert result.version != first.version and not report["failed"]


def test_day_only_order_allows_exact_repeat_but_rejects_changed_same_day_body(
    tmp_path: Path,
) -> None:
    package, document, clause = capture(tmp_path)
    document.update({"collected_at": "2026-10-14", "collection_precision": "day"})
    save(package, [document])
    first, raw, _ = build(package, base_snapshot())
    repeated, repeated_raw, report = build(package, first, prior_raw=raw)
    assert repeated == first and repeated_raw == raw and not report["failed"]
    changed = BODY.replace("最多三次", "最多四次")
    (package / "body.txt").write_bytes(changed.encode())
    old_quote = clause["quote"]
    assert isinstance(old_quote, str)
    clause["quote"] = old_quote.replace("最多三次", "最多四次")
    clause["review"] = {"checked_by": "SYNTHETIC validator", "checked_at": "2026-10-14",
                        "body_sha256": digest(changed.encode())}
    save(package, [document])
    result, preserved, report = build(package, first, prior_raw=raw)
    assert result == first and preserved == raw
    assert report["failed"][0]["reason"] == "collection_time_order_unknown"


@pytest.mark.parametrize("status", ["historical", "superseded"])
def test_partial_legacy_upsert_does_not_resurrect_untouched_sibling(
    tmp_path: Path, status: str,
) -> None:
    package, document, clause = capture(tmp_path)
    base = base_snapshot()
    source = base.sources[0].model_copy(update={"temporal_status": status})
    sibling = base.chunks[0].model_copy(update={"chunk_id": "cdut:chunk:synthetic-sibling"})
    base = make_snapshot((source, base.sources[1]), (*base.chunks, sibling),
                         base.source_package_sha256)
    clause.update({"clause_id": base.chunks[0].chunk_id, "source_id": source.source_id})
    save(package, [document])
    result, _, report = build(package, base)
    assert not report["failed"]
    updated_source = next(s for s in result.sources if s.source_id == source.source_id)
    untouched = next(c for c in result.chunks if c.chunk_id == sibling.chunk_id)
    assert updated_source.temporal_status == source.temporal_status and untouched == sibling
    filters = RetrievalFilters(today=date(2026, 10, 14))
    assert not eligible(sibling, source, filters)
    assert not eligible(untouched, updated_source, filters)


def test_day_precision_and_explicit_students_map_without_manufacturing_timestamp(
    tmp_path: Path,
) -> None:
    package, document, clause = capture(tmp_path)
    day_body = BODY + "\nSYNTHETIC 服务人群：学生,教师。"
    (package / "body.txt").write_bytes(day_body.encode())
    document.update({"collected_at": "2026-10-14", "collection_precision": "day",
                     "collection_note": "SYNTHETIC same-day earlier browser observation"})
    clause["review"] = {"checked_by": "SYNTHETIC validator", "checked_at": "2026-10-14",
                        "body_sha256": digest(day_body.encode())}
    clause["applicability"] = {"audiences": ["undergraduate", "graduate", "staff"],
                              "audience_quote": "服务人群：学生,教师。"}
    save(package, [document])
    snapshot, raw, report = build(package, base_snapshot())
    assert not report["failed"]
    chunk = next(c for c in snapshot.chunks if c.verification_status == "official_document")
    assert set(chunk.audiences) == {"undergraduate", "graduate", "staff"}
    prov = json.loads(raw[PROVENANCE])["documents"]["synthetic"]
    record = prov["versions"][prov["current_revision"]]
    assert record["collected_at"] == "2026-10-14" and record["collection_precision"] == "day"
    document.pop("collection_precision")
    save(package, [document])
    assert build(package, base_snapshot())[2]["failed"][0]["reason"] == (
        "collection_precision_required"
    )


def test_same_sentence_end_date_inherits_written_year_but_never_infers_rollover(
    tmp_path: Path,
) -> None:
    package, document, clause = capture(tmp_path)
    interval = "SYNTHETIC 2026年1月26日—3月3日。"
    body = BODY + "\n" + interval
    (package / "body.txt").write_bytes(body.encode())
    clause["review"] = {"checked_by": "SYNTHETIC validator", "checked_at": "2026-10-14",
                        "body_sha256": digest(body.encode())}
    clause["applicability"] = {"audiences": ["undergraduate"], "audience_quote": "适用于本科生。",
                              "valid_from": "2026-01-26", "valid_until": "2026-03-03",
                              "evidence_quotes": {"valid_from": interval, "valid_until": interval}}
    save(package, [document])
    snapshot, _, report = build(package, base_snapshot())
    assert not report["failed"]
    chunk = next(c for c in snapshot.chunks if c.verification_status == "official_document")
    assert chunk.valid_until == date(2026, 3, 3)
    app = clause["applicability"]
    assert isinstance(app, dict)
    app["valid_until"] = "2027-03-03"
    save(package, [document])
    assert build(package, base_snapshot())[2]["failed"][0]["reason"] == "date_not_supported"


def test_attachment_quotes_require_checked_text_original_hash_and_matching_offsets(
    tmp_path: Path,
) -> None:
    package, document, clause = capture(tmp_path)
    image = b"\x89PNG\r\n\x1a\nSYNTHETIC image signature fixture"
    text = "SYNTHETIC 图片条款；适用于研究生，每次只准测试一次。"
    (package / "flow.png").write_bytes(image)
    (package / "flow.txt").write_bytes(text.encode())
    document["attachments"] = [{"attachment_id": "synthetic-flow",
                                "url": "https://www.cdut.edu.cn/SYNTHETIC-flow.png",
                                "file": "flow.png", "format": "png", "text_file": "flow.txt",
                                "text_verified": True}]
    clause.update({"quote": text, "locator": {"file": "flow.txt", "start": 0, "end": len(text)},
                   "applicability": {"audiences": ["graduate"], "audience_quote": "适用于研究生"},
                   "review": {"checked_by": "SYNTHETIC visual checker",
                              "checked_at": "2026-10-14", "body_sha256": digest(BODY.encode()),
                              "content_sha256": digest(text.encode()),
                              "attachment_sha256": digest(image)}})
    save(package, [document])
    snapshot, _, report = build(package, base_snapshot())
    assert not report["failed"]
    chunk = next(c for c in snapshot.chunks if c.verification_status == "official_document")
    assert chunk.ocr and chunk.audiences == ("graduate",)
    (package / "flow.png").write_bytes(image + b"SYNTHETIC changed original")
    save(package, [document])
    assert build(package, base_snapshot())[2]["failed"][0]["reason"] == (
        "review_attachment_hash_mismatch"
    )


def test_document_failure_does_not_stop_other_documents(tmp_path: Path) -> None:
    package, document, _ = capture(tmp_path)
    save(package, [document, {"document_id": "synthetic-failed", "url": SYNTHETIC_URL,
                             "status": "failed", "failure_reason": "SYNTHETIC timeout"}])
    snapshot, _, report = build(package, base_snapshot())
    assert len(snapshot.chunks) == 3 and len(report["adopted"]) == len(report["failed"]) == 1


def test_cross_source_parent_fails_only_its_document_before_last_success_mutation(
    tmp_path: Path,
) -> None:
    package, document, clause = capture(tmp_path)
    parent = {**clause, "clause_id": "parent", "source_id": "cdut:source:synthetic-legacy-0"}
    child = {**clause, "clause_id": "child", "source_id": "cdut:source:synthetic-legacy-1",
             "structure": {"parent_chunk_id": "cdut:chunk:official:synthetic:parent"}}
    document["clauses"] = [parent, child]
    good = {**document, "document_id": "synthetic-good", "clauses": [clause]}
    save(package, [document, good])
    base = base_snapshot()
    result, raw, report = build(package, base)
    assert report["failed"] == [{"document_id": "synthetic", "reason": "invalid_parent_source",
                                 "last_success_preserved": True}]
    assert report["adopted"][0]["document_id"] == "synthetic-good"
    assert len(result.chunks) == len(base.chunks) + 1
    remaining_sources = {s.source_id: s for s in result.sources}
    assert all(remaining_sources[s.source_id] == s for s in base.sources)
    assert all(c in result.chunks for c in base.chunks)
    provenance = json.loads(raw[PROVENANCE])["documents"]
    assert "synthetic" not in provenance and "synthetic-good" in provenance


@pytest.mark.parametrize(
    "field,value,reason", [
        ("title", [], "missing_source_identity"),
        ("publisher", 3, "missing_source_identity"),
        ("url", 3, "invalid_source_url"),
        ("clauses", [None], "invalid_clause"),
        ("attachments", {}, "invalid_capture_artifacts"),
    ],
)
def test_malformed_document_is_rejected_without_aborting_good_document(
    tmp_path: Path, field: str, value: object, reason: str,
) -> None:
    package, document, _ = capture(tmp_path)
    malformed = {**document, "document_id": "synthetic-malformed", field: value}
    save(package, [document, malformed])
    result, _, report = build(package, base_snapshot())
    assert len(result.chunks) == 3 and len(report["adopted"]) == 1
    assert report["failed"][0]["reason"] == reason


def test_non_object_document_is_reported_individually_and_invalid_package_stays_unusable(
    tmp_path: Path,
) -> None:
    package, document, _ = capture(tmp_path)
    (package / "manifest.json").write_bytes(canonical({"schema_version": 1,
                                                     "documents": [document, []]}))
    result, _, report = build(package, base_snapshot())
    assert len(result.chunks) == 3 and len(report["adopted"]) == 1
    assert report["failed"][0]["reason"] == "invalid_document"
    extracted = extract(package)
    assert extracted["documents"][0]["status"] == "extracted"
    assert extracted["documents"][1]["reason"] == "invalid_document"
    (package / "manifest.json").write_bytes(b"[]")
    with pytest.raises(ValueError, match="invalid_capture_manifest"):
        build(package, base_snapshot())


def test_annotation_cli_isolates_malformed_captures_and_writes_checked_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    package, document, clause = capture(tmp_path)
    bad_artifacts = {**document, "document_id": "synthetic-malformed", "attachments": {}}
    (package / "manifest.json").write_bytes(canonical({"schema_version": 1,
                                                     "documents": [document, [], bad_artifacts]}))
    annotations = tmp_path / "annotations.json"
    annotations.write_bytes(canonical({"documents": [{"document_id": "synthetic",
                                                     "clauses": [clause]}]}))
    base, output = tmp_path / "base", tmp_path / "candidate"
    write_candidate(base, base_snapshot())
    script = Path(__file__).resolve().parents[1] / "scripts/official_knowledge.py"
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr("sys.argv", [str(script), "compile", "--package", str(package),
                                    "--annotations", str(annotations), "--base", str(base),
                                    "--output", str(output)])
    runpy.run_path(str(script), run_name="__main__")
    report = json.loads(capsys.readouterr().out)
    assert report["candidate_written"] and not report["published"]
    assert len(report["adopted"]) == 1 and len(report["failed"]) == 2
    assert len(read_candidate(output).chunks) == 3
    assert not (base / "current.json").exists()


@pytest.mark.parametrize("rows", [[[]], [{"document_id": [], "clauses": []}]])
def test_annotation_cli_rejects_malformed_annotation_mapping_without_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], rows: list[object],
) -> None:
    package, _, _ = capture(tmp_path)
    annotations = tmp_path / "annotations.json"
    annotations.write_bytes(canonical({"documents": rows}))
    base, output = tmp_path / "base", tmp_path / "candidate"
    write_candidate(base, base_snapshot())
    script = Path(__file__).resolve().parents[1] / "scripts/official_knowledge.py"
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr("sys.argv", [str(script), "compile", "--package", str(package),
                                    "--annotations", str(annotations), "--base", str(base),
                                    "--output", str(output)])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(script), run_name="__main__")
    assert exit_info.value.code == 2 and not output.exists()
    assert "active knowledge unchanged" in capsys.readouterr().err


def test_package_paths_and_cross_document_clause_ids_are_rejected(tmp_path: Path) -> None:
    package, document, clause = capture(tmp_path)
    document["body_file"] = "../outside.txt"
    save(package, [document])
    assert build(package, base_snapshot())[2]["failed"][0]["reason"] == "unsafe_file_path"
    document["body_file"] = "body.txt"
    document["url"] = "https://www.cdut.edu.cn/SYNTHETIC-other-document"
    clause["clause_id"] = "cdut:chunk:synthetic-legacy-0"
    save(package, [document])
    assert build(package, base_snapshot())[2]["failed"][0]["reason"] == (
        "clause_id_owned_by_other_document"
    )


def test_pdf_and_xlsx_magic_reject_html_and_parse_synthetic_cells(tmp_path: Path) -> None:
    for expected in ("pdf", "xlsx"):
        with pytest.raises(ValueError):
            attachment_format(b"<html>SYNTHETIC $_ts 412 Precondition Failed</html>", expected)
    attachment_format(b"%PDF-1.7\nSYNTHETIC signature only", "pdf")
    out = io.BytesIO()
    with ZipFile(out, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/worksheets/sheet1.xml", (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row><c r="A1" t="inlineStr"><is><t>SYNTHETIC cell</t></is></c>'
            '<c r="B1"><v>3</v></c></row></sheetData></worksheet>'
        ))
    path = tmp_path / "synthetic.xlsx"
    path.write_bytes(out.getvalue())
    text = parse_attachment(path, "xlsx")
    assert "A1=SYNTHETIC cell" in text and "B1=3" in text


def test_catalog_evidence_is_bound_and_archived_without_adopting_link_titles(
    tmp_path: Path,
) -> None:
    package, document, _ = capture(tmp_path)
    catalog = b"<html>SYNTHETIC catalog link only</html>"
    (package / "catalog.html").write_bytes(catalog)
    manifest = {"schema_version": 1, "documents": [document],
                "discovery_files": [{"file": "catalog.html", "sha256": digest(catalog)}]}
    (package / "manifest.json").write_bytes(canonical(manifest))
    snapshot, raw, _ = build(package, base_snapshot())
    assert list(raw.values()).count(catalog) == 1
    assert not any("catalog link" in c.text for c in snapshot.chunks)
    (package / "catalog.html").write_bytes(b"SYNTHETIC tampered catalog")
    with pytest.raises(ValueError, match="discovery_file_hash_mismatch"):
        build(package, base_snapshot())


def test_saved_embedded_asset_keeps_unknown_original_url_and_bound_bytes(tmp_path: Path) -> None:
    package, document, _ = capture(tmp_path)
    image = b"\x89PNG\r\n\x1a\nSYNTHETIC saved embedded image"
    (package / "flow.png").write_bytes(image)
    document["capture_assets"] = [{
        "asset_id": "synthetic-embedded", "file": "flow.png", "format": "png",
        "source_url": None, "local_ref": "./SYNTHETIC_files/flow.png",
        "sha256": digest(image), "text_verified": False,
    }]
    save(package, [document])
    _, raw, report = build(package, base_snapshot())
    assert not report["failed"] and image in raw.values()
    provenance = json.loads(raw[PROVENANCE])["documents"]["synthetic"]
    revision = provenance["versions"][provenance["current_revision"]]
    assert revision["capture_assets"][0]["source_url"] is None
    (package / "flow.png").write_bytes(image + b"SYNTHETIC tampering")
    assert build(package, base_snapshot())[2]["failed"][0]["reason"] == "attachment_hash_mismatch"


def test_capture_manifest_history_is_preserved_across_explicit_imports(tmp_path: Path) -> None:
    package, document, _ = capture(tmp_path)
    first, raw, _ = build(package, base_snapshot())
    previous = {key for key in raw if key.startswith("official/captures/")}
    document["collection_note"] = "SYNTHETIC explicit second import"
    save(package, [document])
    _, updated, report = build(package, first, prior_raw=raw)
    assert not report["failed"]
    assert previous < {key for key in updated if key.startswith("official/captures/")}


def test_provenance_tampering_atomic_publication_index_and_rollback(tmp_path: Path) -> None:
    package, _, _ = capture(tmp_path)
    base = base_snapshot()
    new, raw, _ = build(package, base)
    old_dir, candidate, store = tmp_path / "old", tmp_path / "new", tmp_path / "store"
    write_candidate(old_dir, base)
    write_candidate(candidate, new, raw)
    assert embed_candidate(candidate, lambda texts: [[1.0, 0.0] for _ in texts],
                           "SYNTHETIC embeddings", 2) == len(new.chunks)
    assert read_candidate(candidate) == new
    assert publish(old_dir, store, None) == base.version
    assert publish(candidate, store, base.version) == new.version
    hits = SnapshotStore(store).acquire()
    assert hits is not None
    result = hits.search("每学年最多三次", RetrievalFilters(today=date(2026, 10, 14)), 3)
    assert any(h.knowledge_version == new.version and "chars[" in h.chunk.locator for h in result)
    with pytest.raises(ValueError):
        publish(old_dir, store, base.version)
    assert rollback(store, base.version, new.version) == base.version
    (candidate / "raw" / PROVENANCE).write_bytes(b"SYNTHETIC tampered provenance")
    with pytest.raises(ValueError, match="checksum"):
        read_candidate(candidate)
