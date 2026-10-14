"""Offline, evidence-bound adoption of official browser exports.

Collection, extraction and adoption are separate steps. Extraction never grants authority;
only annotated clauses bound to a complete document can enter a candidate snapshot. This
module does not crawl, detect changes, publish, infer repeal, or read browser credentials.
"""

from __future__ import annotations

import importlib
import io
import json
import re
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from campuspilot.knowledge import CHINA, official_url
from campuspilot.rag import KnowledgeSnapshot, RagChunk, RagSource, canonical, digest, make_snapshot

MAX_FILE = 20_000_000
MAX_PACKAGE = 80_000_000
ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")
CHALLENGE = re.compile(
    r"\$_ts|\b412\s+Precondition|access denied|verify (?:you are|your browser)|"
    r"checking your browser|安全验证|访问过于频繁|请开启JavaScript", re.IGNORECASE
)
AUDIENCE_TERMS = {
    "undergraduate": ("本科",), "graduate": ("研究生", "硕士", "博士"),
    "staff": ("教师", "教职工", "学校管理员"), "alumni": ("校友", "毕业生"),
    "visitor": ("访客",), "all": ("所有人", "全体师生", "师生", "全部人员"),
}
PROVENANCE = "official/provenance.json"


def capture_artifacts(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Attachments and saved embedded assets share byte and transcription checks."""
    attachments, assets = doc.get("attachments", []), doc.get("capture_assets", [])
    _require(isinstance(attachments, list) and isinstance(assets, list),
             "invalid_capture_artifacts")
    _require(all(isinstance(item, dict) for item in [*attachments, *assets]),
             "invalid_capture_artifact")
    return [*attachments, *assets]


class InvalidDocument(ValueError):
    """Reason codes contain no source body, login material or exception details."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise InvalidDocument(reason)


def _file(package: Path, name: str) -> bytes:
    _require(isinstance(name, str) and bool(name), "missing_file")
    parts = PurePosixPath(name.replace("\\", "/")).parts
    _require(not PurePosixPath(name).is_absolute() and ":" not in name,
             "unsafe_file_path")
    _require(not any(p in {".", ".."} for p in parts), "unsafe_file_path")
    path = package.joinpath(*parts)
    _require(path.resolve().is_relative_to(package.resolve()), "unsafe_file_path")
    _require(not any(p.is_symlink() for p in (path, *path.parents)), "symlink_file")
    _require(path.is_file() and path.stat().st_size <= MAX_FILE, "missing_or_large_file")
    return path.read_bytes()


def _text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeError as exc:
        raise InvalidDocument("body_must_be_utf8") from exc


def _date(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


def _collection_value(doc: dict[str, Any]) -> str:
    return str(doc.get("collected_at") or doc["collected_on"])


def _collection_day(doc: dict[str, Any]) -> date:
    value = _collection_value(doc)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        _require(doc.get("collection_precision") == "day", "collection_precision_required")
        return date.fromisoformat(value)
    collected = datetime.fromisoformat(value)
    _require(collected.tzinfo is not None, "collection_time_requires_timezone")
    _require(doc.get("collection_precision", "second") in {"second", "minute"},
             "invalid_collection_precision")
    return collected.astimezone(CHINA).date()


def _check_collection_order(doc: dict[str, Any], prior: dict[str, Any], body_hash: str) -> None:
    """Reject older captures; a day-only timestamp cannot order changed same-day bodies."""
    current_day, previous_day = _collection_day(doc), _collection_day(prior)
    _require(current_day >= previous_day, "older_collection_cannot_replace_last_success")
    if current_day != previous_day:
        return
    current_value, previous_value = _collection_value(doc), _collection_value(prior)
    if len(current_value) == 10 or len(previous_value) == 10:
        _require(body_hash == prior.get("body_sha256"), "collection_time_order_unknown")
        return  # Equal day precision permits an unchanged repeat without inventing an order.
    _require(datetime.fromisoformat(current_value) >= datetime.fromisoformat(previous_value),
             "older_collection_cannot_replace_last_success")


def _url_identity(value: str) -> str:
    # HTTPS is mandatory, but legacy evidence may retain an HTTP URL from its first import.
    u = urlsplit(value)
    return (u.hostname or "").lower() + u.path + ("?" + u.query if u.query else "")


def _id(value: Any) -> str:
    _require(isinstance(value, str) and bool(ID.fullmatch(value)), "invalid_stable_id")
    return str(value)


def attachment_format(data: bytes, expected: str) -> None:
    """Check actual payloads before parsing; an HTML 412 page is never an attachment."""
    _require(not CHALLENGE.search(data[:8000].decode("utf-8", errors="ignore")),
             "attachment_challenge")
    if expected == "pdf":
        _require(data.startswith(b"%PDF-"), "invalid_pdf_magic")
    elif expected == "xlsx":
        _require(data.startswith(b"PK\x03\x04"), "invalid_xlsx_magic")
        try:
            with ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                _require({"[Content_Types].xml", "xl/workbook.xml"} <= names,
                         "invalid_xlsx_package")
                _require(sum(x.file_size for x in archive.infolist()) <= MAX_PACKAGE,
                         "expanded_attachment_too_large")
        except BadZipFile as exc:
            raise InvalidDocument("invalid_xlsx_package") from exc
    elif expected == "png":
        _require(data.startswith(b"\x89PNG\r\n\x1a\n"), "invalid_png_magic")
    elif expected == "jpeg":
        _require(data.startswith(b"\xff\xd8\xff"), "invalid_jpeg_magic")
    else:
        raise InvalidDocument("unsupported_attachment_format")


def parse_attachment(path: Path, expected: str) -> str:
    """Parse public PDF/XLSX files locally; PDF support is an optional maintenance extra."""
    data = path.read_bytes()
    _require(len(data) <= MAX_FILE, "attachment_too_large")
    attachment_format(data, expected)
    if expected == "pdf":
        try:
            pdf_reader = importlib.import_module("pypdf").PdfReader
        except ImportError as exc:
            raise InvalidDocument("pdf_parser_unavailable_install_pypdf") from exc
        reader = pdf_reader(io.BytesIO(data))
        return "\n\n".join(
            f"[page {i + 1}]\n{page.extract_text() or ''}"
            for i, page in enumerate(reader.pages)
        )
    _require(expected == "xlsx", "image_requires_checked_transcription")
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows: list[str] = []
    with ZipFile(io.BytesIO(data)) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ["".join(t.itertext()) for t in
                      ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))]
        for name in sorted(archive.namelist()):
            if not re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name):
                continue
            rows.append(f"[{name}]")
            tree = ElementTree.fromstring(archive.read(name))
            for row in tree.findall(".//s:sheetData/s:row", ns):
                cells = []
                for cell in row.findall("s:c", ns):
                    value = cell.findtext("s:v", default="", namespaces=ns)
                    if cell.get("t") == "s":
                        value = shared[int(value)] if value else ""
                    elif cell.get("t") == "inlineStr":
                        value = "".join(cell.find("s:is", ns).itertext())  # type: ignore[union-attr]
                    cells.append(f"{cell.get('r', '')}={value}")
                rows.append("\t".join(cells))
    return "\n".join(rows)


def load_package(package: Path) -> dict[str, Any]:
    data = json.loads(_file(package, "manifest.json"))
    _require(isinstance(data, dict) and data.get("schema_version") == 1
             and isinstance(data.get("documents"), list),
             "invalid_capture_manifest")
    _require(0 < len(data["documents"]) <= 200, "invalid_document_count")
    # Invalid individual records are reported by extract/build without aborting good documents.
    ids = [d["document_id"] for d in data["documents"]
           if isinstance(d, dict) and isinstance(d.get("document_id"), str)]
    _require(len(ids) == len(set(ids)), "duplicate_document_id")
    return dict(data)


def discovery_files(package: Path, manifest: dict[str, Any]) -> dict[str, bytes]:
    """Preserve explicitly selected catalog evidence; never scan arbitrary folders."""
    entries = manifest.get("discovery_files", [])
    _require(isinstance(entries, list) and len(entries) <= 200, "invalid_discovery_files")
    result: dict[str, bytes] = {}
    for entry in entries:
        _require(isinstance(entry, dict), "invalid_discovery_file")
        name = entry.get("file")
        _require(isinstance(name, str) and name not in result, "duplicate_discovery_file")
        content = _file(package, name)
        _require(entry.get("sha256") == digest(content), "discovery_file_hash_mismatch")
        result[name] = content
    _require(sum(map(len, result.values())) <= MAX_PACKAGE, "discovery_evidence_too_large")
    return result


def _document(package: Path, doc: dict[str, Any]) -> tuple[str, dict[str, bytes]]:
    _require(isinstance(doc, dict), "invalid_document")
    _id(doc.get("document_id"))
    _require(doc.get("status", "success") == "success", "collection_failed")
    _require(isinstance(doc.get("url"), str), "invalid_source_url")
    official_url(doc["url"])
    _require(doc.get("complete") is True, "incomplete_document")
    _require(doc.get("content_kind") in {"article", "guide"}, "not_document_body")
    _require(doc.get("channel") in {"browser_dom", "http"}, "unknown_capture_channel")
    _require(doc.get("access_scope") in {"public", "authenticated_general"},
             "unknown_access_scope")
    _require(not doc.get("contains_personal_data"), "personal_data_forbidden")
    _require(doc.get("access_scope") != "authenticated_general"
             or doc.get("channel") == "browser_dom", "authenticated_http_not_supported")
    _require(isinstance(doc.get("title"), str) and isinstance(doc.get("publisher"), str)
             and bool(doc["title"].strip() and doc["publisher"].strip()),
             "missing_source_identity")
    collected = _collection_day(doc)
    for field in ("published_on", "signed_on"):
        timestamp = _date(doc.get(field))
        _require(timestamp is None or timestamp <= collected, "future_source_date")
    name = doc["body_file"]
    files = {name: _file(package, name)}
    body = _text(files[name])
    _require(len(body.strip()) >= 40 and not CHALLENGE.search(body), "empty_or_challenge_body")
    _require(not re.search(r"<(?:html|script|iframe)\b", body, re.IGNORECASE),
             "body_must_be_visible_text")
    if doc.get("body_sha256"):
        _require(doc["body_sha256"] == digest(files[name]), "capture_body_hash_mismatch")
    if doc.get("original_file"):
        original = doc["original_file"]
        files[original] = _file(package, original)
    seen: set[str] = set()
    for attachment in capture_artifacts(doc):
        aid = _id(attachment.get("attachment_id") or attachment.get("asset_id"))
        _require(aid not in seen, "duplicate_attachment_id")
        seen.add(aid)
        if "attachment_id" in attachment:
            _require(isinstance(attachment.get("url"), str), "invalid_attachment_url")
            official_url(attachment["url"])
        elif attachment.get("source_url"):
            _require(isinstance(attachment["source_url"], str), "invalid_attachment_url")
            official_url(attachment["source_url"])
        else:
            _require(doc["channel"] == "browser_dom"
                     and attachment.get("format") in {"png", "jpeg"}
                     and bool(attachment.get("local_ref")), "unattributed_capture_asset")
        name = attachment["file"]
        files[name] = _file(package, name)
        attachment_format(files[name], attachment["format"])
        if attachment.get("sha256"):
            _require(attachment["sha256"] == digest(files[name]), "attachment_hash_mismatch")
        if attachment.get("text_file"):
            name = attachment["text_file"]
            files[name] = _file(package, name)
            _text(files[name])
    _require(sum(len(b) for b in files.values()) <= MAX_PACKAGE, "document_package_too_large")
    return body, files


def extract(package: Path) -> dict[str, Any]:
    """Suggest exact paragraphs with offsets, not approvals or inferred policy scopes."""
    manifest = load_package(package)
    output: list[dict[str, Any]] = []
    for doc in manifest["documents"]:
        document_id = doc.get("document_id") if isinstance(doc, dict) else None
        try:
            body, files = _document(package, doc)
            candidates: list[dict[str, Any]] = []
            for number, match in enumerate(re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", body), 1):
                quote = match.group().strip()
                if len(quote) < 8:
                    continue
                start = match.start() + len(match.group()) - len(match.group().lstrip())
                candidates.append({
                    "candidate_id": f"p{number:04d}", "clause_id": None, "quote": quote,
                    "locator": {"file": doc["body_file"], "start": start,
                                "end": start + len(quote)},
                    "disposition": "candidate", "review_required": True,
                    "applicability": {"audiences": [], "campuses": [], "conditions": [],
                                      "exceptions": [], "evidence_quotes": {}},
                })
            output.append({"document_id": document_id, "status": "extracted",
                           "body_sha256": digest(files[doc["body_file"]]),
                           "clauses": candidates})
        except (ValueError, OSError, KeyError, TypeError) as exc:
            output.append({"document_id": document_id, "status": "failed",
                           "reason": str(exc) if isinstance(exc, InvalidDocument)
                           else "invalid_capture"})
    return {"schema_version": 1, "authority": "candidate_only", "documents": output}


def _evidence(app: dict[str, Any], field: str, texts: tuple[str, ...]) -> str:
    quotes = app.get("evidence_quotes", {})
    _require(isinstance(quotes, dict), "invalid_applicability_evidence")
    quote = quotes.get(field, "")
    if field == "audiences":
        quote = quote or app.get("audience_quote", "")
    _require(isinstance(quote, str) and bool(quote) and any(quote in text for text in texts),
             "applicability_missing_exact_evidence")
    return str(quote)


def _date_in_quote(value: date, quote: str) -> bool:
    normalized = re.sub(r"[年月日/\.—–－]", "-", quote)
    normalized = re.sub(r"\s+", "", normalized)
    if re.search(
        rf"(?<!\d){value.year}-0?{value.month}-0?{value.day}(?!\d)", normalized
    ):
        return True
    # Only the omitted end year of the same explicit interval can inherit a year.
    # Do not infer a year rollover or carry a year between unrelated sentences.
    interval = re.search(
        r"(?<!\d)(\d{4})年(\d{1,2})月(\d{1,2})日\s*[—–－~～至到-]\s*"
        r"(\d{1,2})月(\d{1,2})日", quote
    )
    if not interval:
        return False
    year, first_month, first_day, last_month, last_day = map(int, interval.groups())
    return (value == date(year, last_month, last_day)
            and date(year, first_month, first_day) <= value)


def _generic_students(quote: str) -> bool:
    restricted = re.sub(r"(?:本科|研究|硕士|博士)(?:学生|生)?", "", quote)
    return "学生" in restricted


def _clause(
    clause: dict[str, Any], doc: dict[str, Any], files: dict[str, bytes], body: str,
    source_ids: set[str], checked_on: date,
) -> tuple[RagChunk, dict[str, Any]]:
    disposition = clause.get("disposition")
    _require(disposition in {"adopt", "limitation"}, "clause_not_adopted")
    _require(not clause.get("unresolved_conflict"), "unresolved_conflict")
    locator = clause["locator"]
    filename, start, end = locator["file"], locator["start"], locator["end"]
    allowed_text = {doc["body_file"]}
    images = set()
    for attachment in capture_artifacts(doc):
        if attachment.get("text_verified") is True and attachment.get("text_file"):
            allowed_text.add(attachment["text_file"])
            if attachment["format"] in {"png", "jpeg"}:
                images.add(attachment["text_file"])
    _require(filename in allowed_text, "unchecked_attachment_transcription")
    text = _text(files[filename])
    evidence_texts = (body,) if filename == doc["body_file"] else (body, text)
    _require(type(start) is int and type(end) is int and 0 <= start < end <= len(text),
             "invalid_quote_offsets")
    _require(clause["quote"] == text[start:end], "quote_locator_mismatch")
    _require(len(clause["quote"].strip()) > 2, "empty_clause")
    review = clause["review"]
    _require(isinstance(review, dict), "invalid_clause_review")
    _require(isinstance(review.get("checked_by"), str) and bool(review["checked_by"].strip()),
             "missing_clause_validator")
    _require(review.get("body_sha256") == digest(files[doc["body_file"]]),
             "review_body_hash_mismatch")
    if filename != doc["body_file"]:
        _require(review.get("content_sha256") == digest(files[filename]),
                 "review_attachment_text_hash_mismatch")
        attachment = next(a for a in capture_artifacts(doc) if a.get("text_file") == filename)
        _require(review.get("attachment_sha256") == digest(files[attachment["file"]]),
                 "review_attachment_hash_mismatch")
    _require(_date(review.get("checked_at")) == checked_on, "invalid_review_date")
    _require(checked_on >= _collection_day(doc),
             "review_predates_capture")
    app = clause.get("applicability", {})
    _require(isinstance(app, dict), "invalid_clause_applicability")
    audiences = app.get("audiences", [])
    _require(isinstance(audiences, list) and len(audiences) == len(set(audiences)),
             "invalid_audiences")
    if audiences:
        quote = _evidence(app, "audiences", evidence_texts)
        for audience in audiences:
            _require(audience in AUDIENCE_TERMS and (
                any(term in quote for term in AUDIENCE_TERMS[audience])
                or (audience in {"undergraduate", "graduate"} and _generic_students(quote))
            ),
                     "audience_not_supported")
    else:
        _require(disposition == "limitation" and bool(clause.get("limitation")),
                 "unknown_audience_requires_limitation")
        audiences = ["unknown"]
    valid_from, valid_until = _date(app.get("valid_from")), _date(app.get("valid_until"))
    for field, value in (("valid_from", valid_from), ("valid_until", valid_until)):
        if value:
            _require(_date_in_quote(value, _evidence(app, field, evidence_texts)),
                     "date_not_supported")
    academic_year = app.get("academic_year")
    if academic_year:
        _require(bool(re.fullmatch(r"\d{4}-\d{4}", academic_year)), "invalid_academic_year")
        quote = _evidence(app, "academic_year", evidence_texts)
        normalized = re.sub(r"\s+", "", re.sub(r"[—–－至]", "-", quote))
        _require(academic_year in normalized, "academic_year_not_supported")
    for field in ("campuses", "conditions", "exceptions"):
        _require(isinstance(app.get(field, []), list), "invalid_applicability_conditions")
        _require(all(isinstance(v, str) and v and any(v in t for t in evidence_texts)
                     for v in app.get(field, [])),
                 "condition_not_supported")
    ident = clause["clause_id"]
    if isinstance(ident, str) and ident.startswith("cdut:chunk:"):
        _require(bool(re.fullmatch(r"cdut:chunk:[a-zA-Z0-9:_-]+", ident)),
                 "invalid_stable_clause_id")
        chunk_id = ident
    else:
        chunk_id = f"cdut:chunk:official:{doc['document_id']}:{_id(ident)}"
    source_id = clause.get("source_id") or f"cdut:source:official:{doc['document_id']}"
    _require(source_id in source_ids, "invalid_clause_source_mapping")
    facts = clause["quote"]
    scope_parts = []
    for key, label in (("campuses", "校区"), ("conditions", "适用条件"),
                       ("exceptions", "例外条件")):
        if app.get(key):
            scope_parts.append(label + "：" + "；".join(app[key]))
    if clause.get("limitation"):
        scope_parts.append("适用限制（采集校验标注）：" + clause["limitation"])
    if scope_parts:
        facts += "\n" + "\n".join(scope_parts)
    source_hash = digest(files[filename])
    approval = "official:" + digest(canonical({
        "document_id": doc["document_id"], "body_sha256": review["body_sha256"],
        "clause": clause,
    }))[:24]
    chunk = RagChunk(
        chunk_id=chunk_id, source_id=source_id, topic_id=clause["topic_id"],
        title=clause.get("title") or doc["title"], text=facts,
        locator=f"{filename}:chars[{start}:{end}] sha256={source_hash}",
        aliases=clause.get("aliases", ""),
        kind="limitation" if disposition == "limitation" else "fact",
        text_sha256=digest(facts.encode()), verification_status="official_document",
        reviewer=review["checked_by"], verified_at=checked_on, approval_id=approval,
        audiences=tuple(audiences), academic_year=academic_year,
        valid_from=valid_from, valid_until=valid_until, ocr=filename in images,
    )
    return chunk, {"chunk_id": chunk_id, "source_id": source_id, "quote": clause["quote"],
                   "locator": locator, "content_sha256": source_hash,
                   "applicability": app, "review": review,
                   "disposition": disposition, "limitation": clause.get("limitation"),
                   "approval_id": approval}


def build(
    package: Path, base: KnowledgeSnapshot, *, prior_raw: dict[str, bytes] | None = None,
) -> tuple[KnowledgeSnapshot, dict[str, bytes], dict[str, Any]]:
    """Upsert validated stable clause IDs; a failed document changes none of its old data.

    ``prior_raw`` uses paths below the candidate's raw/ directory. Carry it from the base
    manifest to preserve previous successful original files and version relationships.
    """
    manifest = load_package(package)
    sources, chunks = {s.source_id: s for s in base.sources}, {c.chunk_id: c for c in base.chunks}
    catalog_files = discovery_files(package, manifest)
    raw = dict(prior_raw or {})
    previous = json.loads(raw.get(PROVENANCE, b'{"documents":{}}'))
    documents = previous.get("documents", {})
    _require(isinstance(documents, dict), "invalid_previous_provenance")
    exclusions: list[dict[str, str]] = []
    failed, adopted = [], []
    touched: set[str] = set()
    for doc in manifest["documents"]:
        document_id = doc.get("document_id") if isinstance(doc, dict) else None
        try:
            body, files = _document(package, doc)
            identity = _url_identity(doc["url"])
            previous_doc = documents.get(document_id)
            _require(not previous_doc or previous_doc["url_identity"] == identity,
                     "document_id_rebound_to_different_url")
            if previous_doc:
                prior_version = previous_doc["versions"][previous_doc["current_revision"]]
                _check_collection_order(doc, prior_version, digest(files[doc["body_file"]]))
            legacy = {s.source_id for s in base.sources
                      if _url_identity(s.url) == identity
                      and not s.source_id.startswith("cdut:source:official:")}
            explicit = set(doc.get("legacy_source_ids", []))
            _require(explicit <= legacy, "legacy_source_url_mismatch")
            source_id = f"cdut:source:official:{document_id}"
            source_ids = legacy | {source_id}
            accepted: list[RagChunk] = []
            bindings: list[dict[str, Any]] = []
            checked_dates: list[date] = []
            clauses = doc.get("clauses", [])
            _require(isinstance(clauses, list), "invalid_document_clauses")
            for clause in clauses:
                _require(isinstance(clause, dict), "invalid_clause")
                if clause.get("disposition") == "exclude":
                    _require(bool(clause.get("exclusion_reason")), "missing_exclusion_reason")
                    exclusions.append({"chunk_id": str(clause.get("clause_id", "")),
                                       "exclude_reason": clause["exclusion_reason"]})
                    continue
                review = clause.get("review", {})
                _require(isinstance(review, dict), "invalid_clause_review")
                checked_on = _date(review.get("checked_at"))
                _require(checked_on is not None, "missing_clause_review")
                assert checked_on is not None
                chunk, binding = _clause(clause, doc, files, body, source_ids, checked_on)
                _require(chunk.chunk_id not in touched
                         and chunk.chunk_id not in {c.chunk_id for c in accepted},
                         "duplicate_clause_id")
                old = chunks.get(chunk.chunk_id)
                _require(old is None or old.source_id in source_ids,
                         "clause_id_owned_by_other_document")
                accepted.append(chunk)
                bindings.append(binding)
                checked_dates.append(checked_on)
            _require(bool(accepted), "no_validated_clauses")
            revision = digest(canonical({
                "document": doc, "files_sha256": {n: digest(b) for n, b in files.items()},
            }))
            prefix = f"official/documents/{document_id}/{revision}/"
            for name, content in files.items():
                raw[prefix + name.replace("\\", "/")] = content
            scope = {"audiences": sorted({a for c in accepted for a in c.audiences}),
                     "clauses": [b["applicability"] for b in bindings],
                     "access_scope": doc["access_scope"]}
            for sid in {c.source_id for c in accepted}:
                sources[sid] = RagSource(
                    source_id=sid, title=doc["title"], url=doc["url"],
                    publisher=doc["publisher"], applicability=json.dumps(scope, ensure_ascii=False),
                    temporal_status=sources[sid].temporal_status if sid in legacy else "unknown",
                    content_scope="complete_official_browser_dom" if doc["channel"] == "browser_dom"
                    else "complete_official_http_response",
                    verification_status="official_document", reviewer="official-source-validator",
                    verified_at=max(checked_dates),
                )
            for chunk in accepted:
                chunks[chunk.chunk_id] = chunk
                touched.add(chunk.chunk_id)
            version = {
                "revision": revision, "base_knowledge_version": base.version,
                "previous_revision": previous_doc.get("current_revision") if previous_doc else None,
                "collected_at": _collection_value(doc), "channel": doc["channel"],
                "collection_precision": doc.get("collection_precision", "second"),
                "collection_note": doc.get("collection_note"),
                "original_kind": "rendered_dom" if doc["channel"] == "browser_dom"
                else "server_response", "published_on": doc.get("published_on"),
                "signed_on": doc.get("signed_on"), "access_scope": doc["access_scope"],
                "body_sha256": digest(files[doc["body_file"]]),
                "files": {n: {"path": prefix + n.replace("\\", "/"), "sha256": digest(b)}
                          for n, b in files.items()},
                "attachments": doc.get("attachments", []),
                "capture_assets": doc.get("capture_assets", []), "clauses": bindings,
                "replacement_policy": "stable_clause_upsert_no_inferred_repeal",
            }
            history = dict(previous_doc.get("versions", {})) if previous_doc else {}
            if revision not in history:
                history[revision] = version
            documents[document_id] = {
                "url_identity": identity, "url": doc["url"], "title": doc["title"],
                "publisher": doc["publisher"], "legacy_source_ids": sorted(legacy),
                "current_revision": revision, "versions": history,
            }
            adopted.append({"document_id": document_id, "clauses": len(accepted),
                            "revision": revision, "legacy_source_ids": sorted(legacy)})
        except (ValueError, OSError, KeyError, TypeError) as exc:
            failed.append({"document_id": document_id,
                           "reason": str(exc) if isinstance(exc, InvalidDocument)
                           else "invalid_capture_or_annotation",
                           "last_success_preserved": True})
    report: dict[str, Any] = {
        "base_version": base.version, "adopted": adopted, "failed": failed,
        "adopted_clauses": len(touched), "excluded": exclusions, "published": False,
    }
    if not adopted:
        return base, raw, report | {"version": base.version, "unchanged": True}
    raw[PROVENANCE] = canonical({"schema_version": 1, "documents": documents})
    raw["official/capture_manifest.json"] = canonical(manifest)
    capture_hash = digest(canonical(manifest))
    raw[f"official/captures/{capture_hash}/manifest.json"] = canonical(manifest)
    for name, content in catalog_files.items():
        normalized_name = name.replace("\\", "/")
        raw[f"official/captures/{capture_hash}/discovery_sources/{normalized_name}"] = content
    if manifest.get("discovery"):
        raw["official/discovery.json"] = canonical(manifest["discovery"])
        raw[f"official/captures/{capture_hash}/discovery.json"] = canonical(manifest["discovery"])
    # Source-package hash binds the preserved history and newly checked raw bytes.
    package_hash = digest(canonical({n: digest(b) for n, b in sorted(raw.items())}))
    snapshot = make_snapshot(tuple(sources.values()), tuple(chunks.values()), package_hash)
    return snapshot, raw, report | {"version": snapshot.version,
                                   "unchanged": snapshot.version == base.version}
