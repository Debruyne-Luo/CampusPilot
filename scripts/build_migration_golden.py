"""Create the fixed 120 public cases from approved facts, without running the router."""

import argparse
import json
from pathlib import Path

from campuspilot.rag import canonical, digest

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = {
    "aaooffices:01": "教务处教学事务中心负责哪些事务？",
    "aaooffices:02": "教务处学籍管理科负责什么？",
    "aaooffices:03": "教务处综合科有哪些职责？",
    "aaooffices:04": "质量建设与智慧教学科负责什么？",
    "aaooffices:05": "教材建设科负责哪些教材事务？",
    "aaooffices:06": "实践教学科负责哪些实践教学事务？",
    "card2024:01": "校园卡小程序怎样绑定？",
    "card2024:02": "校园卡挂失之后怎样解挂？",
    "card2024:03": "校园卡补办费用与地点的资料有哪些限制？",
    "gradeform2018:01": "历史上的2018年成绩复核申请表说明什么？",
    "gradesindex:01": "期末课程成绩复核指南在哪里查看？",
    "identity2021:01": "统一身份认证账号怎样激活？",
    "identity2021:02": "统一身份认证怎样通过绑定方式找回密码？",
    "identity2021:03": "统一身份认证安全手机换了怎么办？",
    "libfaq:01": "图书馆馆藏怎样查找、续借和预约？",
    "libfaq:02": "在图书馆馆外怎样使用数据库？",
    "libfaq:03": "图书馆借阅数量怎么规定？",
    "libfresh:01": "新生第一次借书有哪些步骤？",
    "libhours:01": "图书馆常规开馆时间是什么？",
    "libservices:01": "图书馆有哪些服务项目和咨询渠道？",
    "libwinter2026:01": "历史上的2026寒假图书馆开放安排是什么？",
    "mail2022:01": "学生邮箱激活入口在哪里？",
    "mail2022:02": "学生邮箱激活有哪些步骤？",
    "mail2022:03": "历史学生邮箱客户端配置资料说明什么？",
    "netfaq2023:01": "校园网怎样进行实名认证？",
    "netfaq2023:02": "历史2023年校园网联网设备数量有什么限制？",
    "netfaq2023:03": "校园网络故障怎样求助？",
    "portal2020:01": "历史2020年砚湖易办PC操作演示在哪里？",
    "portalmanual:01": "砚湖易办官方手册入口在哪里？",
    "proofindex:01": "本科生电子证明官方指南在哪里？",
    "repair:01": "宿舍楼宇零星维修有哪些报修渠道？",
    "repair:02": "宿舍维修报修需要哪些信息？",
    "repair:03": "零星维修受理时间和咨询方式是什么？",
    "retiredvpn2018:01": "历史Hillstone旧VPN是否已经停止服务？",
    "sslvpn2020:01": "历史2020年旧版客户端SSLVPN说明什么？",
    "voucher2026:01": "电子凭证平台使用手册入口在哪里？",
    "winter2026:01": "历史2026年寒假WebVPN入口是什么？",
    "winter2026:02": "历史2026年寒假SSLVPN安排说明什么？",
    "winter2026:03": "历史2026年寒假砚湖易办入口在哪里？",
    "xscoffices:01": "学生处学生管理科负责哪些工作？",
    "xscoffices:02": "学生资助管理中心办公室负责什么？",
    "xscoffices:03": "学生处思想政治教育科负责什么？",
    "xscoffices:04": "学生网络文化建设中心和易班发展中心负责什么？",
    "xscoffices:05": "学生处综合科负责什么？",
}


def build() -> list[dict[str, object]]:
    directory = ROOT / "data/cdut"
    snapshot = json.loads((directory / "rag/bootstrap.json").read_bytes())
    sources = {s["source_id"]: s for s in snapshot["sources"]}
    rows: list[dict[str, object]] = []

    def add(question: str, group: str, facts: list[str], **kwargs: object) -> None:
        rows.append(
            {
                "question": question,
                "messages": [],
                "group": group,
                "public_fixture": True,
                "expected_facts": facts,
                "required_premises": [],
                "chunk_ids": [],
                "source_ids": [],
                "service_ids": [],
                "teacher_ids": [],
                "place_ids": [],
                "answer_strategy": "generate",
                "expected_search_needed": False,
                **kwargs,
            }
        )

    # Twenty existing map/directory cases, using record IDs as the authoritative target.
    places = json.loads((directory / "places.json").read_bytes())
    for place in places[:20]:
        add(
            place["name"] + "在哪里？",
            "legacy_campus",
            [place["name"], "坐标仅取自目录，不能由模型推算"],
            place_ids=[place["place_id"]],
            answer_strategy="direct",
        )
    teachers = json.loads((directory / "teachers.json").read_bytes())
    for teacher in teachers:
        for subject in ("办公室在哪里", "公开教师主页在哪里"):
            add(
                teacher["name"] + "老师" + subject + "？",
                "legacy_teacher",
                [teacher["office"] or "办公室暂未收录", "房号不代表教师此刻在场"],
                teacher_ids=[teacher["teacher_id"]],
                answer_strategy="direct",
            )
    service_cases = [
        ("校园卡怎么挂失？", "campus-card-loss", [], "generate", []),
        ("校园卡遗失了怎么挂失？", "campus-card-loss", [], "generate", []),
        ("挂失校园卡有什么官方入口？", "campus-card-loss", [], "direct", []),
        (
            "校园卡挂失需要先有20元余额吗？",
            "campus-card-loss",
            ["大于20元是自助补卡前提，不是挂失前提"],
            "generate",
            [],
        ),
        (
            "我在学校外面能挂失校园卡吗？",
            "campus-card-loss",
            ["只依据已收录入口，未知能力不补造"],
            "generate",
            [],
        ),
        (
            "校园卡在哪补办，怎么做？",
            "campus-card-replacement",
            ["卡内余额大于20元", "不是补卡费", "身份证"],
            "direct",
            [],
        ),
        (
            "校园卡补办需要哪些材料？",
            "campus-card-replacement",
            ["卡内余额大于20元", "身份证"],
            "direct",
            [],
        ),
        (
            "校园卡补办多少钱？",
            "campus-card-replacement",
            ["2020年25元资料不能冒充现行费用", "20元是余额前提，不是工本费"],
            "generate",
            [],
        ),
        (
            "校园卡补卡后余额多久回来？",
            "campus-card-replacement",
            ["依照原文限定，未知时间不补造"],
            "generate",
            [],
        ),
        (
            "补卡机器现在在哪里？",
            "campus-card-replacement",
            ["机器精确坐标未核验，不等于食堂地点未知"],
            "generate",
            [],
        ),
        ("在读证明怎么办？", "", ["澄清本科或研究生身份"], "clarify", []),
        (
            "研究生在读证明怎么办？",
            "graduate-enrollment-proof",
            ["2023年试运行资料", "当前规则待复核"],
            "generate",
            [],
        ),
        (
            "那要准备什么？",
            "graduate-enrollment-proof",
            ["材料未知不等于无需材料"],
            "generate",
            ["研究生在读证明怎么办？"],
        ),
        (
            "本科生在读证明怎么办？",
            "",
            ["不能套用研究生流程", "仅有本科电子证明官方指南入口"],
            "generate",
            [],
        ),
        (
            "我是本科",
            "",
            ["本轮身份覆盖研究生身份，不返回研究生流程"],
            "generate",
            ["研究生在读证明怎么办？"],
        ),
        ("学费电子票据怎么查？", "", ["必须澄清适用学年"], "clarify", []),
        (
            "2026-2027学年学费电子票据怎么查？",
            "tuition-electronic-receipt",
            ["2026-2027学年限定"],
            "generate",
            [],
        ),
        ("2025-2026学年学费票据怎么查？", "", ["不能套用2026-2027学年通知"], "clarify", []),
        (
            "那2026-2027学年呢？",
            "tuition-electronic-receipt",
            ["保留本轮学年条件"],
            "generate",
            ["学费电子票据怎么查？"],
        ),
        (
            "2026-2027学年电子票据缴费后多久能查？",
            "tuition-electronic-receipt",
            ["只采用通知等待条件，不承诺实时到账"],
            "generate",
            [],
        ),
    ]
    services = {s["service_id"]: s for s in json.loads((directory / "services.json").read_bytes())}
    for question, name, premises, strategy, messages in service_cases:
        ident = "cdut:service:" + (
            "tuition-receipt-2026-2027" if name == "tuition-electronic-receipt" else name
        )
        service = services.get(ident)
        facts = (
            [service["summary"]]
            if service and service.get("summary")
            else [step["instruction"] for step in service["steps"]]
            if service
            else premises
        )
        add(
            question,
            "legacy_service",
            facts,
            service_ids=[ident] if ident in services else [],
            required_premises=premises,
            answer_strategy=strategy,
            messages=messages,
        )
    knowledge = json.loads((directory / "knowledge.json").read_bytes())
    for record in knowledge:
        add(
            record["title"] + "有哪些已收录资料？",
            "legacy_notice",
            [record["summary"]],
            source_ids=[record["source_url"]],
            answer_strategy="direct",
        )
    for question, fact in (
        ("现在帮我缴学费", "只读范围，不执行缴费"),
        ("综合科在哪里？", "同名部门歧义，先澄清教务处或学生处"),
        ("胡艳梅和蔡彪老师的办公室在哪？", "请指定一位教师，不混用办公室"),
        ("2026寒假图书馆安排能当今天开放时间吗？", "历史已过期，不能当现行时间"),
    ):
        add(
            question,
            "legacy_boundary",
            [fact],
            answer_strategy="clarify",
            expected_search_needed=True,
        )
    assert len(rows) == 60
    for chunk in snapshot["chunks"]:
        ident = chunk["chunk_id"]
        office = ident.startswith("cdut:candidate-office:")
        question = (
            chunk["title"] + "在哪里、有什么职责及核对限制？"
            if office
            else QUESTIONS[ident.removeprefix("cdut:chunk:")]
        )
        source = sources[chunk["source_id"]]
        add(
            question,
            "new_office" if office else "new_knowledge",
            [chunk["text"]],
            chunk_ids=[ident],
            source_ids=[chunk["source_id"]],
            required_premises=[
                "保留资料适用对象和时效：" + source["applicability"],
                "内容类型：" + chunk["kind"],
            ],
            answer_strategy="generate",
            expected_search_needed=chunk["kind"] in {"index_only", "limitation"},
        )
    for question, fact in (
        ("现在还能用Hillstone旧VPN吗？", "已废弃资料不能当现行规则，证据不足时说明缺口"),
        ("本科生电子证明能照研究生自助机操作吗？", "本科资料只有入口，不能扩大研究生流程"),
        ("教务处综合科和学生处综合科是否同一办公室？", "来源和部门范围分开，不按相同URL覆盖"),
        ("楼寓服务中心的资料能自动变成导航点吗？", "办公室摘要不是已核验坐标，不新增地图卡片"),
    ):
        add(
            question, "new_boundary", [fact], answer_strategy="clarify", expected_search_needed=True
        )
    assert len(rows) == 120
    for i, row in enumerate(rows):
        row["case_id"] = f"cp-{i + 1:03d}"
        row["split"] = "holdout" if i % 3 == 2 else "development"
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = build()
    args.output.mkdir(parents=True, exist_ok=False)
    data = b"\n".join(canonical(row) for row in rows) + b"\n"
    (args.output / "cases.jsonl").write_bytes(data)
    manifest = {
        "schema_version": 1,
        "cases_sha256": digest(data),
        "total": 120,
        "development": 80,
        "holdout": 40,
        "label_authority": "approved_public_evidence",
        "independent_label_audit": "PENDING",
        "baseline_status": "NOT_LOCKED",
    }
    (args.output / "manifest.json").write_bytes(canonical(manifest))
    print("Fixed 120 public cases written; 80 development / 40 holdout. No inference performed.")


if __name__ == "__main__":
    main()
