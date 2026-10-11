"""Four-arm agent-level comparison for the Jev plugin (CAMPUSPILOT_JEV), dev + refusal sets.

Arms (all hybrid retrieval, same cases, same generation model):
  A  current            CAMPUSPILOT_GROUNDING=flag, CAMPUSPILOT_JEV=off
  B  + local grounding  CAMPUSPILOT_GROUNDING=block, CAMPUSPILOT_JEV=off
  C  + jev shadow       CAMPUSPILOT_GROUNDING=flag, CAMPUSPILOT_JEV=shadow
  D  + jev on           CAMPUSPILOT_GROUNDING=flag, CAMPUSPILOT_JEV=on

Metrics per arm and per case file:
  refusal_recall      refusal cases (no gold chunk ids) answered with a refusal/clarification
  false_refusal       answerable cases (gold chunk ids) answered with a refusal/clarification
  citation_accuracy   answerable, not refused: share of shown excerpt chunks that are gold
                      (precision) and share of cases with >=1 gold excerpt (hit rate);
                      refusal cases: share with no excerpts and no citations
  latency_ms          p50 / p95 per turn (wall clock, includes model and Jev calls)
  cost_usd            Jev spend per question from the EvaluationBudget ledger (generation
                      model spend is not metered here)
  jev_unknown_rate    turns whose Jev status is not "ok" (unknown / unsure / timeout / ...)

Safety: the default ``--jev fake`` uses an offline stand-in that always answers ``unknown``
(arms C/D then equal A: a wiring smoke test only). ``--jev live`` calls OpenRouter with the
configured CAMPUSPILOT_JEV_* key and prices and spends real money within the $5 / 1000-call
ledger; it also requires ``--i-understand-this-is-paid``. Query embeddings come only from the
disk cache (``--embedding-cache``); missing vectors make the case lexical-only (unassessed).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from campuspilot.agent.executor import NO_BASIS_ANSWER, AgentRunner
from campuspilot.chat_runtime import ConversationContext
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.evaluation_budget import EvaluationBudget
from campuspilot.jev_plugin import JevMode, JevPlugin
from campuspilot.jev_shadow import ShadowResult
from campuspilot.knowledge import KnowledgeStore
from campuspilot.rag import RetrievalHit, SnapshotStore
from campuspilot.retrieval.grounding import GroundingMode
from campuspilot.tools import agent_registry

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/cdut"
ARMS: dict[str, tuple[GroundingMode, JevMode]] = {
    "A_current": ("flag", "off"),
    "B_local_block": ("block", "off"),
    "C_jev_shadow": ("flag", "shadow"),
    "D_jev_on": ("flag", "on"),
}
DEFAULT_CASES = [
    ROOT / "evaluation/dev-colloquial-20261011/cases.jsonl",
    ROOT / "evaluation/refusal-20261011/dev.jsonl",
]


class CachedEmbedder:
    """Query vectors from the eval disk cache only; never calls the embedding service."""

    def __init__(self, cache: Path, model: str) -> None:
        self.data: dict[str, list[float]] = json.loads(cache.read_text()) if cache.exists() else {}
        self.model = model
        self.cached: list[float] | None = None

    def embed_query(self, text: str) -> list[float]:
        key = hashlib.sha256((self.model + "\0" + text).encode()).hexdigest()
        if key not in self.data:
            from campuspilot.llm.embedding import EmbeddingUnavailable

            raise EmbeddingUnavailable("not cached")
        return self.data[key]

    async def prefetch(self, text: str) -> None:
        return None


class OfflineJev:
    """Always ``unknown``: exercises the fail-open wiring without any network."""

    timeout_seconds = 3.0

    async def evaluate(
        self, question: str, candidates: tuple[RetrievalHit, ...], **_: Any
    ) -> ShadowResult:
        return ShadowResult(
            status="unknown",
            selected_ids=tuple(h.chunk.chunk_id for h in candidates[:4]),
            reason="offline_fake",
        )


def load_cases(paths: list[Path], limit: int | None) -> list[dict[str, Any]]:
    out = []
    for path in paths:
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        for i, c in enumerate(rows[:limit]):
            out.append(
                {
                    "id": c.get("case_id", f"{path.stem}-{i}"),
                    "file": path.parent.name + "/" + path.name,
                    "question": c["question"],
                    "gold": c.get("chunk_ids") or c.get("target_chunk_ids") or [],
                }
            )
    return out


def refused(body: dict[str, Any]) -> bool:
    return (
        body.get("answer") == NO_BASIS_ANSWER
        or body.get("answer_mode") == "agent_jev"
        or (body.get("result_status") == "empty" and not body.get("excerpts"))
    )


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 1)


def ratio(n: int, d: int) -> str:
    return f"{n}/{d}" + (f" ({n / d:.1%})" if d else "")


def summarize(rows: list[dict[str, Any]], spend: Decimal) -> dict[str, Any]:
    ans = [r for r in rows if r["gold"]]
    ref = [r for r in rows if not r["gold"]]
    answered = [r for r in ans if not r["refused"]]
    shown = [c for r in answered for c in r["excerpt_ids"]]
    gold_shown = [c for r in answered for c in r["excerpt_ids"] if c in r["gold"]]
    jev = [r["jev_status"] for r in rows if r["jev_status"] is not None]
    lat = [r["latency_ms"] for r in rows]
    return {
        "n": len(rows),
        "refusal_recall": ratio(sum(r["refused"] for r in ref), len(ref)),
        "false_refusal": ratio(sum(r["refused"] for r in ans), len(ans)),
        "citation_precision": round(len(gold_shown) / len(shown), 4) if shown else None,
        "citation_hit_rate": ratio(
            sum(any(c in r["gold"] for c in r["excerpt_ids"]) for r in answered), len(answered)
        ),
        "refusal_citation_free": ratio(
            sum(not r["excerpt_ids"] and not r["citations"] for r in ref), len(ref)
        ),
        "latency_ms_p50": pct(lat, 0.5),
        "latency_ms_p95": pct(lat, 0.95),
        "jev_cost_usd_per_question": str(spend / len(rows)) if rows else None,
        "jev_calls": len(jev),
        "jev_unknown_rate": ratio(sum(s != "ok" for s in jev), len(jev)) if jev else None,
        "jev_unsure_rate": ratio(sum(s == "unsure" for s in jev), len(jev)) if jev else None,
    }


async def run_arm(
    name: str, cases: list[dict[str, Any]], args: argparse.Namespace, model: Any, client: Any
) -> dict[str, Any]:
    grounding, jev_mode = ARMS[name]
    emb = CachedEmbedder(args.embedding_cache, args.embedding_model)
    snapshots = SnapshotStore(
        DATA / "rag",
        "hybrid",
        embedder=emb,
        bundled=args.knowledge_bundle,  # type: ignore[arg-type]
    )
    repo = DirectoryRepository.load(DATA)
    registry = agent_registry(
        repo,
        KnowledgeStore.load(DATA / "knowledge.json"),
        snapshots,
        emb,  # type: ignore[arg-type]
        roster=DATA / "teachers_roster.json",
        grounding=grounding,
    )
    ledger = Path(tempfile.mkdtemp(prefix=f"jev-eval-{name}-"))
    budget = EvaluationBudget(ledger, "phase2")
    plugin = JevPlugin(client, budget, jev_mode, snapshots) if jev_mode != "off" else None
    agent = AgentRunner(registry, repo, model, grounding=grounding, jev=plugin)
    rows = []
    for c in cases:
        started = time.perf_counter()
        body = await agent.run(c["question"], ConversationContext())
        jev = body.get("jev") if isinstance(body.get("jev"), dict) else None
        rows.append(
            {
                **c,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "refused": refused(body),
                "result_status": body.get("result_status"),
                "excerpt_ids": [e.get("chunk_id") for e in body.get("excerpts") or []],
                "citations": [x.get("id") for x in body.get("citations") or []],
                "jev_status": jev.get("status") if jev else None,
                "jev_decision": jev.get("decision") if jev else None,
                "jev_applied": jev.get("applied") if jev else None,
            }
        )
    spend = Decimal(str(budget.report()["charged_usd"]))
    files = sorted({r["file"] for r in rows})
    return {
        "grounding": grounding,
        "jev": jev_mode,
        "overall": summarize(rows, spend),
        "by_file": {f: summarize([r for r in rows if r["file"] == f], Decimal(0)) for f in files},
        "cases": rows,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cases", type=Path, nargs="+", default=DEFAULT_CASES)
    p.add_argument("--arms", nargs="+", choices=sorted(ARMS), default=sorted(ARMS))
    p.add_argument("--limit", type=int, help="first N cases per file (smoke runs)")
    p.add_argument("--jev", choices=("fake", "live"), default="fake")
    p.add_argument("--i-understand-this-is-paid", action="store_true")
    p.add_argument(
        "--model",
        choices=("none", "env"),
        default="none",
        help="none: summary path only; env: CAMPUSPILOT_MODEL_* generation model",
    )
    p.add_argument("--embedding-cache", type=Path, default=ROOT / ".cache/eval-embeddings.json")
    p.add_argument("--embedding-model", default="@cf/baai/bge-m3")
    p.add_argument("--knowledge-bundle", default="approved-20261011b")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.jev == "live":
        if not a.i_understand_this_is_paid:
            p.error("--jev live spends real money; add --i-understand-this-is-paid")
        from campuspilot.migration_config import shadow_client

        client: Any = shadow_client()
    else:
        client = OfflineJev()
    model = None
    if a.model == "env":
        from campuspilot.migration_config import generation_model

        model = generation_model()
    cases = load_cases(a.cases, a.limit)

    async def all_arms() -> dict[str, Any]:
        return {name: await run_arm(name, cases, a, model, client) for name in a.arms}

    arms = asyncio.run(all_arms())
    report = {
        "jev_client": a.jev,
        "generation_model": a.model,
        "case_files": [
            str(c.relative_to(ROOT)) if c.is_relative_to(ROOT) else str(c) for c in a.cases
        ],
        "summary": {k: {"overall": v["overall"], "by_file": v["by_file"]} for k, v in arms.items()},
        "arms": arms,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if a.output:
        a.output.write_text(text + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
