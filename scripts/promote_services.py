"""Admission gate for the captured service catalogue.

Builds a real `CampusService` per catalogue entry using only published fields, so the
directory schema itself decides admission. Entries that cannot satisfy the contract are
reported with the validator's own reason and stay in the catalog layer. Public catalogue
and guide facts do not require a handling procedure. The historical navigation-step flag
is accepted for command compatibility but never fabricates a step or upgrades a guide.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from campuspilot.directory.repository import DirectoryRepository  # noqa: E402
from campuspilot.domain import CampusService  # noqa: E402
from campuspilot.evidence import SourceEvidence  # noqa: E402

PORTAL = ("https://bsdt.cdut.edu.cn/EIP/nonlogin/onewebsitehande/"
          "toPersonalCenterPage.htm?activePersonalHomeTab=false")
EVIDENCE = "cdut:evidence:bsdt-catalog-20261017"
ENTRY_MODES = {"线上": ("online",), "线下": ("in_person",), "线上线下结合": ("online", "in_person")}


def _slug(record: dict[str, Any]) -> str | None:
    """Project-assigned identifiers may be minted; they are not university facts."""
    code = str(record.get("code") or "").strip()
    if code:
        return f"cdut:service:bsdt-{code}"
    opaque = str(record.get("service_id") or "").strip()
    if re.fullmatch(r"[a-z0-9]{8,64}", opaque):
        return f"cdut:service:bsdt-{opaque[:12]}"
    return None


def _modes(record: dict[str, Any]) -> tuple[str, ...]:
    channel = str(record.get("handling_entry_text") or "").strip()
    if channel in ENTRY_MODES:
        return ENTRY_MODES[channel]
    published = str(record.get("handling_mode_text") or "")
    if "线上" in published:
        return ("online", "in_person") if "线下" in published else ("online",)
    if "线下" in published:
        return ("in_person",)
    return ()


def _evidence(record: dict[str, Any], *paths: str, note: str) -> tuple[dict[str, Any], ...]:
    evidence_id = str(_slug(record)).replace("cdut:service:", "cdut:evidence:")
    return tuple({"field_path": p, "evidence_ids": (evidence_id,), "note": note} for p in paths)


def build(record: dict[str, Any], *, allow_navigation_step: bool = False) -> dict[str, Any]:
    # Kept in the Python interface for old callers; intentionally has no effect.
    name = str(record.get("name") or "").strip()
    department = str(record.get("department") or "").strip()
    audience = str(record.get("service_object_text") or "").strip()
    code = str(record.get("code") or "").strip()
    advisory = str(record.get("advisory_text") or "").strip()
    phone = str(record.get("enquiry_phone") or "").strip()
    label = (f"砚湖易办事项指南「{name}」（编号 {code}）" if code
             else f"砚湖易办事项指南「{name}」")
    entry_points = (label, record.get("detail_url") or record.get("source_url") or PORTAL)
    modes = _modes(record)
    notes = [f"办事大厅服务指南采集于 {record.get('collected_on', '2026-10-17')}。"]
    if advisory:
        notes.append("官方注意事项：" + advisory.replace("\n", " "))
    has_detail = any(record.get(key) for key in (
        "handling_mode_text", "handling_entry_text", "advisory_text", "fees_text",
    ))
    notes.append("未收录登录后流程、材料和表单；公开入口不代表事项当前开放。")

    return {
        "service_id": _slug(record),
        "name": name,
        "aliases": (),
        "department": department,
        "office_id": None,
        "audience": audience,
        "information_level": "guide" if has_detail else "directory",
        "academic_year": None,
        "modes": modes,
        "entry_points": entry_points,
        "contacts": ({"label": "咨询电话", "value": phone},) if phone else None,
        "required_materials": None,
        "required_inputs": None,
        "steps": (),
        "availability": None,
        "fees": (str(record["fees_text"]),) if record.get("fees_text") else None,
        "limits": None,
        "field_evidence": _evidence(record,
            "name", "department", "audience", "modes", "entry_points.0", "entry_points.1",
            "notes.0", "aliases",
            *(["fees.0"] if record.get("fees_text") else []),
            *(["contacts.0"] if phone else []),
            note="砚湖易办事项指南公开页；仅采纳已保存的公开字段"),
        "notes": tuple(notes),
    }


def _validate_candidate_output(output: Path, base: Path) -> None:
    base_root, output_root = base.resolve(), output.resolve()
    if output_root == base_root or base_root.is_relative_to(output_root):
        raise ValueError("Candidate output must not replace the active directory")
    if output_root.is_relative_to(base_root) and "rag/candidates/" not in (
        output_root.as_posix() + "/"
    ):
        raise ValueError("Use output/ or data/cdut/rag/candidates/ for an isolated candidate")


def write_directory(
    output: Path, admitted: list[dict[str, Any]], records: list[dict[str, Any]], base: Path,
    input_bytes: bytes, reviewed_services: Path | None,
) -> dict[str, Any]:
    """Build an isolated, loadable candidate. Never write back into the active directory."""
    _validate_candidate_output(output, base)
    baseline = DirectoryRepository.load(base)
    base_services = json.loads((reviewed_services or base / "services.json").read_bytes())
    parsed_base = [CampusService.model_validate_json(json.dumps(x)) for x in base_services]
    if {x.service_id for x in parsed_base} != {x.service_id for x in baseline.services()}:
        raise ValueError("Reviewed baseline must preserve the existing service identifiers")
    scope_ids = {
        _slug(r) for r in records
        if {"undergraduate", "graduate"}.intersection(r.get("audiences") or ())
        and not any(word in str(r.get("name", "")) for word in ("宜宾校区", "宜宾校园"))
    }
    current = [row for row in admitted if row["service_id"] in scope_ids]
    records_by_id = {_slug(r): r for r in records}
    sources = json.loads((base / "sources.json").read_bytes())
    output.mkdir(parents=True, exist_ok=True)
    raw = output / "raw" / "bsdt"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "services_full.json").write_bytes(input_bytes)
    for row in current:
        original = records_by_id[row["service_id"]]
        encoded = json.dumps(original, ensure_ascii=False, sort_keys=True, indent=2).encode()
        capture_name = row["service_id"].split(":")[-1] + ".json"
        (raw / capture_name).write_bytes(encoded)
        sources.append(SourceEvidence.model_validate_json(json.dumps({
            "evidence_id": row["field_evidence"][0]["evidence_ids"][0],
            "source_id": row["service_id"].replace("cdut:service:", "cdut:source:"),
            "source_reference": "砚湖易办公开事项指南：" + row["name"],
            "source_url": original.get("detail_url") or original.get("source_url") or PORTAL,
            "publisher": "成都理工大学砚湖易办事大厅",
            "source_authority": "official_university", "version": "capture-20261017",
            "locator": "公开事项目录及事项详情字段；raw/bsdt/" + capture_name,
            "applicability": row["audience"], "retrieved_at": "2026-10-17",
            "access_method": "direct", "source_file_sha256": hashlib.sha256(encoded).hexdigest(),
            "limitations": [
                "复用已保存公开采集；未重新请求网页。",
                "校区未明确时不得推断特定校区；未收录登录后流程。",
            ],
        })).model_dump(mode="json"))
    candidate = [x.model_dump(mode="json") for x in parsed_base] + current
    for name, content in (("services.json", candidate), ("sources.json", sources)):
        (output / name).write_text(
            json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    for name in ("offices.json", "places.json", "teachers.json"):
        if (base / name).exists():
            (output / name).write_bytes((base / name).read_bytes())
    DirectoryRepository.load(output)
    scope_report = [{
        "service_id": row["service_id"], "name": row["name"],
        "audiences": records_by_id[row["service_id"]].get("audiences", []),
        "status": "adopted_candidate" if row["service_id"] in scope_ids else "out_of_scope",
        "reason": "本科生/研究生公开指南；完整流程未收录" if row["service_id"] in scope_ids
        else "仅教工、校友、访客适用或明确标注宜宾校区",
    } for row in admitted]
    (output / "scope-report.json").write_text(
        json.dumps(scope_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"schema_version": 2, "captured": len(records), "schema_admitted": len(admitted),
            "in_scope_new": len(current), "out_of_scope": len(admitted) - len(current),
            "baseline_services": len(parsed_base), "candidate_services": len(candidate),
            "baseline_explicitly_reviewed": reviewed_services is not None,
            "active_directory_unchanged": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-navigation-step", action="store_true")
    parser.add_argument("--base-directory", type=Path)
    parser.add_argument("--reviewed-services", type=Path,
                        help="Explicitly reviewed baseline records; never auto-upgrade legacy")
    args = parser.parse_args()
    if args.base_directory:
        _validate_candidate_output(args.output, args.base_directory)

    input_bytes = args.input.read_bytes()
    records = json.loads(input_bytes)
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise SystemExit("Expected a flat services array")

    admitted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for record in records:
        payload = build(record, allow_navigation_step=args.allow_navigation_step)
        try:
            admitted.append(CampusService.model_validate(payload).model_dump(mode="json"))
        except ValidationError as exc:
            reasons = "; ".join(str(e.get("msg")) for e in exc.errors()[:3])
            rejected.append({"name": record.get("name"), "code": record.get("code"),
                             "reason": reasons})

    args.output.mkdir(parents=True, exist_ok=True)
    if args.allow_navigation_step:
        print("--allow-navigation-step is obsolete; no steps will be generated", file=sys.stderr)
    (args.output / "services_admitted.json").write_text(
        json.dumps(admitted, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.output / "services_rejected.json").write_text(
        json.dumps(rejected, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.base_directory:
        report = write_directory(args.output, admitted, records, args.base_directory,
                                 input_bytes, args.reviewed_services)
        (args.output / "directory-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"total={len(records)} admitted={len(admitted)} rejected={len(rejected)}")
    tally: dict[str, int] = {}
    for row in rejected:
        key = row["reason"][:70]
        tally[key] = tally.get(key, 0) + 1
    for reason, count in sorted(tally.items(), key=lambda kv: -kv[1])[:6]:
        print(f"  {count:4d}  {reason}")


if __name__ == "__main__":
    main()
