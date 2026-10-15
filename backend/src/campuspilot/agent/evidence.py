"""Turn evidence and validation helpers, independent of orchestration and providers."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import JsonValue

from campuspilot.agent.verify import BARE_DOMAIN
from campuspilot.contracts import Contract
from campuspilot.llm.chat_model import ImageInput

if TYPE_CHECKING:
    from campuspilot.jev_plugin import JevTurn

ID_KEYS = ("source_id", "evidence_id", "chunk_id", "service_id", "place_id", "teacher_id")
_URL = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'*+,;=%()]+")


def generation_evidence(value: Any) -> Any:
    """Keep facts/IDs for generation; source and entry links remain owned by the UI."""
    if isinstance(value, dict):
        return {
            key: item if key in ID_KEYS or key == "id" or key.endswith("_ids")
            else generation_evidence(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [generation_evidence(item) for item in value]
    if isinstance(value, str):
        return BARE_DOMAIN.sub("（入口见下方来源）", _URL.sub("（入口见下方来源）", value))
    return value


class StepRecord(Contract):
    step: int
    tool: str
    label: str
    status: str


Emit = Callable[[str, dict[str, JsonValue]], Awaitable[None]]


@dataclass
class Evidence:
    results: list[dict[str, JsonValue]] = field(default_factory=list)
    allowed: set[str] = field(default_factory=set)
    services: dict[str, Any] = field(default_factory=dict)
    places: dict[str, Any] = field(default_factory=dict)
    teachers: dict[str, Any] = field(default_factory=dict)
    hits: list[dict[str, JsonValue]] = field(default_factory=list)
    checklist: dict[str, JsonValue] | None = None
    citations: dict[str, dict[str, JsonValue]] = field(default_factory=dict)
    # search_knowledge grounding decisions ("grounded" / "insufficient" / "unassessed").
    grounding: list[str] = field(default_factory=list)
    knowledge_sources: set[str] = field(default_factory=set)
    # Per-search grounding records (policy, decision, grounded chunk ids) for the trace.
    grounding_checks: list[dict[str, JsonValue]] = field(default_factory=list)
    # Set while the model's own tool loop (_answer) runs: its knowledge searches get the
    # same Jev check as planned ones.
    question: str = ""
    answering: bool = False
    emit: Emit | None = None
    destination_query: str = ""
    locked_place_ids: set[str] = field(default_factory=set)
    place_status: str = ""
    place_resolution: str = ""
    routing_complete: bool = False
    images: tuple[ImageInput, ...] = ()
    user_observation: str = ""
    visible_text: str = ""
    web_status: str = ""
    jev_turn: JevTurn | None = None

    async def notify(self, event: str, data: dict[str, JsonValue]) -> None:
        if self.emit is not None:
            await self.emit(event, data)

    def text(self) -> str:
        return json.dumps(self.results, ensure_ascii=False)

    def grounded_hits(self) -> list[dict[str, JsonValue]]:
        """Knowledge hits the grounding policy accepted (legacy rows carry no flag: kept)."""
        return [h for h in self.hits if h.get("grounded", True) is not False]

    def no_grounding(self) -> bool:
        """Only knowledge was found, and every knowledge search was judged insufficient."""
        return (
            bool(self.grounding)
            and all(d == "insufficient" for d in self.grounding)
            and not self.has_structured()
        )

    def has_structured(self) -> bool:
        """Known directory or checklist facts can support a partial answer."""
        return bool(self.services or self.places or self.teachers or self.checklist)

    def has_local_evidence(self) -> bool:
        """Local material can support a partial answer without proving the whole task."""
        return self.has_structured() or any(
            bool(hit.get("text"))
            and (hit.get("chunk_id") in self.allowed or hit.get("source_id") in self.allowed)
            for hit in self.hits if not hit.get("web")
        )

    def source_references(self, cited: tuple[str, ...]) -> tuple[str, ...]:
        """Resolve checked entry-button IDs to their already retrieved source IDs."""
        aliases: dict[str, str] = {}
        for hit in self.grounded_hits():
            links = hit.get("service_links")
            if not isinstance(links, list):
                continue
            for link in links:
                if not isinstance(link, dict):
                    continue
                ident, source = link.get("id"), link.get("source_id")
                if isinstance(ident, str) and isinstance(source, str) and source in self.allowed:
                    aliases[ident] = source
        return tuple(dict.fromkeys(aliases.get(ident, ident) for ident in cited))


def _without_ocr(value: Any, ocr_texts: tuple[str, ...] = ()) -> Any:
    """Tool results minus OCR'd rows (and summaries quoting them): text-only evidence."""
    if isinstance(value, dict):
        return {k: _without_ocr(v, ocr_texts) for k, v in value.items()}
    if isinstance(value, list):
        return [
            _without_ocr(v, ocr_texts) for v in value if not (isinstance(v, dict) and v.get("ocr"))
        ]
    if isinstance(value, str):
        for text in ocr_texts:
            value = value.replace(text, "")
    return value


def _collect_ids(value: Any, into: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ID_KEYS and isinstance(item, str):
                into.add(item)
            elif key.endswith("_ids") and isinstance(item, list):
                into.update(i for i in item if isinstance(i, str))
            else:
                _collect_ids(item, into)
    elif isinstance(value, list):
        for item in value:
            _collect_ids(item, into)


def _split_grounding(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, JsonValue]]:
    """Flag mode: strip grounding fields so the model sees the pre-grounding payload."""
    grounding = result.get("grounding")
    record: dict[str, JsonValue] = dict(grounding) if isinstance(grounding, dict) else {}
    hits = result.get("hits") or []
    record["grounded_chunk_ids"] = [
        str(h.get("chunk_id")) for h in hits if isinstance(h, dict) and h.get("grounded")
    ]
    clean_hits = [
        {k: v for k, v in h.items() if k != "grounded"} if isinstance(h, dict) else h for h in hits
    ]
    clean = {k: v for k, v in result.items() if k != "grounding"}
    if "hits" in result:
        clean["hits"] = clean_hits
    return clean, record


def _apply_grounding(name: str, result: dict[str, Any]) -> dict[str, Any]:
    """A knowledge search the grounding policy judged insufficient carries no evidence.

    Its chunks never reach the model, the allowed citation set, excerpts or citations; the
    model still sees an empty result and may call other tools or answer ``empty``.
    """
    grounding = result.get("grounding")
    if name != "search_knowledge" or not isinstance(grounding, dict):
        return result
    if grounding.get("decision") != "insufficient" or not result.get("hits"):
        return result
    return {**result, "result_status": "empty", "answer": "", "hits": [], "withheld": True}


