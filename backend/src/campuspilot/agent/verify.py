"""Answer verification shared by the rule runtime and the agent loop.

Every check returns a failure code (or None). Codes: invalid_response (unknown or missing
citations, URLs, coordinates, numbers absent from evidence) and required_premise_missing.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import date

UNSAFE_TEXT = re.compile(
    r"https?://|\d{1,3}\.\d{4,}|"
    r"(?:经度|纬度|坐标)\D{0,12}[-+]?\d|"
    r"[-+]?\d{1,3}\.\d+\s*[,，]\s*[-+]?\d{1,3}\.\d+"
)
# Bare domains (mail.stu.cdut.edu.cn, www.example.com) are links too; links are rendered
# from citations by the program, never typed by the model.
BARE_DOMAIN = re.compile(
    r"(?<![\w@.-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:cn|com|net|org|edu|gov|io|top|info|xyz|me|cc)(?![\w.-]*[a-z0-9])",
    re.IGNORECASE,
)
NUMBER = re.compile(r"\d{3,}(?:[-.]\d+)*")
BALANCE_PREMISE = re.compile(r"(?:余额|账户).{0,20}(?:大于|超过|>)\s*20")
CALENDAR_DATE = re.compile(
    r"(?<!\d)(20\d{2})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})(?:日)?(?!\d)"
)
MONTH_DAY = re.compile(r"(?<!\d)(\d{1,2})\s*(?:月|/)\s*(\d{1,2})(?:日|号)?(?!\d)")
TIME_NUMBER = r"(?:\d{1,2}|[零〇一二两三四五六七八九十]{1,3})"
CLOCK = re.compile(
    rf"(?:(凌晨|早上|上午|中午|下午|晚上)\s*)?"
    rf"(?<![\d零〇一二两三四五六七八九十])({TIME_NUMBER})\s*"
    rf"(?:[:：]\s*(\d{{1,2}})|(?:时|点)(?:\s*({TIME_NUMBER}|半)\s*分?)?)"
    rf"(?!\d|\s*(?:元|块))"
)


def _calendar_dates(text: str) -> list[tuple[tuple[int, int], date | None]]:
    values: list[tuple[tuple[int, int], date | None]] = []
    for match in CALENDAR_DATE.finditer(text):
        try:
            value = date(int(match[1]), int(match[2]), int(match[3]))
        except ValueError:
            values.append((match.span(), None))
            continue
        values.append((match.span(), value))
    return values


def _month_days(text: str) -> list[tuple[str, tuple[int, int] | None]]:
    full_dates = _calendar_dates(text)
    values: list[tuple[str, tuple[int, int] | None]] = []
    for match in MONTH_DAY.finditer(text):
        if any(start <= match.start() and match.end() <= end for (start, end), _ in full_dates):
            continue
        try:
            value = date(2000, int(match[1]), int(match[2]))
        except ValueError:
            values.append((match.group(), None))
            continue
        values.append((match.group(), (value.month, value.day)))
    return values


def _time_number(text: str) -> int:
    if text.isdecimal():
        return int(text)
    digits = {char: number for number, char in enumerate("零一二三四五六七八九")}
    digits.update({"〇": 0, "两": 2})
    if "十" in text:
        tens, ones = text.split("十", 1)
        if (tens and tens not in digits) or (ones and ones not in digits):
            return -1
        return (digits.get(tens, 1) if tens else 1) * 10 + (digits.get(ones, 0) if ones else 0)
    return digits.get(text, -1)


def _clocks(text: str) -> list[tuple[str, tuple[int, int] | None]]:
    values: list[tuple[str, tuple[int, int] | None]] = []
    for match in CLOCK.finditer(text):
        hour = _time_number(match[2])
        minute_text = match[3] or match[4] or "0"
        minute = 30 if minute_text == "半" else _time_number(minute_text)
        period = match[1]
        if period in {"下午", "晚上"} and 1 <= hour < 12:
            hour += 12
        elif period in {"凌晨", "早上", "上午"} and hour == 12:
            hour = 0
        # Noon outside twelve and "晚上12点" are ambiguous across 12-hour/day boundaries.
        ambiguous = (period == "中午" and hour != 12) or (period == "晚上" and hour == 12)
        value = (
            (hour, minute)
            if not ambiguous and 0 <= hour <= 23 and 0 <= minute <= 59
            else None
        )
        values.append((match.group(), value))
    return values


def unsafe_text(answer: str) -> bool:
    """URLs and coordinates are rendered by the program, never written by the model."""
    return bool(UNSAFE_TEXT.search(answer) or BARE_DOMAIN.search(answer))


def unsupported_numbers(answer: str, evidence: str, user_context: str = "") -> list[str]:
    """Numbers of 3+ digits (phones, fees, dates) must appear verbatim in the evidence."""
    normal_answer = unicodedata.normalize("NFKC", answer)
    normal_user = unicodedata.normalize("NFKC", user_context)
    normal_evidence = unicodedata.normalize("NFKC", evidence)
    evidence_numbers = set(NUMBER.findall(normal_evidence))
    evidence_dates = {
        value for _, value in _calendar_dates(normal_evidence) if value is not None
    }
    evidence_month_days = {(value.month, value.day) for value in evidence_dates}
    evidence_month_days.update(
        value for _, value in _month_days(normal_evidence) if value is not None
    )
    evidence_clocks = {value for _, value in _clocks(normal_evidence) if value is not None}
    answer_dates = _calendar_dates(normal_answer)
    classroom = re.compile(r"E[12][-\s]?[ABC][-\s]?\d{3,4}(?!\d)", re.I)
    known = {re.sub(r"[-\s]", "", m.group()).upper() for m in classroom.finditer(normal_user)}
    spans = [
        m.span()
        for m in classroom.finditer(normal_answer)
        if re.sub(r"[-\s]", "", m.group()).upper() in known
    ]
    spans.extend(span for span, value in answer_dates if value in evidence_dates)
    unsupported_dates = [
        normal_answer[start:end]
        for (start, end), value in answer_dates
        if value not in evidence_dates
    ]
    unsupported_temporal = [
        raw for raw, value in _month_days(normal_answer) if value not in evidence_month_days
    ] + [raw for raw, value in _clocks(normal_answer) if value not in evidence_clocks]
    return unsupported_dates + unsupported_temporal + [
        m.group()
        for m in NUMBER.finditer(normal_answer)
        if m.group() not in evidence_numbers
        and not any(start <= m.start() and m.end() <= end for start, end in spans)
    ]


def missing_premise(answer: str, evidence: str) -> bool:
    """A source's critical prerequisite (card balance > 20) must survive summarisation."""
    return "大于20" in evidence and not BALANCE_PREMISE.search(answer)


def citation_failure(cited: Iterable[str], allowed: Iterable[str], status: str) -> str | None:
    cited_set, allowed_set = set(cited), set(allowed)
    if cited_set - allowed_set:
        return "invalid_response"
    if status == "success" and not cited_set:
        return "invalid_response"
    return None


def verify_answer(
    answer: str,
    cited: Iterable[str],
    allowed: Iterable[str],
    status: str,
    evidence: str,
    premise_evidence: str = "",
    *,
    user_context: str = "",
) -> str | None:
    """Full check used by the agent; returns the first failure code or None."""
    failure = citation_failure(cited, allowed, status)
    if failure:
        return failure
    if unsafe_text(answer) or unsupported_numbers(answer, evidence, user_context):
        return "invalid_response"
    # Small fees and floors are still factual claims, even when the old 3-digit guard
    # did not catch them. Classroom identifiers never establish an indoor floor.
    amounts = re.findall(r"\d+(?:\.\d+)?\s*元", answer)
    floors = re.findall(r"[一二三四五六七八九十百\d]+(?:楼|层)", answer)
    entrances = re.findall(r"(?:东|西|南|北|正|侧)(?:门|入口)", answer)
    normalized_evidence = re.sub(r"\s", "", evidence + " " + premise_evidence)
    if any(
        re.sub(r"\s", "", claim) not in normalized_evidence
        for claim in [*amounts, *floors, *entrances]
    ):
        return "invalid_response"
    if premise_evidence and missing_premise(answer, premise_evidence):
        return "required_premise_missing"
    return None


AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*元")


def _amounts(text: str) -> set[str]:
    out = set()
    for raw in AMOUNT.findall(text):
        value = raw.replace(",", "")
        out.add(value[:-3] if value.endswith(".00") else value)
    return out


def ocr_example_amount(answer: str, ocr_text: str, other_text: str) -> bool:
    """Amounts found only in OCR'd example screenshots (2020-2021) must not reach the answer."""
    from_ocr = _amounts(answer) & _amounts(ocr_text)
    return bool(from_ocr - _amounts(other_text))
