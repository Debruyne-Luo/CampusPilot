"""Import a reviewed knowledge package directory (sources.json, chunks.jsonl, teachers).

Only the explicitly named files are read; anything else in the package directory (notably
browser-raw/, which holds the reviewer's personal login pages) is never opened. The result
is the previous approved snapshot plus the package, written as a candidate directory that
`publish` can later promote. Teacher rows keep only name, title, department, office,
research areas and publicly listed e-mail (with the page it came from); never phones.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from campuspilot.rag import KnowledgeSnapshot, RagChunk, RagSource, canonical, digest, make_snapshot

PACKAGE_FILES = ("sources.json", "chunks.jsonl", "teachers_merged.json", "teacher_conflicts.json")
TEACHER_FILES = ("teachers_merged.json", "teacher_conflicts.json")
UNREADABLE = re.compile(r"[^，。；;\n]*\[无法识别\][^，。；;\n]*[，。；;]?")


def drop_unreadable(text: str) -> str:
    """OCR placeholders are never surfaced: the clause holding one is removed entirely."""
    return re.sub(r"\n{3,}", "\n\n", UNREADABLE.sub("", text)).strip()


TEMPORAL = {"current": "current", "historical": "historical", "superseded": "superseded"}
STALE_STATUSES = {"expired", "possibly_stale"}
PHONE = re.compile(r"(?<![\w/.-])(?:1[3-9]\d{9}|0\d{2,3}-?\d{7,8}|\d{8})(?![\w/.-])")
DEPARTMENT = "计算机与网络安全学院（示范性软件学院）"


def _read(package: Path, name: str) -> bytes:
    if name not in PACKAGE_FILES:
        raise ValueError("Only package data files may be read")
    path = (package / name).resolve()
    if not path.is_relative_to(package.resolve()) or "browser-raw" in path.parts:
        raise ValueError("Unsafe package path")
    return path.read_bytes()


def audiences(applicability: str) -> list[str]:
    if "研究生" in applicability and "本科" not in applicability:
        return ["graduate"]
    if "本科" in applicability and "研究生" not in applicability:
        return ["undergraduate"]
    return ["all"]


def email_page(row: dict[str, Any]) -> str:
    source = row.get("email_source", "")
    if not row.get("email"):
        return ""
    if source.startswith("A"):
        return row.get("faculty_homepage_url") or row.get("cist_profile_url") or ""
    return row.get("cist_profile_url") or ""


def teacher_roster(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Allowed fields only. Merged main columns already hold the faculty-platform value."""
    roster = []
    for row in rows:
        if PHONE.search(row.get("email", "")) or row.get("phone"):
            raise ValueError("Phone numbers are not ingested")
        office = "".join(x for x in (row.get("building", ""), row.get("room", "")) if x)
        roster.append(
            {
                "name": row["name"],
                "title": row.get("title", ""),
                "department": DEPARTMENT,
                "office": office,
                "research_areas": row.get("research_areas", ""),
                "email": row.get("email", ""),
                "email_source_page": email_page(row),
                "profile_url": row.get("faculty_homepage_url") or row.get("cist_profile_url") or "",
                "chunk_id": f"cdut:chunk:teacher:{row['name']}",
            }
        )
    return roster


def teacher_text(t: dict[str, Any]) -> str:
    parts = [f"{t['name']}，成都理工大学{t['department']}教师"]
    if t["title"]:
        parts.append(f"职称：{t['title']}")
    if t["office"]:
        parts.append(f"办公地点：{t['office']}")
    if t["research_areas"]:
        parts.append(f"研究方向：{t['research_areas']}")
    if t["email"]:
        parts.append(f"公开邮箱：{t['email']}（见其公开主页）")
    return "；".join(parts) + "。"


def resolve_conflicts(conflicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """No page dates are comparable in this package, so the faculty-platform value wins."""
    return [
        {
            "name": c["name"],
            "field": c["field"],
            "kept": c.get("value_A") or "",
            "other": c.get("value_B") or "",
            "rule": "faculty_platform_value (no comparable page dates)",
            "note": c.get("note") or "",
        }
        for c in conflicts
    ]


def build(
    package: Path, base: KnowledgeSnapshot, approval: dict[str, Any]
) -> tuple[KnowledgeSnapshot, dict[str, bytes], dict[str, Any]]:
    """Teacher files are optional (the WeChat package has none)."""
    names = [n for n in PACKAGE_FILES if n not in TEACHER_FILES or (package / n).exists()]
    files = {name: _read(package, name) for name in names}
    approval_id, reviewer = approval["approval_id"], approval["reviewer"]
    approved_at = date.fromisoformat(approval["approved_at"])
    raw_sources = json.loads(files["sources.json"])
    raw_chunks = [json.loads(x) for x in files["chunks.jsonl"].splitlines() if x.strip()]
    review = {"verification_status": "verified", "reviewer": reviewer, "verified_at": approved_at}
    by_id = {s["source_id"]: s for s in raw_sources}
    sources = [
        RagSource(
            source_id=s["source_id"],
            title=s["title"],
            url=s["url"],
            publisher=s["publisher"],
            applicability=s.get("applicability") or s.get("audience") or "未注明",
            temporal_status=TEMPORAL.get(s["temporal_status"], "unknown"),  # type: ignore[arg-type]
            content_scope=s.get("content_scope") or "unknown",
            **review,
        )
        for s in raw_sources
    ]
    roster = teacher_roster(json.loads(files.get("teachers_merged.json", b"[]")))
    teacher_by_chunk = {t["chunk_id"]: t for t in roster}
    for c in raw_chunks:
        if c["chunk_id"] in teacher_by_chunk:
            teacher_by_chunk[c["chunk_id"]]["source_id"] = c["source_id"]
    chunks: list[RagChunk] = []
    excluded: list[dict[str, str]] = []
    stale_ids: list[str] = []
    for c in raw_chunks:
        if c.get("excluded_from_retrieval"):
            excluded.append(
                {"chunk_id": c["chunk_id"], "exclude_reason": c.get("exclusion_reason") or ""}
            )
            continue
        source = by_id[c["source_id"]]
        text, kind = c["text"], c.get("kind", "fact")
        if c["topic_id"] == "teacher_lookup":
            text, kind = teacher_text(teacher_by_chunk[c["chunk_id"]]), "fact"
        elif digest(text.encode()) != c["text_sha256"]:
            raise ValueError("Package chunk hash mismatch")
        ocr = bool(c.get("ocr")) or kind == "official_image_ocr"
        if ocr:
            text = drop_unreadable(text)
        stale = bool(
            c.get("stale_source")
            or source.get("stale")
            or source["temporal_status"] in STALE_STATUSES
        )
        if stale:
            stale_ids.append(c["chunk_id"])
        chunks.append(
            RagChunk(
                chunk_id=c["chunk_id"],
                source_id=c["source_id"],
                topic_id=c["topic_id"],
                title=c["title"],
                text=text,
                locator=c.get("locator") or c["title"],
                aliases=c.get("aliases") or "",
                kind=kind
                if kind in {"fact", "historical", "index_only", "deprecated", "limitation"}
                else "fact",
                text_sha256=digest(text.encode()),
                approval_id=approval_id,
                audiences=tuple(audiences(source.get("applicability") or "")),
                stale=stale,
                ocr=ocr,
                **review,
            )
        )
    snapshot = make_snapshot(
        (*base.sources, *sources),
        (*base.chunks, *chunks),
        digest(b"".join(digest(files[n]).encode() for n in names)),
    )
    conflicts = resolve_conflicts(json.loads(files.get("teacher_conflicts.json", b"[]")))
    raw = {f"package/{n}": files[n] for n in names}
    if roster:
        raw["package/teachers_roster.json"] = canonical(roster)
        raw["package/teacher_conflicts_resolved.json"] = canonical(conflicts)
    raw["APPROVAL_RECORD.json"] = canonical(
        {**approval, "file_sha256": {n: digest(files[n]) for n in names}}
    )
    report = {
        "sources": len(sources),
        "chunks": len(chunks),
        "excluded": excluded,
        "stale_chunks": stale_ids,
        "teachers": len(roster),
        "conflicts": len(conflicts),
        "ocr_chunks": sum(c.ocr for c in chunks),
        "base_version": base.version,
        "version": snapshot.version,
    }
    return snapshot, raw, report
