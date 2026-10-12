"""Preserve the newer official lead without treating seasonal device lists as current locations."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "cdut"


def main() -> None:
    sources = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    ident = "cdut:evidence:card-winter-2026"
    if any(s["evidence_id"] == ident for s in sources):
        raise SystemExit("Lead already imported; no files changed")
    sources.append(
        {
            "evidence_id": ident,
            "source_id": "cdut:source:card-winter-2026",
            "source_reference": "成都理工大学2026年寒假网络信息服务指南",
            "source_url": "https://wxc.cdut.edu.cn/info/1006/3954.htm",
            "publisher": "成都理工大学网络与信息化处",
            "source_authority": "official_department",
            "version": "2026年寒假通知",
            "locator": "一卡通自助设备地点",
            "applicability": "仅证明该通知列出自助服务区；不确认2026年10月补卡机或卡种。",
            "source_published_at": "2026-01-29",
            "retrieved_at": "2026-10-07",
            "access_method": "search_index",
            "verification_status": "needs_review",
            "synthetic": False,
            "limitations": [
                "寒假安排已过期，不用其值班时间描述当前开放时间。",
                "通知未说明每台设备是否支持当前补卡及对应卡种。",
            ],
        }
    )
    services = json.loads((ROOT / "services.json").read_text(encoding="utf-8"))
    replacement = next(
        s for s in services if s["service_id"] == "cdut:service:campus-card-replacement"
    )
    replacement["notes"].append(
        "核验线索：2026年寒假通知列出香樟、珙桐、银杏自助服务区；当前补卡能力与卡种未知。"
    )
    replacement["field_evidence"].append(
        {
            "field_path": "notes.2",
            "evidence_ids": [ident],
            "note": "季节性设备线索，不作为当前补卡点关联依据。",
        }
    )
    for name, value in (("sources.json", sources), ("services.json", services)):
        (ROOT / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
