"""Reproducible source-backed candidate inventory. Never guesses coordinates or offices.

Initial generation only: refuses to overwrite reviewed/edited files. Sources were read
through their official search indexes except the user-supplied card guide PDF.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "cdut"
DAY = "2026-10-07"


def evidence(
    key: str, url: str, title: str, locator: str, authority: str = "official_college"
) -> dict:
    return {
        "evidence_id": f"cdut:evidence:{key}",
        "source_id": f"cdut:source:{key}",
        "source_reference": title,
        "source_url": url,
        "publisher": "成都理工大学",
        "source_authority": authority,
        "version": "公开页面；当前有效性待复核",
        "locator": locator,
        "applicability": "仅支持页面明示字段，不推断校区、入口、坐标或接待时间。",
        "retrieved_at": DAY,
        "access_method": "search_index",
        "limitations": ["官方页面部分直连失败；使用官方搜索索引，需人工复核现行信息。"],
    }


def links(fields: list[str], source: str) -> list[dict]:
    return [
        {
            "field_path": key,
            "evidence_ids": [source],
            "note": "名称依据明示来源；别名和分类为项目检索整理，不代表新增校园事实。",
        }
        for key in fields
    ]


def generate() -> None:
    if (DATA / "places.json").exists() or (DATA / "teachers.json").exists():
        raise SystemExit("Inventory already exists; edit/review it directly, do not overwrite.")
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    map_source = evidence(
        "campus-plan",
        "https://www.cdut.edu.cn/files/mapcl.pdf",
        "成理平面图",
        "地图图例编号；无可靠版次日期",
        "official_university",
    )
    map_source["limitations"].append("平面图用于名称候选，不作为坐标或当前院系办公地点证明。")
    sources.append(map_source)
    building_source = evidence(
        "cist-building-2025",
        "https://cist.cdut.edu.cn/info/1145/6716.htm",
        "学院2025年招生简章",
        "主校区与网安楼203教务科",
    )
    sources.append(building_source)
    places = []
    entries = [
        ("network-security", "网安楼", "office", ["网络安全楼"]),
        ("east-library", "东区图书馆", "library", ["东图"]),
        ("east-teaching", "东区教学楼", "teaching", []),
        ("administration", "行政楼", "office", []),
        ("card-centre", "校园一卡通中心", "service", []),
        ("finance", "财务处", "office", []),
        ("hospital", "校医院", "service", []),
        ("security", "保卫处", "office", []),
        ("furong-dining", "芙蓉食堂", "dining", []),
        ("ginkgo-dining", "银杏餐厅", "dining", []),
        ("gongtong-dining", "珙桐餐厅", "dining", ["珙桐食堂"]),
        ("camphor-dining", "香樟餐厅", "dining", ["香樟食堂"]),
        ("sports-college", "体育学院", "office", []),
        ("earth-sciences", "地球科学学院", "office", []),
        ("energy", "能源学院", "office", []),
        ("environment-civil", "环境与土木工程学院", "office", []),
        ("foreign-languages", "外国语学院", "office", []),
        ("materials", "材料与化学化工学院", "office", []),
        ("yifu", "逸夫楼", "teaching", []),
        ("tourism", "旅游与城乡规划学院", "office", []),
    ]
    for key, name, category, aliases in entries:
        source = (
            building_source["evidence_id"]
            if key == "network-security"
            else map_source["evidence_id"]
        )
        places.append(
            {
                "place_id": f"cdut:place:{key}",
                "name": name,
                "aliases": aliases,
                "campus": "成都校区",
                "category": category,
                "address_detail": None,
                "position": None,
                "field_evidence": links(["name", "aliases", "campus", "category"], source),
                "notes": [
                    "公开资料候选，当前名称、具体建筑和位置尚待复核。",
                    "未录入坐标，不提供精确地图点位或导航；院系条目不是教师办公室。",
                ],
            }
        )
    teachers = []
    for key, name, page, office in [
        ("wang-honghui", "王洪辉", "7607", "网安楼204室"),
        ("cai-biao", "蔡彪", "7466", None),
        ("tang-ying", "汤影", "7487", None),
        ("yao-guangle", "姚光乐", "7636", None),
        ("hu-yanmei", "胡艳梅", "7472", None),
    ]:
        url = f"https://cist.cdut.edu.cn/info/1231/{page}.htm"
        source = evidence(
            f"teacher-{key}", url, f"{name}个人简介", "教师姓名、院系；办公室仅在页面明确时记录"
        )
        sources.append(source)
        fields = ["name", "aliases", "department", "profile_url"] + (["office"] if office else [])
        teachers.append(
            {
                "teacher_id": f"cdut:teacher:{key}",
                "name": name,
                "aliases": [name + "老师"],
                "department": "计算机与网络安全学院",
                "campus": None,
                "office": office,
                "place_id": None,
                "profile_url": url,
                "field_evidence": links(fields, source["evidence_id"]),
                "notes": [
                    "公开教师资料；不表示老师当前在办公室或可随时接待。",
                    "成都/宜宾校区归属和办公室现行性待确认，尚未建立导航关联。",
                ],
            }
        )
    replacement_source = evidence(
        "card-replacement-guide-2024",
        "https://wxc.cdut.edu.cn/__local/8/1C/3C/0F34CEA8E563BE8802193833FE4_CFB792C4_36A72F.pdf",
        "网络与信息化服务指南（学生版），第四版",
        "正文第27页／PDF第30页：自助补卡设备操作流程",
        "official_department",
    )
    replacement_source.update(
        {
            "publisher": "成都理工大学网络与信息化处",
            "access_method": "user_provided_file",
            "source_file_sha256": (
                "825729937cfd2791c768c2682d1bc1ac41b57a4a6ded57033b0de63f419239b9"
            ),
            "version": "第四版；封面2024年8月",
            "applicability": "自助设备补卡步骤；不支持当前机器位置、收费或小程序补卡推断。",
            "limitations": [
                "原PDF已核对；2024年规则现行性仍待人工复核。",
                "余额要求不等于补卡费；正文未确定补卡服务区。",
            ],
        }
    )
    sources.append(replacement_source)
    services = json.loads((DATA / "services.json").read_text(encoding="utf-8"))
    services.append(
        {
            "service_id": "cdut:service:campus-card-replacement",
            "name": "校园卡补办",
            "aliases": ["一卡通补办", "校园卡补卡"],
            "department": "网络与信息化处",
            "office_id": "cdut:office:network-information",
            "audience": "持校园卡学生；按学生版指南整理",
            "modes": ["self_service"],
            "entry_points": ["校园卡自助补卡设备（当前服务区待确认）"],
            "steps": [
                {
                    "mode": "self_service",
                    "instruction": (
                        "在自助设备选择自助补卡，选择所在服务区补卡机，"
                        "再点击开始补卡并按设备提示操作。"
                    ),
                    "condition": "依据2024年8月指南；当前设备、适用卡种及步骤待复核",
                    "place_ids": None,
                }
            ],
            "required_materials": None,
            "required_inputs": None,
            "fees": None,
            "limits": ["2024年指南要求校园卡余额大于20元；这不是已确认的补卡工本费。"],
            "notes": [
                "仅提供补卡指引；未执行挂失、充值或补办。",
                "当前机器位置、入口、卡种、收费和开放时间未知。",
            ],
            "field_evidence": links(
                [
                    "name",
                    "aliases",
                    "department",
                    "audience",
                    "modes",
                    "entry_points",
                    "steps.0",
                    "limits",
                ],
                replacement_source["evidence_id"],
            ),
        }
    )
    for filename, value in [
        ("sources.json", sources),
        ("services.json", services),
        ("places.json", places),
        ("teachers.json", teachers),
    ]:
        (DATA / filename).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        "Created 20 place candidates, 5 teachers and a distinct card replacement service; "
        "no guessed coordinates."
    )


if __name__ == "__main__":
    generate()
