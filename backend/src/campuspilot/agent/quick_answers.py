"""Conservative directory shortcuts; attribute and compound questions retain the agent."""

from __future__ import annotations

import re

from campuspilot.agent.plan import asks_place_attribute
from campuspilot.agent.understand import Slots, Understanding, rule_identity, rule_year
from campuspilot.directory.repository import DirectoryRepository, normalise_place_query
from campuspilot.domain import CampusService

DETAILS = re.compile(r"材料|带什么|准备什么|需要什么|信息|流程|步骤|清单|详细|怎么操作|操作方法")
FOLLOWUP = re.compile(
    r"(?:那|那么|这个|它)?(?:线上|网上|线下)?"
    r"(?:入口在哪|在哪里办|在哪办|怎么去|怎么操作|要带什么材料|需要什么材料|"
    r"要带什么|需要准备什么|步骤是什么|详细流程|生成清单|查看清单)[？?。！!]*"
)
COMPLEX = re.compile(
    r"最新|联网|今天|明天|现在|是否|能否|能不能|可不可以|影响|区别|如果|"
    r"多少钱|费用|收费|工本费|几点|什么时候|电话|邮箱|规定|政策|预约|"
    r"以及|同时|顺便|还有|[和与及、，,；;]"
)


def entry_subject(question: str) -> str | None:
    """Recognize a request for an address, without inferring eligibility or a process."""
    if (len(question) > 80 or COMPLEX.search(question.replace('邮箱', ''))
            or DETAILS.search(question)):
        return None
    match = re.fullmatch(
        r"(?:请问|帮我找)?(.{3,50}?)(?:的)?(?:官方|线上|网上)?(?:办理)?"
        r"(?:入口|网址|链接)(?:在哪|在哪里|是什么|是哪个|怎么找)?[？?。！!\s]*", question.strip(),
    )
    return match[1].strip() if match else None


def entry_title_matches(subject: str, title: str) -> bool:
    title = re.sub(r"(?:办理指南|办事指南|申请指南|服务指南|指南|入口)$", "", title.strip())
    return normalise_place_query(subject) == normalise_place_query(title)


def service_channel(question: str) -> str:
    online = any(w in question for w in ('线上', '网上', '入口', '网址', '链接', '微信', '小程序'))
    if online and '线下' in question:
        return 'all'
    if online:
        return 'online'
    return 'offline' if any(w in question for w in ('线下', '哪里', '在哪')) else 'all'


def quick_view(question: str, repository: DirectoryRepository) -> Understanding | None:
    if len(question) > 100 or COMPLEX.search(question) or DETAILS.search(question):
        return None
    identity = rule_identity(question)
    matches = [
        (len(name), service)
        for service in repository.services() for name in (service.name, *service.aliases)
        if len(name) >= 3 and name in question
    ]
    if matches:
        matches.sort(key=lambda pair: pair[0], reverse=True)
        service = matches[0][1]
        if service.information_level != "procedure":
            return None
        if "研究生" in service.audience and "本科" not in service.audience:
            if identity != "graduate":
                return None
        # A bounded directory match cannot answer unrelated factual additions.
        names = [name for name in (service.name, *service.aliases) if name in question]
        rest = question.replace(max(names, key=len), "", 1)
        rest = re.sub(
            r"请问|帮我|我是|本科生|研究生|教职工|想|我要|我|的|怎么|办|在|哪|里|去|"
            r"入口|网址|链接|线上|网上|线下|微信|小程序|地址|位置|找|[？?。！!\s]", "", rest,
        )
        if rest:
            return None
        return Understanding(intent="办事", slots=Slots(
            identity=identity, academic_year=rule_year(question), service=service.name,
        ))
    if asks_place_attribute(question):
        return None
    places = repository.match_places_in_question(question)
    if len(places) == 1 and any(
        w in question for w in ("在哪", "哪里", "位置", "怎么去", "带我去")
    ):
        text = normalise_place_query(question)
        names = [normalise_place_query(n) for n in (places[0].name, *places[0].aliases)]
        names = [name for name in names if name in text]
        if not names:
            return None
        rest = text.replace(max(names, key=len), "", 1)
        rest = re.sub(
            r"请问|帮我|带我去|怎么去|位置|在哪里|在哪|哪里|我想|我要|的|到|去|找|[？?。！!]",
            "", rest,
        )
        if rest:
            return None
        return Understanding(
            intent="路线" if any(w in question for w in ("怎么去", "带我去")) else "找地点",
            slots=Slots(identity=identity, destination=places[0].name),
        )
    return None


def service_answer(service: CampusService, question: str) -> str | None:
    channel = service_channel(question)
    modes = {s.mode for s in service.steps}
    if channel == 'online' and "online" not in modes:
        return None  # Do not turn a source page into an unsupported online service.
    entries = list(service.entry_points or ())
    if channel == 'online':
        entries = [e for e in entries if not any(w in e for w in ("线下", "食堂", "人工"))]
    elif channel == 'offline':
        entries = [e for e in entries if any(w in e for w in ("线下", "食堂", "中心", "自助"))]
    if not entries:
        return None
    # A URL is rendered as a separately validated button, never copied into answer prose.
    entries = [e for e in entries if "http" not in e]
    if not entries:
        return None
    lines = ["**办理入口：**" + "；".join(entries[:2]) + "。"]
    # Preparation stays in the procedure disclosure; constraints still affect choice.
    prerequisites = list(service.limits or ())
    if prerequisites:
        lines.append("**注意：**" + "；".join(p.rstrip('。；') for p in prerequisites) + "。")
    conditions = [s.condition for s in service.steps if s.condition]
    if any(any(w in c for w in ("历史", "待复核", "2023年", "2024年")) for c in conditions):
        lines.append("**资料时效：**依据所引年份指南，当前入口及受理安排以学校最新说明为准。")
    return "\n\n".join(lines)
