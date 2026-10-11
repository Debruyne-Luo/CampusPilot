"""Deterministic 1-4 step tool plan from the understood intent.

Plans are shown to the user, so they are produced by code, not by the model. Arguments
that depend on earlier results (e.g. the service_id for make_checklist) are marked with
`from_step` and resolved by the executor.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import Field, JsonValue

from campuspilot.agent.understand import Understanding
from campuspilot.contracts import Contract

MAX_STEPS = 4


class PlanStep(Contract):
    step: Annotated[int, Field(ge=1, le=MAX_STEPS)]
    tool: Annotated[str, Field(min_length=1, max_length=64)]
    label: Annotated[str, Field(min_length=1, max_length=60)]
    arguments: dict[str, JsonValue] = {}
    from_step: int | None = None


class Plan(Contract):
    steps: tuple[PlanStep, ...] = Field(default=(), max_length=MAX_STEPS)
    map_action: Annotated[str, Field(pattern=r"^(show_place|plan_route)$")] | None = None


def _query(text: str | None, question: str) -> str:
    value = (text or question).strip()[:120]
    return value or question[:120]


# A place question that asks about an attribute of the place (hours, rules, fees, contact,
# booking...) also needs the official documents, not only the map record.
PLACE_ATTRIBUTE = re.compile(
    r"几点|时间|开门|关门|开放|闭馆|开馆|营业|作息|规定|政策|制度|要求|收费|多少钱|价格|费用"
    r"|电话|联系|预约|预定|能不能|可不可以|可以|允许|需要|要带|怎么办|流程|规则"
)


def asks_place_attribute(question: str) -> bool:
    return bool(PLACE_ATTRIBUTE.search(question))


def make_plan(view: Understanding, question: str) -> Plan:
    slots = view.slots
    audience = slots.identity if slots.identity != "unknown" else "all"
    knowledge_args: dict[str, JsonValue] = {"query": question[:500], "audience": audience}
    if slots.academic_year:
        knowledge_args["academic_year"] = slots.academic_year
    raw: list[tuple[str, str, dict[str, JsonValue], int | None]] = []
    map_action: str | None = None
    if view.intent == "办事":
        raw = [
            ("search_service", "查找办事事项", {"query": _query(slots.service, question)}, None),
            ("make_checklist", "生成办理清单", {"audience": audience}, 1),
            ("search_knowledge", "检索官方资料", knowledge_args, None),
        ]
        map_action = "show_place"
    elif view.intent == "找人":
        who = _query(slots.destination, question)
        raw = [
            ("search_teacher", "查找老师", {"query": who}, None),
            ("find_teacher", "查教师名录", {"query": who[:40]}, None),
        ]
        map_action = "show_place"
    elif view.intent in {"找地点", "路线"}:
        raw = [("search_place", "查找地点", {"query": _query(slots.destination, question)}, None)]
        if asks_place_attribute(question):
            raw.append(("search_knowledge", "检索官方资料", knowledge_args, None))
        map_action = "plan_route" if view.intent == "路线" else "show_place"
    elif view.intent == "政策问答":
        raw = [("search_knowledge", "检索官方资料", knowledge_args, None)]
    steps = tuple(
        PlanStep(step=i, tool=tool, label=label, arguments=args, from_step=dep)
        for i, (tool, label, args, dep) in enumerate(raw[:MAX_STEPS], start=1)
    )
    return Plan(steps=steps, map_action=map_action)
