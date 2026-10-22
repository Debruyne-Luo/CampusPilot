"""Metered, resumable real-answer acceptance; never changes an active knowledge pointer."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
import time
from decimal import Decimal
from pathlib import Path

from campuspilot.agent.executor import AgentRunner
from campuspilot.chat_runtime import ConversationContext
from campuspilot.dify import ChatUnavailable
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.evaluation_budget import TokenPrice
from campuspilot.experiment_budget import CampaignBudget
from campuspilot.jev_plugin import JevPlugin
from campuspilot.jev_shadow import JevShadowClient
from campuspilot.knowledge import KnowledgeStore, campus_clock
from campuspilot.knowledge_answer_eval import FixtureClockRetriever, RecordingRegistry
from campuspilot.knowledge_evaluation import Observation, QualityCase, fingerprint, validate_suite
from campuspilot.knowledge_release import atomic_write, read_candidate, release_reference
from campuspilot.llm.chat_model import ChatCompletionsModel, Completion
from campuspilot.rag import SnapshotStore, canonical, digest
from campuspilot.tools import agent_registry
from evaluate_student_experience import SmokeModel, key_file

ROOT = Path(__file__).resolve().parents[1]


class ObservedModel(SmokeModel):
    """Record format/failure metadata, never headers or credentials."""

    records: list[dict[str, object]]

    async def complete(self, messages, tools=None, json_mode=False, max_tokens=None) -> Completion:
        try:
            value = await super().complete(messages, tools, json_mode, max_tokens)
        except ChatUnavailable as exc:
            self.records.append({"error": exc.code})
            raise
        record: dict[str, object] = {"finish_reason": value.finish_reason,
                                    "tools": [c.name for c in value.tool_calls]}
        try:
            parsed = json.loads(value.content or "")
            if isinstance(parsed, dict):
                record.update(json_keys=list(parsed), status=parsed.get("status"))
                if "answer" in parsed:
                    record["reply"] = parsed
        except ValueError:
            record["json_valid"] = False
        self.records.append(record)
        return value


async def collect(args: argparse.Namespace) -> None:
    output: Path = args.output
    output.mkdir(parents=True, exist_ok=True)
    snapshot = read_candidate(args.candidate)
    if snapshot.pending:
        raise ValueError("pending_source_adoption")
    cases = [QualityCase.model_validate_json(line) for line in args.cases.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    validate_suite(cases, require_full=True)
    selected = [c for c in cases if c.split == "holdout"]
    runtime_hash = digest(canonical({p.relative_to(ROOT).as_posix(): digest(p.read_bytes())
                                    for p in sorted((ROOT / "backend/src").rglob("*.py"))}))
    binding = {"knowledge_version": snapshot.version, "runtime_sha256": runtime_hash,
               "cases": {c.case_id: fingerprint(c.model_dump(mode="json")) for c in selected},
               "mode": "lexical", "judge": "on", "web": "off_local_rag_acceptance"}
    binding_path = output / "binding.json"
    if binding_path.exists() and json.loads(binding_path.read_bytes()) != binding:
        raise ValueError("Frozen inputs changed; observations cannot be silently reused")
    atomic_write(binding_path, canonical(binding))
    journal = output / "observations.jsonl"
    done = {json.loads(line)["case_id"] for line in journal.read_text(
        encoding="utf-8").splitlines()} if journal.exists() else set()
    inflight = output / "inflight.json"
    if inflight.exists() and json.loads(inflight.read_bytes()).get("case_id"):
        raise ValueError("Unconfirmed previous case; do not automatically repeat paid requests")
    pending = [c for c in selected if c.case_id not in done]
    if args.case_id:
        requested = set(args.case_id)
        if requested - {c.case_id for c in selected}:
            raise ValueError("Unknown holdout case")
        pending = [c for c in pending if c.case_id in requested]
    if not done and args.limit != 2:
        raise ValueError("First run requires --limit 2")
    if args.limit:
        pending = pending[:args.limit]
    credentials = json.loads(args.config.read_bytes())
    budget = CampaignBudget(args.budget_dir)
    model = ObservedModel(ChatCompletionsModel(
        "https://api.deepseek.com", "deepseek-flash",
        key_file(Path(credentials["deepseek_key_file"])), max_output_tokens=1500,
    ), budget)
    model.records = []
    with tempfile.TemporaryDirectory(prefix="campuspilot-frozen-acceptance-") as temp:
        root = Path(temp)
        copied = root / "versions" / snapshot.version
        shutil.copytree(args.candidate, copied)
        atomic_write(root / "current.json", canonical(release_reference(copied)))
        store = SnapshotStore(root, "lexical")
        base = store.acquire()
        assert base is not None
        directory = args.candidate / "directory"
        repo = DirectoryRepository.load(directory)
        knowledge = KnowledgeStore.load(directory / "knowledge.json")
        for case in pending:
            model_boundary = len(model.records)
            atomic_write(inflight, canonical({"case_id": case.case_id,
                                              "case_sha256": binding["cases"][case.case_id]}))
            registry = RecordingRegistry(agent_registry(
                repo, knowledge, store, roster=directory / "teachers_roster.json",
            ))
            judge = JevPlugin(JevShadowClient(
                key_file(Path(credentials["jev_key_file"])),
                TokenPrice(Decimal(".042"), Decimal("0")),
            ), budget, "on", store)
            agent = AgentRunner(registry, repo, model, snapshots=store, concise=True, jev=judge)
            retriever = FixtureClockRetriever(base, case)
            context = ConversationContext(audience=(
                "unknown" if case.audience == "all" else case.audience),
                campus=case.campus or "chengdu", academic_year=case.academic_year)
            before = Decimal(json.loads(budget.path.read_bytes())["charged_usd"])
            started = time.perf_counter()
            turns = []
            with campus_clock(case.today), store.pin(retriever):
                for question in (*case.messages, case.question):
                    boundary = len(retriever.records)
                    body = await agent.run(question, context)
                    turns.append({"question": question, "response": body})
                    context.remember(question, str(body.get("answer") or ""))
            await agent.drain()
            cost = Decimal(json.loads(budget.path.read_bytes())["charged_usd"]) - before
            ranked = tuple(dict.fromkeys(cid for r in retriever.records[boundary:]
                                         for cid in r["ranked_chunk_ids"]))
            shown = tuple(str(e["chunk_id"]) for e in body.get("excerpts", [])
                          if isinstance(e, dict) and e.get("chunk_id"))
            sources = tuple(str(c.get("source_id") or c["id"])
                            for c in body.get("citations", [])
                            if isinstance(c, dict) and (c.get("source_id") or c.get("id")))
            observation = Observation(
                case_id=case.case_id, case_sha256=binding["cases"][case.case_id],
                knowledge_version=snapshot.version, ranked_chunk_ids=ranked,
                shown_chunk_ids=shown, cited_source_ids=sources,
                answer=str(body.get("answer") or ""), behavior=None,
                latency_ms=(time.perf_counter() - started) * 1000, cost_usd=float(cost),
                execution_mode="real_agent_lexical_jev_on",
            )
            detail = {"case_id": case.case_id, "turns": turns, "tools": registry.records,
                      "retrieval": retriever.records, "binding": binding,
                      "model_calls": model.records[model_boundary:],
                      "observation_sha256": fingerprint(observation.model_dump(mode="json"))}
            atomic_write(output / (case.case_id + ".json"), canonical(detail))
            with journal.open("ab") as stream:
                stream.write(observation.model_dump_json().encode() + b"\n")
                stream.flush()
            atomic_write(inflight, canonical({"case_id": None}))
            print(json.dumps({"case_id": case.case_id, "completed": len(done) + 1,
                              "latency_ms": round(observation.latency_ms),
                              "result": body.get("result_status")}), flush=True)
            done.add(case.case_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate", "cases", "config", "budget-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-id", action="append", default=[],
                        help="Only repeat cases affected by a documented change or failure")
    asyncio.run(collect(parser.parse_args()))
