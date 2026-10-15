"""Prepare and replay public development cases against the same frozen local evidence.

The command line only prepares files offline. A caller supplies budgeted models and a
shared OnlineBudget for ``replay_arm``; this module never reads credentials or makes its
own provider clients. Replay bypasses understanding, retrieval, embedding and web search.
It measures the current Jev/answer path on already collected documents, not new-web quality.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import time
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from campuspilot.agent.evidence import Evidence, _collect_ids, _split_grounding
from campuspilot.agent.executor import AgentRunner
from campuspilot.agent.plan import Plan
from campuspilot.agent.understand import Understanding
from campuspilot.chat_runtime import ConversationContext, public_input
from campuspilot.rag import KnowledgeSnapshot, SnapshotStore, canonical, digest
from campuspilot.retrieval.hybrid import HybridRetriever
from pydantic import JsonValue

Arm = Literal["off", "jev_on"]
LABEL_FIELDS = ("id", "category", "question", "expected", "unknown", "support_ids", "label_basis")


@dataclass(frozen=True)
class ReplayCase:
    """Gold labels are audit data; only question/view/tools enter answer generation."""

    ident: str
    question: str
    category: str
    knowledge_version: str
    understanding: Understanding
    tools: tuple[dict[str, JsonValue], ...]
    labels: dict[str, Any]

    @property
    def evidence_sha256(self) -> str:
        return digest(canonical(self.tools))

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.ident, "question": self.question, "category": self.category,
            "knowledge_version": self.knowledge_version,
            "understanding": self.understanding.model_dump(mode="json"),
            "evidence_sha256": self.evidence_sha256,
            "tools": copy.deepcopy(self.tools), "labels": copy.deepcopy(self.labels),
        }


def validate_tools(
    tools: Sequence[dict[str, Any]], snapshot: KnowledgeSnapshot,
) -> None:
    """Old retrieval bodies must still match the exact approved local snapshot."""
    chunks = {chunk.chunk_id: chunk for chunk in snapshot.chunks}
    sources = {source.source_id: source for source in snapshot.sources}
    if not tools or len(tools) > 8:
        raise ValueError("replay_tool_count_invalid")
    for entry in tools:
        name, result = entry.get("tool"), entry.get("result")
        if set(entry) != {"tool", "result"} or not isinstance(result, dict):
            raise ValueError("replay_tool_record_invalid")
        if name == "search_service" and not any(
            result.get(key) for key in ("matches", "evidence", "sources", "answer")
        ):
            continue  # Keep an original empty directory search without adding any facts.
        if name != "search_knowledge":
            raise ValueError("replay_local_document_only")
        if result.get("knowledge_version") != snapshot.version:
            raise ValueError("replay_knowledge_version_mismatch")
        hits = result.get("hits")
        if not isinstance(hits, list) or len(hits) > 8:
            raise ValueError("replay_hits_invalid")
        for row in hits:
            if not isinstance(row, dict) or row.get("web"):
                raise ValueError("replay_local_document_only")
            chunk = chunks.get(str(row.get("chunk_id")))
            if chunk is None or row.get("source_id") != chunk.source_id:
                raise ValueError("replay_chunk_unknown")
            source = sources[chunk.source_id]
            if (row.get("text") != chunk.text or row.get("text_sha256") != chunk.text_sha256
                    or row.get("url") != source.url):
                raise ValueError("replay_body_or_source_mismatch")
        if result.get("answer", "") != "\n".join(str(row["text"]) for row in hits[:3]):
            raise ValueError("replay_summary_mismatch")


def prepare_cases(
    labels: Sequence[Mapping[str, Any]], observations: Sequence[Mapping[str, Any]],
    snapshot: KnowledgeSnapshot, source_arm: str = "off",
) -> list[ReplayCase]:
    """Select only public case labels and raw tool records; discard history/messages/usage."""
    selected = [row for row in observations if row.get("arm") == source_arm]
    records = {str(row.get("id")): row for row in selected}
    if len(records) != len(selected):
        raise ValueError("replay_duplicate_source_case")
    prepared: list[ReplayCase] = []
    for label in labels:
        ident, question = str(label["id"]), str(label["question"])
        if not question.strip() or len(question) > 2000 or not public_input(question):
            raise ValueError("replay_public_question_required")
        if "public" not in str(label.get("label_basis", "")).lower():
            raise ValueError("replay_public_scenario_label_required")
        row = records.get(ident)
        if row is None or row.get("question") != question:
            raise ValueError("replay_case_missing_or_question_mismatch")
        body, raw_tools = row.get("body"), row.get("evidence")
        if not isinstance(body, dict) or not isinstance(raw_tools, list):
            raise ValueError("replay_original_tools_required")
        validate_tools(raw_tools, snapshot)
        prepared.append(ReplayCase(
            ident, question, str(label["category"]), snapshot.version,
            Understanding.model_validate(body.get("understanding")),
            tuple(copy.deepcopy(raw_tools)),
            {key: copy.deepcopy(label[key]) for key in LABEL_FIELDS if key in label},
        ))
    return prepared


def replay_evidence(agent: AgentRunner, case: ReplayCase) -> Evidence:
    """Rebuild normal flag-mode absorption, freshly for every arm and repetition."""
    evidence = Evidence(question=case.question, routing_complete=True)
    for entry in copy.deepcopy(case.tools):
        name = str(entry["tool"])
        raw = cast(dict[str, Any], entry["result"])
        if name == "search_knowledge" and isinstance(raw.get("grounding"), dict):
            result, record = _split_grounding(raw)
            if not result.get("hits"):
                record["decision"] = "insufficient"
            evidence.grounding_checks.append(record)
        else:
            result = raw
        evidence.results.append({"tool": name, "result": result})
        _collect_ids(result, evidence.allowed)
        agent._absorb(name, result, evidence)
    return evidence


async def replay_arm(
    agent: AgentRunner, case: ReplayCase, frozen: HybridRetriever, arm: Arm,
) -> dict[str, Any]:
    """Use real supplied models; the caller owns credentials, budget and usage capture.

    Construct each runner with ToolRegistry(()), max_tool_rounds=0, grounding='flag',
    snapshots=the same store, and (for jev_on) the ordinary JevPlugin using that store.
    No tool capability can be supplied to the model during this restricted experiment.
    """
    if (agent.registry.tools or agent.max_tool_rounds != 0 or agent.web_service is not None
            or agent.grounding != "flag" or agent.model is None):
        raise ValueError("replay_requires_generation_only_runner")
    mode = agent.jev.mode if agent.jev is not None else "off"
    if mode != ("on" if arm == "jev_on" else "off"):
        raise ValueError("replay_arm_mode_mismatch")
    if frozen.snapshot.version != case.knowledge_version:
        raise ValueError("replay_knowledge_version_mismatch")
    validate_tools(case.tools, frozen.snapshot)
    evidence = replay_evidence(agent, case)
    before = [str(hit["chunk_id"]) for hit in evidence.hits]
    started = time.monotonic()
    with ExitStack() as pins:
        for store in agent._snapshot_stores:
            pins.enter_context(store.pin(frozen))
        async with asyncio.timeout(45):
            body = await agent._with_jev(
                case.question, case.understanding.model_copy(deep=True), ConversationContext(),
                evidence, Plan(), [],
            )
            await agent.drain()
    return {
        "id": case.ident, "category": case.category, "question": case.question, "arm": arm,
        "knowledge_version": case.knowledge_version, "evidence_sha256": case.evidence_sha256,
        "before_chunk_ids": before,
        "after_chunk_ids": [str(hit["chunk_id"]) for hit in evidence.hits],
        "latency_ms": round((time.monotonic() - started) * 1000, 1), "body": body,
        "experiment": "fixed_local_evidence_development_replay_no_web",
        "quality_review": "pending_source_review",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--knowledge-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-arm", default="off")
    args = parser.parse_args()
    store = SnapshotStore(args.knowledge_root, "lexical")
    retriever = store.acquire()
    if retriever is None or store.load_error:
        raise ValueError("replay_snapshot_unavailable")
    raw = args.observations.read_bytes()
    labels = json.loads(args.labels.read_bytes())
    cases = prepare_cases(labels, [json.loads(line) for line in raw.splitlines() if line.strip()],
                          retriever.snapshot, args.source_arm)
    output = {
        "experiment": "fixed_local_evidence_development_replay_no_web", "holdout": False,
        "knowledge_version": retriever.snapshot.version,
        "input_observations_sha256": digest(raw),
        "input_labels_sha256": digest(args.labels.read_bytes()),
        "cases": [case.as_dict() for case in cases],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as target:
        target.write(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"prepared": len(cases), "knowledge_version": retriever.snapshot.version}))


if __name__ == "__main__":
    main()
