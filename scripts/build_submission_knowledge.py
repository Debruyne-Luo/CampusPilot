"""Build one public submission corpus without changing the archived RAG corpus."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "integrations/dify"


def main() -> None:
    inputs = [
        ROOT / "integrations/dify/knowledge" / name
        for name in (
            "campus-card-loss.md",
            "graduate-enrollment-proof.md",
            "tuition-receipt-2026-2027.md",
        )
    ]
    inputs.extend(
        ROOT / "data/cdut" / name for name in ("services.json", "teachers.json", "sources.json")
    )
    services = json.loads(inputs[-3].read_text(encoding="utf-8"))
    teachers = json.loads(inputs[-2].read_text(encoding="utf-8"))
    sources = {s["evidence_id"]: s for s in json.loads(inputs[-1].read_text(encoding="utf-8"))}
    replacement = next(
        s for s in services if s["service_id"] == "cdut:service:campus-card-replacement"
    )
    parts = [
        "# CampusPilot 提交版公开资料快照\n\n"
        "整理日期：2026-10-07。全部 needs_review，不是实时学校系统。"
        "本轮业务 API 结果决定记录与卡片；语料仅补充同一事项的来源说明。"
        "未知办公室、校区、设备位置与坐标不得补造，暂不能定位或导航。\n"
    ]
    parts.extend(p.read_text(encoding="utf-8") for p in inputs[:3])
    parts.append("# 校园卡补办（独立于挂失）\n\n状态：needs_review。\n")
    parts.extend(
        f"- {step['instruction']} 条件：{step['condition']}\n" for step in replacement["steps"]
    )
    parts.extend(f"- {note}\n" for note in (*replacement["limits"], *replacement["notes"]))
    for ident in ("cdut:evidence:card-replacement-guide-2024", "cdut:evidence:card-winter-2026"):
        source = sources[ident]
        parts.append(
            f"来源：{source['source_reference']}；{source['source_url']}；{source['locator']}。"
            f"适用限制：{source['applicability']}\n"
        )
    for teacher in teachers:
        parts.append(
            f"# {teacher['name']}老师办公室查询\n\n"
            f"姓名：{teacher['name']}；学院：{teacher['department']}；"
            f"办公室：{teacher['office'] or '未收录'}；校区：{teacher['campus'] or '待确认'}。"
            "状态：needs_review。建筑位置/地图坐标未收录，暂不能定位或导航。\n"
            f"官方教师资料来源：{teacher['profile_url']}\n" + "\n".join(teacher["notes"]) + "\n"
        )
    corpus = "\n\n".join(parts)
    filename = "CampusPilot-submission-knowledge.txt"
    (TARGET / filename).write_text(corpus, encoding="utf-8")
    manifest = {
        "export_date": "2026-10-07",
        "verification_status": "needs_review",
        "purpose": "Public submission corpus for economical keyword RAG; no factual verification",
        "document": filename,
        "document_sha256": hashlib.sha256((TARGET / filename).read_bytes()).hexdigest(),
        "source_sha256": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in inputs
        },
    }
    (TARGET / "submission-knowledge-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Public corpus prepared: {len(corpus)} characters; all facts remain needs_review.")


if __name__ == "__main__":
    main()
