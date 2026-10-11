"""Build the tuning (dev) set. Never reads gold labels of the colloquial test set; it only
reads its question strings to drop exact duplicates so dev and test stay disjoint."""

import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path("/workspace/cp-knowledge/eval-colloquial-20261011.jsonl")
)
MINE = [
    (
        "教务处管选课排课的办公室在哪",
        ["cdut:candidate-office:05", "cdut:chunk:aaooffices:01"],
        "academic_office",
    ),
    (
        "学籍科电话多少 想问学历注册",
        ["cdut:candidate-office:06", "cdut:chunk:aaooffices:02"],
        "academic_office",
    ),
    (
        "教材是在哪个科室领的",
        ["cdut:candidate-office:03", "cdut:chunk:aaooffices:05"],
        "academic_office",
    ),
    (
        "毕设和竞赛归哪个科管",
        ["cdut:candidate-office:04", "cdut:chunk:aaooffices:06"],
        "academic_office",
    ),
    (
        "贫困认定找学生处哪个办公室",
        ["cdut:candidate-office:09", "cdut:chunk:xscoffices:02"],
        "financial_aid",
    ),
    ("饭卡丢了咋冻结", ["cdut:chunk:card2024:02"], "campus_card"),
    ("一卡通小程序怎么绑", ["cdut:chunk:card2024:01"], "campus_card"),
    ("补卡要多少钱在哪补", ["cdut:chunk:card2024:03"], "campus_card"),
    ("统一认证账号第一次咋激活", ["cdut:chunk:identity2021:01"], "campus_network"),
    ("密码忘了登不上砚湖易办", ["cdut:chunk:identity2021:02"], "campus_network"),
    ("换手机号了验证码收不到咋整", ["cdut:chunk:identity2021:03"], "campus_network"),
    ("学校邮箱网址是啥", ["cdut:chunk:mail2022:01"], "campus_network"),
    ("邮箱能用outlook收信不", ["cdut:chunk:mail2022:03"], "campus_network"),
    ("宿舍连不上网 获取不到ip", ["cdut:chunk:netfaq2023:03"], "campus_network"),
    ("校园网一个号能同时登几台设备", ["cdut:chunk:netfaq2023:02"], "campus_network"),
    ("在家咋上知网 要挂vpn吗", ["cdut:chunk:libfaq:02", "cdut:chunk:winter2026:01"], "library"),
    ("图书馆几点关门", ["cdut:chunk:libhours:01"], "library"),
    ("本科生能借几本书 借多久", ["cdut:chunk:libfaq:03"], "library"),
    ("书快到期了能续借吗", ["cdut:chunk:libfaq:01"], "library"),
    ("图书馆有打印机吗 咋打印", ["cdut:chunk:libprint:bs01"], "campus_print"),
    ("想换寝室找谁办", ["cdut:chunk:lyfwdorm:bs01"], "dorm"),
    ("搬出去住要交啥材料", ["cdut:chunk:lyfwdorm:bs03"], "dorm"),
    ("暑假想留校住怎么申请", ["cdut:chunk:lyfwdorm:bs05"], "dorm"),
    ("寝室灯坏了去哪报修", ["cdut:chunk:lyfwdorm:bs06", "cdut:chunk:repair:01"], "dorm"),
    ("宿舍没电了咋充电费", ["cdut:chunk:lyfwdorm:bs08", "cdut:chunk:cistfresh2025:bs13"], "dorm"),
    ("考试那天发烧了能缓考吗", ["cdut:chunk:xjgl2019:08"], "academic_exam"),
    ("挂科了补考还是重修", ["cdut:chunk:xjgl2019:08"], "academic_exam"),
    ("优良中及格咋换算成分数", ["cdut:chunk:xjgl2019:07"], "academic_exam"),
    (
        "体测不及格能毕业吗",
        ["cdut:chunk:xjgl2019:09", "cdut:chunk:xjgl2019:14"],
        "academic_graduation",
    ),
    (
        "拿不到学位证的情况有哪些",
        ["cdut:chunk:xjgl2019:14", "cdut:chunk:xjgl2019:15"],
        "academic_graduation",
    ),
    ("毕业证丢了能补吗", ["cdut:chunk:xjgl2019:16"], "academic_graduation"),
    ("想休学一年去创业行不行", ["cdut:chunk:xjgl2019:12"], "academic_suspension"),
    ("休学回来咋复学", ["cdut:chunk:xjgl2019:13"], "academic_suspension"),
    ("大一能转专业吗 几次机会", ["cdut:chunk:xjgl2019:10"], "academic_transfer"),
    ("四级过了英语课能免吗", ["cdut:chunk:xjgl2019:04"], "academic_course"),
    ("这学期选课啥时候开始", ["cdut:chunk:select20262027:bs01"], "academic_course"),
    ("勤工助学一个月给多少钱", ["cdut:chunk:cistwork2025:bs03"], "financial_aid"),
    ("国励志奖学金大一能申请吗", ["cdut:chunk:mee2025grant:bs02"], "financial_aid"),
    ("助学贷款毕业了要确认啥", ["cdut:chunk:loanconfirm2026:bs01"], "financial_aid"),
    ("学费交不起能缓交吗", ["cdut:chunk:wx:fee20262027:03"], "financial_aid"),
    ("学费发票去哪下载", ["cdut:chunk:wx:feeinvoice:01"], "financial_aid"),
    ("校医院住院能报多少", ["cdut:chunk:medins2026:bs02"], "health_insurance"),
    ("医保咋交 多少钱一年", ["cdut:chunk:medins2026:bs01"], "health_insurance"),
    ("心理咨询怎么预约", ["cdut:chunk:psych2026:bs01"], "health_mental"),
    ("校医院能做彩超吗", ["cdut:chunk:hospoverview:bs02"], "health_insurance"),
    (
        "军训服要自己买吗多少钱",
        ["cdut:chunk:cistfresh2024:bs13", "cdut:chunk:cistfresh2025:bs12"],
        "freshman",
    ),
    (
        "新生户口要不要迁过来",
        ["cdut:chunk:cistfresh2025:bs04", "cdut:chunk:cistfresh2024:bs04"],
        "freshman",
    ),
    ("秋季双选会啥时候", ["cdut:chunk:wx:jobfair2027autumn:01"], "career"),
    ("北森平台能模拟面试吗", ["cdut:chunk:wx:beisen:04", "cdut:chunk:wx:beisen:05"], "career"),
    ("校团委有哪些学生组织可以加", ["cdut:chunk:wx:tworgs2026:01"], "clubs"),
]
REFUSE = [
    "食堂几点开饭",
    "校车时刻表有吗",
    "游泳馆怎么预约",
    "教师资格证在哪报名",
    "驾校报名有优惠吗",
    "考研自习室怎么申请",
]


def norm(q):
    return "".join(q.split())


test = {
    norm(json.loads(l)["question"])
    for l in TEST.read_text(encoding="utf-8").splitlines()
    if l.strip()
}
snap = json.loads(
    (ROOT / "data/cdut/rag/approved-20261011b/snapshot.json").read_text(encoding="utf-8")
)
ids = {c["chunk_id"] for c in snap["chunks"]}
rows = [
    {
        "case_id": f"devK{i + 1:03d}",
        "question": q,
        "chunk_ids": g,
        "topic": t,
        "source": "kb-derived",
    }
    for i, (q, g, t) in enumerate(MINE)
]
rows += [
    {
        "case_id": f"devR{i + 1:03d}",
        "question": q,
        "chunk_ids": [],
        "topic": "no_answer",
        "source": "handwritten-refusal",
    }
    for i, q in enumerate(REFUSE)
]
for l in (
    (ROOT / "evaluation/colloquial-20261011/cases.jsonl").read_text(encoding="utf-8").splitlines()
):
    c = json.loads(l)
    rows.append(
        {
            "case_id": "devC-" + c["case_id"],
            "question": c["question"],
            "chunk_ids": c["chunk_ids"],
            "topic": "colloquial-20261011",
            "source": "evaluation/colloquial-20261011",
        }
    )
dropped = [r["question"] for r in rows if norm(r["question"]) in test]
rows = [r for r in rows if norm(r["question"]) not in test]
assert all(i in ids for r in rows for i in r["chunk_ids"])
(Path(__file__).parent / "cases.jsonl").write_text(
    "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
)
print(len(rows), "dev cases; dropped (exact dup of test):", dropped)
