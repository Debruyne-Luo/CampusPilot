"""Application-owned route recipes. A decision never supplies executable arguments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from campuspilot.agent.plan import Plan, make_plan
from campuspilot.agent.understand import Understanding

Route = Literal["service", "teacher", "place", "knowledge", "place_knowledge", "clarify", "chat"]
ROUTES: dict[str, str] = {
    "service": "Find an official service, preparation checklist and supporting documents.",
    "teacher": "Find a named teacher or public faculty directory entry.",
    "place": "Find a named place or a reference route; no policy facts are requested.",
    "knowledge": "Retrieve official policy, procedures, contacts or other public documents.",
    "place_knowledge": "Find a place AND official evidence for its hours, rules or services.",
    "clarify": "A missing USER condition prevents choosing the applicable task.",
    "chat": "Greeting or conversation with no campus factual question.",
}


@dataclass(frozen=True)
class RouteDecision:
    status: str
    route: str = ""
    confidence: float = 0.0
    latency_ms: float = 0.0
    reason: str = ""


def route_plan(view: Understanding, question: str, route: str) -> tuple[Understanding, Plan]:
    if route not in ROUTES:
        raise ValueError("Unknown route recipe")
    intent = {
        "service": "办事",
        "teacher": "找人",
        "place": "找地点",
        "knowledge": "政策问答",
        "place_knowledge": "找地点",
    }.get(route)
    if intent is None:
        # A judge cannot invent missing slots or turn a factual task into small talk.
        return view, make_plan(view, question)
    if route == "place" and view.intent == "路线":
        intent = "路线"
    routed = view.model_copy(update={"intent": intent})
    plan = make_plan(routed, question)
    if route == "place_knowledge" and not any(s.tool == "search_knowledge" for s in plan.steps):
        knowledge = make_plan(view.model_copy(update={"intent": "政策问答"}), question)
        step = knowledge.steps[0].model_copy(update={"step": len(plan.steps) + 1})
        plan = plan.model_copy(update={"steps": (*plan.steps, step)})
    return routed, plan
