"""Record the 2026-10-09 official campus-plan recheck without inventing coordinates.

The plan legend groups 财务处 with 校园一卡通中心 in one numbered building, and it does not
list 网安楼 at all. Both are provenance statements about the official document, not a
position: no coordinate, reviewer or `confirmed` status is created here.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "cdut"
PLAN_SHA256 = "2d354d434f72657a77c8f2ec8d96f36735654e8623518ef6d636006c00a31481"
PLAN_NOTE = (
    "官方平面图图例把“财务处、校园一卡通中心”标为同一编号建筑；这是同楼线索，"
    "不是房间号或已确认点位，不能据此生成坐标或导航。"
)
SECURITY_NOTE = "官方平面图图例不含“网安楼”，不能用该图定位本楼；本次复核仍未找到官方方位说明。"


def main() -> None:
    sources = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    plan = next(s for s in sources if s["evidence_id"] == "cdut:evidence:campus-plan")
    if plan.get("source_file_sha256"):
        raise SystemExit("Plan provenance already recorded; no files changed")
    plan["access_method"] = "direct"
    plan["source_file_sha256"] = PLAN_SHA256
    plan["retrieved_at"] = "2026-10-09"
    plan["limitations"] = [
        *plan["limitations"],
        "2026-10-09 自官方 URL 直接下载核对：PDF 响应 200，字节哈希与记录一致；"
        "同一域名的 HTML 页面直连仍返回 412，因此引用页面正文时不能声称直接查看。",
        "平面图没有发布日期；图例可按编号确认楼名，但不提供坐标，也不含“网安楼”。",
    ]

    places = json.loads((ROOT / "places.json").read_text(encoding="utf-8"))
    updated = {}
    for place_id, note in (
        ("cdut:place:card-centre", PLAN_NOTE),
        ("cdut:place:network-security", SECURITY_NOTE),
    ):
        record = next(p for p in places if p["place_id"] == place_id)
        if note in record["notes"]:
            raise SystemExit("Lead already present; no files changed")
        record["notes"].append(note)
        record["field_evidence"].append(
            {
                "field_path": f"notes.{len(record['notes']) - 1}",
                "evidence_ids": ["cdut:evidence:campus-plan"],
                "note": "官方平面图图例的同楼标注或不含该楼，均为来源陈述，不是坐标依据。",
            }
        )
        updated[place_id] = len(record["notes"]) - 1

    for name, value in (("sources.json", sources), ("places.json", places)):
        (ROOT / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        "plan provenance upgraded;",
        "notes added:",
        ", ".join(f"{k}=notes.{v}" for k, v in updated.items()),
    )
    print("plan sha256:", hashlib.sha256((ROOT / "sources.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
