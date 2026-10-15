"""Evidence-only summaries and response presentation; no model or provider calls."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import JsonValue

from campuspilot.agent.evidence import Evidence, StepRecord
from campuspilot.agent.plan import Plan
from campuspilot.agent.understand import Understanding
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.observability import record_event
from campuspilot.presentation import place_card, service_card
from campuspilot.retrieval.grounding import GroundingMode
from campuspilot.service_links import answer_service_links

NO_BASIS_ANSWER = "现有资料还不足以确认这个问题。"
STALE_NOTE_MARK = "可能已过期"
STALE_NOTE = "\n\n（注：所引用的部分资料可能已过期，请以学校最新通知为准。）"


class ResponseBuilder:
    def __init__(
        self,
        repository: DirectoryRepository,
        grounding: GroundingMode,
        trace: Callable[[str, dict[str, JsonValue]], None],
    ) -> None:
        self.repository = repository
        self.grounding = grounding
        self._trace = trace

    def _cards(self, ev: Evidence) -> dict[str, JsonValue]:
        return {
            "services": [service_card(self.repository, s) for s in ev.services.values()],
            "teachers": [t.model_dump(mode="json") for t in ev.teachers.values()],
            "places": [self.place_card(p) for p in ev.places.values()],
        }

    @staticmethod
    def place_card(place: Any) -> dict[str, JsonValue]:
        return dict(place) if isinstance(place, dict) else place_card(place)

    def _map_actions(self, plan: Plan, ev: Evidence) -> list[JsonValue]:
        actions: list[JsonValue] = []
        for place in ev.places.values():
            card = self.place_card(place)
            if card.get("position") is None:
                continue
            actions.append({"type": "show_place", "place_id": card["place_id"]})
        if (
            plan.map_action == "plan_route"
            and len(actions) == 1
            and (ev.place_resolution == "exact" or ev.locked_place_ids)
        ):
            first = actions[0]
            assert isinstance(first, dict)
            # Origin is the browser's own location, resolved in the frontend only.
            actions.insert(
                0, {"type": "plan_route", "place_id": first["place_id"], "origin": "browser"}
            )
        return actions[:6]

    def _shown_hits(self, ev: Evidence) -> list[dict[str, JsonValue]]:
        """Hits eligible for summary/excerpts: grounding-filtered only in block mode."""
        return ev.grounded_hits() if self.grounding == "block" else ev.hits

    def summary(self, ev: Evidence) -> str:
        # Never dump arbitrary retrieved text after a model or verification failure.
        lines: list[str] = []
        for service in list(ev.services.values())[:1]:
            lines.insert(
                0, f"{service.name}：" + "；".join(s.instruction for s in service.steps[:2])
            )
        if ev.places and not lines:
            names = "、".join(
                str(self.place_card(p).get("name")) for p in list(ev.places.values())[:4]
            )
            return f"已找到地点：{names}。可以选择地点并点击“带我去”。"
        if ev.teachers and not lines:
            lines = [f"已找到：{'、'.join(t.name for t in list(ev.teachers.values())[:4])}"]
        accepted: set[str] = set()
        for check in ev.grounding_checks:
            identifiers = check.get("grounded_chunk_ids")
            if isinstance(identifiers, list):
                accepted.update(str(cid) for cid in identifiers)
        grounded = [
            h for h in ev.hits if h.get("grounded") is True or str(h.get("chunk_id")) in accepted
        ]
        if not lines and grounded:
            titles = "、".join(str(h.get("title"))[:80] for h in grounded[:2])
            return f"找到相关来源：{titles}。本次未能整理出可靠答复，可查看下方来源。"
        if not lines:
            return NO_BASIS_ANSWER
        return "已确认的部分信息：\n" + "\n".join(lines)

    def build(
        self,
        *,
        answer: str,
        status: str,
        view: Understanding | None,
        plan: Plan | None,
        steps: list[StepRecord],
        ev: Evidence,
        cited: tuple[str, ...] = (),
        degraded: str = "",
        mode: str = "agent",
        show_sources: bool = True,
    ) -> dict[str, JsonValue]:
        excerpts: list[JsonValue] = [
            {
                "document": h.get("title"),
                "content": h.get("text"),
                "source_id": h.get("source_id"),
                "chunk_id": h.get("chunk_id"),
                "source_url": h.get("url"),
            }
            for h in self._shown_hits(ev)[:4]
        ]
        citations = [ev.citations[c] for c in cited if c in ev.citations]
        if self.grounding != "block":
            # off / flag: pre-grounding behaviour (fallback to every citation), except that
            # an "empty" answer (e.g. the model found no basis) shows no unrelated sources.
            if status == "empty":
                excerpts, citations = [], []
            elif not citations:
                citations = list(ev.citations.values())[:6]
            excerpts, citations = self._drop_ungrounded(ev, excerpts, citations, cited)
        elif status == "empty" or answer == NO_BASIS_ANSWER:
            # An honest refusal shows no excerpts or citations of chunks it did not use.
            excerpts, citations = [], []
        elif not citations and status == "limited":
            # Summary fallback: only sources of hits that passed the grounding policy,
            # plus non-knowledge evidence (services, teachers).
            shown = {str(h.get("source_id")) for h in ev.grounded_hits()}
            citations = [
                c for k, c in ev.citations.items() if k not in ev.knowledge_sources or k in shown
            ][:6]
        if not show_sources:
            excerpts, citations = [], []
        if (
            answer
            and status in {"success", "limited"}
            and any(ev.citations[c].get("stale") for c in cited if c in ev.citations)
            and STALE_NOTE_MARK not in answer
        ):
            answer += STALE_NOTE
        body: dict[str, JsonValue] = {
            **self._cards(ev),
            "answer": answer,
            "result_status": status,
            "answer_mode": mode,
            "excerpts": excerpts,
            "source_ids": list(cited),
            "service_links": answer_service_links(ev.hits, cited, status) if show_sources else [],
            "plan": [s.model_dump(mode="json") for s in steps],
            "checklist": ev.checklist,
            "citations": list(citations),
            "map_actions": self._map_actions(plan, ev) if plan else [],
            "understanding": (
                {"intent": view.intent, "slots": view.slots.model_dump(mode="json")}
                if view
                else None
            ),
        }
        if degraded:
            body["degraded_reason"] = degraded
        if ev.web_status:
            body["web_search"] = {"status": ev.web_status}
        if self.grounding == "block" and ev.no_grounding():
            body["grounding"] = "insufficient"
        if self.grounding != "off" and ev.grounding_checks:
            decisions = [str(c.get("decision")) for c in ev.grounding_checks]
            other = ev.has_structured()
            self._trace(
                "grounding_check",
                {
                    "mode": self.grounding,
                    "policy": ev.grounding_checks[0].get("policy"),
                    "decisions": list(decisions),
                    "decision": (
                        "insufficient" if all(d == "insufficient" for d in decisions)
                        else "grounded" if "grounded" in decisions else "unassessed"
                    ),
                    "count": len(decisions),
                    "grounded_chunk_ids": sorted(  # type: ignore[dict-item]
                        {
                            str(i)
                            for c in ev.grounding_checks
                            for i in c.get("grounded_chunk_ids") or []  # type: ignore[union-attr]
                        }
                    ),
                    # Whether block mode would have answered with the no-basis refusal.
                    "would_refuse": all(d == "insufficient" for d in decisions) and not other,
                },
            )
        reason = (
            degraded if degraded else "evidence_insufficient" if status == "empty"
            else "non_public_input" if mode == "agent_local" and status == "needs_clarification"
            else "missing_conditions" if status == "needs_clarification" else "supported"
        )
        record_event("answer_decision", status=status, degraded_reason=degraded, reason=reason)
        return body

    def _drop_ungrounded(
        self,
        ev: Evidence,
        excerpts: list[JsonValue],
        citations: list[dict[str, JsonValue]],
        cited: tuple[str, ...],
    ) -> tuple[list[JsonValue], list[dict[str, JsonValue]]]:
        """flag/shadow: when place/teacher/service evidence carries the answer, knowledge
        hits the grounding check rejected are not shown as excerpts or fallback citations.

        Only what the model cited or what passed the grounding check stays. Answer text and
        model citations are unchanged; off mode (no grounding check) is unaffected.
        """
        if self.grounding == "off" or not ev.grounding_checks:
            return excerpts, citations
        if not (ev.services or ev.places or ev.teachers):
            return excerpts, citations
        grounded = {
            str(i)
            for c in ev.grounding_checks
            for i in c.get("grounded_chunk_ids") or []  # type: ignore[union-attr]
        }
        keep_sources = set(cited) | {
            str(h.get("source_id")) for h in ev.hits if str(h.get("chunk_id")) in grounded
        }
        excerpts = [
            e
            for e in excerpts
            if isinstance(e, dict)
            and (str(e.get("chunk_id")) in grounded or str(e.get("source_id")) in set(cited))
        ]
        citations = [
            c
            for c in citations
            if str(c.get("id")) not in ev.knowledge_sources or str(c.get("id")) in keep_sources
        ]
        return excerpts, citations

