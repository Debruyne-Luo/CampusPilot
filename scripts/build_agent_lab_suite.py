"""Freeze 24 new tasks and independent source anchors; never exposes labels to editors."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/agent-lab-20261020"


def build() -> None:
    checked = [
        json.loads(line)
        for line in (ROOT / "evaluation/knowledge-quality-20261017/cases.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    facts: dict[str, list[dict]] = {}
    for case in checked:
        if case["label_status"] != "source_checked":
            continue
        for anchor in case["evidence"]:
            if anchor["check_status"] != "source_checked":
                continue
            path = ROOT / anchor["raw_file"]
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != anchor["raw_sha256"]:
                raise ValueError("Source anchor changed")
            if anchor["quote"] not in raw.decode("utf-8-sig"):
                raise ValueError("Source quote missing")
            facts.setdefault(case["issue_group"], []).append(
                {
                    k: anchor[k]
                    for k in ("source_id", "source_url", "quote", "raw_file", "raw_sha256")
                }
            )
    # Group membership is fixed before any model execution or optimizer observation.
    groups = [
        (
            "development",
            "service",
            "official:graduate-proof-2023",
            [
                "研究生需要在读证明时，已收录通知给出的两种办理渠道是什么？",
                "我是研究生，想先下载在读证明，应该从什么平台的哪项流程开始？",
            ],
        ),
        (
            "development",
            "policy",
            "official:portal-06",
            [
                "账号激活需要验证本人信息；安全手机能不能随便填同学的？",
                "按已有激活指南，开始验证之前应准备哪两项身份信息？",
            ],
        ),
        (
            "development",
            "combined",
            "official:winter2026",
            [
                "旧寒假通知里有一卡通设备地点，能据此确认现在窗口值班时间吗？",
                "我看到寒假每周四值班的旧通知，它能保证今天能现场补卡吗？",
            ],
        ),
        (
            "development",
            "insufficient",
            "official:portal-1266",
            [
                "借户口本的指南是否承诺审批一定当天完成？有依据的申请资格是什么？",
                "借户口本最长可以拿走多少天？找不到依据时请指出未知项。",
            ],
        ),
        (
            "holdout",
            "service",
            "official:tuition-2026",
            [
                "2026—2027学年四川农信贷款到账后，我还要做什么才算交上学费？",
                "2026—2027学年国开行贷款和其他银行贷款，要交给辅导员的回执有何区别？",
            ],
        ),
        (
            "holdout",
            "policy",
            "official:gradesindex",
            [
                "成绩复核超过申请期限，现有官方资料是否支持保证受理？",
                "成绩复核申请交上去以后，有没有明确保证几天内出结果？",
            ],
        ),
        (
            "holdout",
            "combined",
            "official:portal-1053",
            [
                "网络坏了准备报修，登录砚湖易办后该去哪个中心、哪个部门？",
                "网络故障报修的图上出现保修一词，我应按哪项业务提交？能保证多久修好？",
            ],
        ),
        (
            "holdout",
            "insufficient",
            "official:portal-1042",
            [
                "心理咨询预约指南能不能告诉我本周哪天还有空位？",
                "已有心理咨询预约资料，是否足够保证我今天可以预约成功？",
            ],
        ),
    ]
    tasks, reviews = [], []
    for split, category, group, questions in groups:
        anchors = facts.get(group)
        if not anchors:
            raise ValueError("Missing independently source-checked group: " + group)
        for question in questions:
            ident = f"{split[:3]}-{category}-{len(tasks) + 1:02}"
            tasks.append(
                {
                    "id": ident,
                    "split": split,
                    "category": category,
                    "group": group,
                    "question": question,
                }
            )
            reviews.append(
                {
                    "id": ident,
                    "anchors": anchors,
                    "basis": "previous_source_checked_raw_bytes_revalidated",
                    "fact_review": "pending",
                    "critical_errors": None,
                }
            )
    # Directory tasks test lookup/unknown boundaries against the maintained public
    # contract. They do not certify present occupancy or physical inspection.
    for split, teacher, place in [
        ("development", "蔡彪", "香樟餐厅"),
        ("holdout", "汤影", "东区图书馆"),
    ]:
        for category, name, filename in [
            ("teacher", teacher, "teachers.json"),
            ("place", place, "places.json"),
        ]:
            records = json.loads((ROOT / "data/cdut" / filename).read_bytes())
            record = next(r for r in records if r["name"] == name)
            questions = (
                [
                    f"想联系{name}老师，能否先查公开教师资料，而不猜办公室？",
                    f"没有公开办公室记录时，能直接给我{name}老师的具体房间和接待时间吗？",
                ]
                if category == "teacher"
                else [
                    f"帮我在地图目录找{name}，只需要建筑参考位置。",
                    f"带我去{name}，目的地先用目录建筑点，具体入口不确定就说明。",
                ]
            )
            for question in questions:
                ident = f"{split[:3]}-{category}-{len(tasks) + 1:02}"
                tasks.append(
                    {
                        "id": ident,
                        "split": split,
                        "category": category,
                        "group": category + ":" + name,
                        "question": question,
                    }
                )
                reviews.append(
                    {
                        "id": ident,
                        "basis": "directory_contract_only",
                        "record": record,
                        "source_file": "data/cdut/" + filename,
                        "record_sha256": hashlib.sha256(
                            json.dumps(record, ensure_ascii=False, sort_keys=True).encode()
                        ).hexdigest(),
                        "fact_review": "pending",
                        "critical_errors": None,
                        "limitation": "No new original-page or field verification claim.",
                    }
                )
    assert len(tasks) == 24
    assert all(
        sum(t["split"] == split for t in tasks) == 12 for split in ("development", "holdout")
    )
    a = {t["group"] for t in tasks if t["split"] == "development"}
    b = {t["group"] for t in tasks if t["split"] == "holdout"}
    assert not a & b
    OUT.mkdir(parents=True, exist_ok=True)
    for name, value in [("tasks.json", tasks), ("review-anchors.json", reviews)]:
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tasks_sha256": hashlib.sha256((OUT / "tasks.json").read_bytes()).hexdigest(),
                "development": 12,
                "holdout": 12,
                "groups_disjoint": True,
                "original_source_cases": 16,
                "directory_contract_cases": 8,
                "answer_reviews_completed": False,
                "knowledge_release_gate": "unaffected",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    build()
