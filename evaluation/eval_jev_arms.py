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
  cost_usd            Jev spend per question from the run's own OnlineBudget ledger, hard
                      capped by --max-usd across all arms (generation model spend is not
                      metered here)
  jev_unknown_rate    turns whose Jev status is not "ok" (unknown / unsure / timeout / ...)

Generation-model usage: with ``--model env`` every chat-completions response's ``usage`` is
recorded per turn (prompt / completion / prompt_cache_hit / prompt_cache_miss / reasoning
tokens) through a recording httpx transport, and priced with ``--gen-price`` (USD per 1M:
cache-hit input, cache-miss input, output; defaults: DeepSeek deepseek-flash off-peak list
price checked 2026-10-11 at api-docs.deepseek.com/quick_start/pricing). Calls inside DeepSeek's
peak windows (01-04, 06-10 UTC Mon-Fri) are charged at 2x, as documented there.

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
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from campuspilot.agent.executor import NO_BASIS_ANSWER, AgentRunner
from campuspilot.chat_runtime import ConversationContext
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.evaluation_budget import OnlineBudget
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


class UsageRecorder(httpx.AsyncBaseTransport):
    """Wraps the real transport; copies each response's `usage` object (no content)."""

    def __init__(self, thinking: str = "") -> None:
        self.inner = httpx.AsyncHTTPTransport()
        self.calls: list[dict[str, Any]] = []
        self.thinking = thinking

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self.thinking and request.method == "POST":
            # DeepSeek: deepseek-flash defaults to thinking mode; the retired deepseek-chat
            # alias was the non-thinking mode. Eval-only switch, production client unchanged.
            payload = json.loads(await request.aread())
            payload["thinking"] = {"type": self.thinking}
            headers = {k: v for k, v in request.headers.items() if k.lower() != "content-length"}
            request = httpx.Request(
                request.method,
                request.url,
                headers=headers,
                json=payload,
                extensions=request.extensions,
            )
        response = await self.inner.handle_async_request(request)
        body = await response.aread()
        usage: Any = None
        try:
            usage = json.loads(body).get("usage")
        except ValueError, AttributeError:
            pass
        now = datetime.now(UTC)
        self.calls.append(
            {
                "status": response.status_code,
                "usage": usage if isinstance(usage, dict) else None,
                "peak": now.weekday() < 5 and (1 <= now.hour < 4 or 6 <= now.hour < 10),
            }
        )
        # `body` is already decoded: drop encoding/length headers so it is not decoded twice.
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
        }
        return httpx.Response(response.status_code, headers=headers, content=body, request=request)

    async def aclose(self) -> None:
        await self.inner.aclose()


def usage_of(calls: list[dict[str, Any]], price: tuple[Decimal, Decimal, Decimal]) -> dict:
    hit_p, miss_p, out_p = price
    tot = {k: 0 for k in ("prompt", "completion", "cache_hit", "cache_miss", "reasoning")}
    cost = Decimal(0)
    unknown = 0
    for c in calls:
        u = c["usage"]
        if not u:
            unknown += 1
            continue
        prompt, completion = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
        hit = int(u.get("prompt_cache_hit_tokens") or 0)
        miss = int(u.get("prompt_cache_miss_tokens") or (prompt - hit))
        details = u.get("completion_tokens_details") or {}
        tot["prompt"] += prompt
        tot["completion"] += completion
        tot["cache_hit"] += hit
        tot["cache_miss"] += miss
        tot["reasoning"] += int(details.get("reasoning_tokens") or 0)
        factor = 2 if c["peak"] else 1
        cost += factor * (hit * hit_p + miss * miss_p + completion * out_p) / 1_000_000
    return {
        **tot,
        "calls": len(calls),
        "calls_without_usage": unknown,
        "http_errors": sum(c["status"] >= 400 for c in calls),
        "cost_usd": str(cost),
    }


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


def load_cases(paths: list[Path], limits: list[int] | None) -> list[dict[str, Any]]:
    out = []
    for n, path in enumerate(paths):
        limit = None if not limits else limits[min(n, len(limits) - 1)]
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
    gen = [r["gen_usage"] for r in rows if r.get("gen_usage")]
    gen_total: dict[str, Any] = {}
    for g in gen:
        for k, v in g.items():
            gen_total[k] = (
                str(Decimal(gen_total.get(k, "0")) + Decimal(v))
                if k == "cost_usd"
                else gen_total.get(k, 0) + v
            )
    lat = [r["latency_ms"] for r in rows]
    jlat = [r["jev_latency_ms"] for r in rows if r["jev_latency_ms"]]
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
        "jev_latency_ms_p50": pct(jlat, 0.5),
        "jev_latency_ms_p95": pct(jlat, 0.95),
        "jev_cost_usd_per_question": str(spend / len(rows)) if rows else None,
        "jev_calls": len(jev),
        "jev_unknown_rate": ratio(sum(s != "ok" for s in jev), len(jev)) if jev else None,
        "jev_unsure_rate": ratio(sum(s == "unsure" for s in jev), len(jev)) if jev else None,
        "generation_usage": gen_total or None,
        "generation_cost_usd_per_question": str(Decimal(gen_total["cost_usd"]) / len(rows))
        if gen_total and rows
        else None,
        "degraded": ratio(sum(bool(r.get("degraded_reason")) for r in rows), len(rows)),
    }


async def run_arm(
    name: str,
    cases: list[dict[str, Any]],
    args: argparse.Namespace,
    model: Any,
    client: Any,
    budget: OnlineBudget,
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
    before = Decimal(str(budget.report()["charged_usd"]))
    plugin = JevPlugin(client, budget, jev_mode, snapshots) if jev_mode != "off" else None
    records: dict[str, Any] = {}
    agent = AgentRunner(
        registry,
        repo,
        model,
        grounding=grounding,
        jev=plugin,
        trace=lambda kind, record: records.__setitem__(kind, record),
    )
    rows = []
    recorder: UsageRecorder | None = getattr(model, "transport", None)  # type: ignore[assignment]
    for c in cases:
        records.clear()
        mark = len(recorder.calls) if isinstance(recorder, UsageRecorder) else 0
        started = time.perf_counter()
        body = await agent.run(c["question"], ConversationContext())
        latency = (time.perf_counter() - started) * 1000  # shadow Jev runs after this
        await agent.drain()
        jev = records.get("jev")
        rows.append(
            {
                **c,
                "latency_ms": latency,
                "jev_latency_ms": jev.get("latency_ms") if jev else None,
                "jev_reason": jev.get("reason") if jev else None,
                "would_refuse_local": (records.get("grounding_check") or {}).get("would_refuse"),
                "refused": refused(body),
                "result_status": body.get("result_status"),
                "excerpt_ids": [e.get("chunk_id") for e in body.get("excerpts") or []],
                "citations": [x.get("id") for x in body.get("citations") or []],
                "degraded_reason": body.get("degraded_reason"),
                "gen_usage": usage_of(recorder.calls[mark:], args.gen_price_decimal)
                if isinstance(recorder, UsageRecorder)
                else None,
                "jev_record": jev,
                "jev_status": jev.get("status") if jev else None,
                "jev_decision": jev.get("decision") if jev else None,
                "jev_applied": jev.get("applied") if jev else None,
            }
        )
    spend = Decimal(str(budget.report()["charged_usd"])) - before
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
    p.add_argument(
        "--limit", type=int, nargs="+", help="first N cases per file (one value or one per file)"
    )
    p.add_argument("--max-usd", default="0.50", help="hard Jev spend cap for the whole run")
    p.add_argument("--ledger-dir", type=Path, help="budget ledger dir (default: new temp dir)")
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
    p.add_argument(
        "--gen-price",
        nargs=3,
        default=["0.003", "0.15", "0.6"],
        metavar=("HIT", "MISS", "OUT"),
        help="generation USD per 1M tokens: cache-hit input, cache-miss input, output",
    )
    p.add_argument(
        "--gen-thinking",
        choices=("disabled", "enabled", ""),
        default="disabled",
        help='DeepSeek "thinking" request field ("" = provider default)',
    )
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
        if model is not None:
            model = replace(model, transport=UsageRecorder(a.gen_thinking))
    a.gen_price_decimal = tuple(Decimal(x) for x in a.gen_price)
    cases = load_cases(a.cases, a.limit)

    ledger = a.ledger_dir or Path(tempfile.mkdtemp(prefix="jev-eval-"))
    budget = OnlineBudget(ledger, Decimal(a.max_usd), 1000)

    async def all_arms() -> dict[str, Any]:
        return {name: await run_arm(name, cases, a, model, client, budget) for name in a.arms}

    arms = asyncio.run(all_arms())
    report = {
        "jev_client": a.jev,
        "generation_model": getattr(model, "model", None) if model is not None else "none",
        "generation_price_usd_per_million": a.gen_price,
        "generation_thinking": a.gen_thinking or "provider_default",
        "max_usd": a.max_usd,
        "jev_spend_usd_total": str(budget.report()["charged_usd"]),
        "jev_calls_total": budget.report()["calls"],
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
