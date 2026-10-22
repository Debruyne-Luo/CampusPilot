"""One scope policy for direct retrieval and permission-checked knowledge tools."""

from __future__ import annotations

import re
from datetime import date

from pydantic import JsonValue

from campuspilot.rag import RagChunk, RetrievalFilters

CAMPUS_NAMES = {
    "成都校区": "chengdu", "成都": "chengdu", "本部": "chengdu",
    "宜宾校区": "yibin", "宜宾": "yibin", "峨眉校区": "emei", "峨眉": "emei",
    "全校": "all", "各校区": "all", "所有校区": "all",
}
AUDIENCE_NAMES = {"undergraduate": "本科生", "graduate": "研究生", "staff": "教职工"}


def page_status_question(question: str) -> bool:
    """Reading or recapturing a page is not proof that its service has reopened."""
    return bool(
        re.search(r"重新[抓采]|抓到|抓取成功|采集成功|网页能打开|页面能打开|页面可访问|网页可访问",
                  question)
        and re.search(r"恢复|重新上线|重新开放|重开", question)
    )


def campus_value(value: str) -> str:
    """Normalize explicit campus annotations; preserve unknown named campuses as distinct."""
    return CAMPUS_NAMES.get(value, value)


def query_filters(
    question: str, today: date, *, audience: str = "all", academic_year: str | None = None,
    campus: str = "chengdu", historical: bool = False, current_only: bool = False,
) -> RetrievalFilters:
    # Obsolete pages may establish a cessation notice, never a current operating procedure.
    historical = historical or (
        bool(re.search(r"旧|停用|停止|历史", question)) and page_status_question(question)
    )
    # Explicit user wording takes precedence over tool/model/context guesses.
    audiences = {name for name, words in (
        ("undergraduate", ("本科",)), ("graduate", ("研究生", "硕士", "博士")),
        ("staff", ("教职工",)),
    ) if any(word in question for word in words)}
    if len(audiences) == 1:
        audience = audiences.pop()
    elif audiences:
        audience = "all"
    # The university's name identifies the institution, not its Chengdu campus.
    campus_text = re.sub(r"成都理工(?:大学)?", "", question)
    named = {value for name, value in CAMPUS_NAMES.items() if name in campus_text}
    if len(named) == 1:
        campus = named.pop()
    elif named:
        campus = "all"  # comparisons require individually labelled evidence
    year = re.search(r"(20\d{2})\s*[-—–至]\s*(20\d{2})", question)
    return RetrievalFilters(
        today=today, audience="all" if audience == "unknown" else audience,
        academic_year=f"{year[1]}-{year[2]}" if year else academic_year,
        campus=campus_value(campus), historical=historical,
        current_only=current_only or any(x in question for x in ("现行", "当前有效", "现在还")),
    )


def scope_notes(chunk: RagChunk, filters: RetrievalFilters) -> tuple[str, ...]:
    """Conditions needed to use this evidence; unknown source scope is a data gap."""
    notes: list[str] = []
    if "unknown" in chunk.audiences:
        notes.append("来源适用人群尚未确认")
    elif filters.audience == "all" and "all" not in chunk.audiences:
        names = [AUDIENCE_NAMES.get(a, a) for a in chunk.audiences if a != "unknown"]
        notes.append("仅适用于" + "、".join(names) if names else "来源适用人群尚未确认")
    if "unknown" in chunk.campuses:
        notes.append("来源适用校区尚未确认")
    elif filters.campus in {"all", "unknown"} and "all" not in chunk.campuses:
        labels = {"chengdu": "成都校区", "yibin": "宜宾校区", "emei": "峨眉校区"}
        notes.append("仅适用于" + "、".join(labels.get(c, c) for c in chunk.campuses))
    if chunk.academic_year and not filters.academic_year:
        notes.append("仅适用于" + chunk.academic_year + "学年")
    return tuple(notes)


def conditional_text(chunk: RagChunk, filters: RetrievalFilters) -> str:
    notes = scope_notes(chunk, filters)
    body = chunk.text
    for label, values in (("表头", chunk.table_headers), ("脚注", chunk.footnotes)):
        extra = [value for value in values if value not in body]
        if extra:
            body += "\n" + label + "：" + "；".join(extra)
    return ("适用限制：" + "；".join(notes) + "。\n" if notes else "") + body


def evidence_metadata(chunk: RagChunk, filters: RetrievalFilters) -> dict[str, JsonValue]:
    """One provenance/condition serialization for direct answers and Agent tool results."""
    return {
        "document_id": chunk.document_id, "revision_id": chunk.revision_id,
        "section_id": chunk.section_id, "parent_chunk_id": chunk.parent_chunk_id,
        "heading_path": list(chunk.heading_path), "clause_number": chunk.clause_number,
        "locator": chunk.locator, "text_sha256": chunk.text_sha256,
        "table_headers": list(chunk.table_headers), "footnotes": list(chunk.footnotes),
        "scope_notes": list(scope_notes(chunk, filters)),
        "conditional_text": conditional_text(chunk, filters),
    }
