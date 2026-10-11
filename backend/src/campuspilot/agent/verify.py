"""Answer verification shared by the rule runtime and the agent loop.

Every check returns a failure code (or None). Codes: invalid_response (unknown or missing
citations, URLs, coordinates, numbers absent from evidence) and required_premise_missing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

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


def unsafe_text(answer: str) -> bool:
    """URLs and coordinates are rendered by the program, never written by the model."""
    return bool(UNSAFE_TEXT.search(answer) or BARE_DOMAIN.search(answer))


def unsupported_numbers(answer: str, evidence: str) -> list[str]:
    """Numbers of 3+ digits (phones, fees, dates) must appear verbatim in the evidence."""
    return [n for n in NUMBER.findall(answer) if n not in evidence]


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
) -> str | None:
    """Full check used by the agent; returns the first failure code or None."""
    failure = citation_failure(cited, allowed, status)
    if failure:
        return failure
    if unsafe_text(answer) or unsupported_numbers(answer, evidence):
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
