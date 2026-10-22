"""Enrich the captured service catalogue with facts parsed from the official `desc` text.

Every extracted value must appear verbatim in the publisher's own text: fees, basis
document titles with issue numbers, handling location and plain advisory notes. Missing
values stay empty and are never inferred. The output is a candidate layer artifact; it does
not decide admission into the directory store and it does not classify a service by type,
mode or place.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

DOC_NO = re.compile(r"[（(]\s*[^（）()〔〕\[\]]{0,12}?[〔\[(]\s*\d{4}\s*[〕\])]\s*\d+\s*号\s*[）)]")
TITLE = re.compile(r"《[^《》]{2,60}》")
FEE = re.compile(r"(?:不收费|免费|收费标准|收费|费用[：:]?|执行价格)[^，。；\n]*", re.UNICODE)
LOC = re.compile(r"(?:办理地点|线下地点|办理窗口)[：:]?[^，。；\n]*", re.UNICODE)
TAG = re.compile(r"<[^>]+>")
MEANINGLESS = re.compile(r"^(?:不收费|免费|点击查看|详见|无)$", re.UNICODE)
LABEL_ONLY = re.compile(r"^[^：:]{0,8}[：:]\s*$", re.UNICODE)
LABELS = ("注意事项", "办理流程", "办理条件", "办理材料", "申请材料",
          "温馨提示", "提醒", "说明", "备注", "办理说明", "相关说明")


def _prose(raw: object) -> str:
    """Turn publisher markup into visible text, keeping sentences intact."""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    text = html.unescape(raw)
    text = text.replace("</p>", "\n").replace("</h4>", "\n").replace("<br/>", "\n")
    text = text.replace("</li>", "\n").replace("</div>", "\n")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = TAG.sub("", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _basis(text: str) -> list[str]:
    """Basis documents deduplicated by title, each with its issue number when published."""
    found: dict[str, str] = {}
    for match in TITLE.finditer(text):
        title = match.group()
        number = DOC_NO.search(text[match.end():match.end() + 60])
        found.setdefault(title, f"{title}{number.group()}" if number else title)
    return list(found.values())


def _notes(text: str, fee: str, location: str) -> list[str]:
    """Advisory sentences from the publisher; bare labels and basis echoes are dropped."""
    titles = TITLE.findall(text)
    found = []
    for line in text.splitlines():
        line = line.strip()
        if not line or MEANINGLESS.match(line) or LABEL_ONLY.match(line):
            continue
        if line in {fee, location}:
            continue
        if titles and any(title in line for title in titles) and len(line) <= 120:
            continue
        if line.startswith(("事项名称", "事情名称", "办理部门", "服务对象")):
            continue
        for label in LABELS:
            if line.startswith(label):
                line = line[len(label):].strip("：: 　")
                break
        if len(line) >= 6:
            found.append(line)
    return found[:12]


def enrich(record: dict) -> dict:
    text = _prose(record.get("description_html"))
    fee = FEE.search(text).group().strip() if FEE.search(text) else ""
    location = LOC.search(text).group().strip() if LOC.search(text) else ""
    basis = _basis(text)
    notes = _notes(text, fee, location)
    return {
        **record,
        "guidance_text": text or None,
        "fees_text": fee or None,
        "basis_documents": basis or None,
        "handling_location_text": location or None,
        "advisory_notes": notes or None,
        "fact_coverage": {
            "fees": bool(fee),
            "basis": bool(basis),
            "location": bool(location),
            "notes": bool(notes),
            "procedure_steps": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records = json.loads(args.input.read_bytes())
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise ValueError("Expected a flat service index array")
    enriched = [enrich(r) for r in records if r.get("name")]
    if len({r["service_id"] for r in enriched}) != len(enriched):
        raise ValueError("Duplicate service ID")

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "service_enriched.json").write_text(
        json.dumps(enriched, ensure_ascii=False, indent=1), encoding="utf-8")
    with_desc = sum(1 for r in enriched if r["guidance_text"])
    facts = {k: sum(1 for r in enriched if r["fact_coverage"][k])
             for k in ("fees", "basis", "location", "notes", "procedure_steps")}
    print(f"Enriched {len(enriched)} entries with guidance: {with_desc}")
    print(f"fact coverage: {facts}")
    print(f"catalog-only without guidance text: {len(enriched) - with_desc}")


if __name__ == "__main__":
    main()
