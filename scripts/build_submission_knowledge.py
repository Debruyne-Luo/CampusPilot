"""Build one public submission corpus without changing the archived RAG corpus."""

import hashlib
import json
from datetime import date
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
    place_file = ROOT / "data/cdut/places.json"
    places = {p["place_id"]: p for p in json.loads(place_file.read_text(encoding="utf-8"))}
    inputs.append(place_file)
    exported = date.today().isoformat()
    parts = [
        "# CampusPilot 提交版公开资料快照\n\n"
        f"整理日期：{exported}。不是实时学校系统，来源采用不等于现场核验。"
        "本轮业务 API 结果决定记录与卡片；语料仅补充同一事项的来源说明。"
        "办理地点与机器精确坐标是不同字段；没有机器坐标不能把有依据的食堂说成未知。\n"
    ]
    parts.extend(p.read_text(encoding="utf-8") for p in inputs[1:3])
    for service in services:
        if service["service_id"] not in {
            "cdut:service:campus-card-loss",
            "cdut:service:campus-card-replacement",
        }:
            continue
        parts.append(f"# {service['name']}：地点、前提与简短流程\n{service.get('summary', '')}\n")
        detail = [f"# {service['name']}：操作与限制"]
        detail.extend(f"{service['name']}入口：{entry}" for entry in service["entry_points"])
        detail.extend(
            f"- {step['instruction']} 条件：{step['condition']}\n" for step in service["steps"]
        )
        for field in ("required_materials", "fees", "limits", "notes"):
            detail.extend(
                f"{service['name']} {field}：{note}" for note in (service.get(field) or [])
            )
        parts.append("\n".join(detail))
        evidence_ids = dict.fromkeys(
            ident for field in service["field_evidence"] for ident in field["evidence_ids"]
        )
        for ident in evidence_ids:
            source = sources[ident]
            parts.append(
                f"# {service['name']}：来源与适用限制\n"
                f"来源（{source['source_authority']}）：{source['source_reference']}；"
                f"{source['source_url'] or '用户当次补充，无公开URL'}；{source['locator']}。"
                f"适用限制：{source['applicability']}\n"
            )
    for teacher in teachers:
        place = places.get(teacher["place_id"])
        map_status = (
            "建筑参考点已收录；不代表室内办公室或老师当前在场。"
            if place and place["position"]
            else "建筑地图坐标未收录。"
        )
        parts.append(
            f"# {teacher['name']}老师办公室查询\n"
            f"姓名：{teacher['name']}；学院：{teacher['department']}；"
            f"办公室：{teacher['office'] or '未收录'}；校区：{teacher['campus'] or '待确认'}。"
            f"状态：needs_review。{map_status}\n"
            f"官方教师资料来源：{teacher['profile_url']}\n" + "\n".join(teacher["notes"]) + "\n"
        )
    for place in places.values():
        location_status = (
            "有高德建筑/店铺参考点" if place["position"] else "独立点位尚未确认，不借用其他楼栋坐标"
        )
        parts.append(
            f"# 校园地点：{place['name']}\n"
            f"可检索名称：{'、'.join([place['name'], *place['aliases']])}。\n"
            f"位置说明：{place['address_detail'] or '见地图建筑参考点'}。"
            f"地图：{location_status}。\n"
            f"{' '.join(place['notes'])}\n"
        )
    corpus = "\n\n".join(parts)
    filename = "CampusPilot-submission-knowledge.txt"
    (TARGET / filename).write_text(corpus, encoding="utf-8")
    manifest = {
        "export_date": exported,
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
    print(f"Public corpus prepared: {len(corpus)} characters; evidence limitations preserved.")


if __name__ == "__main__":
    main()
