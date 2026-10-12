"""Retrieval eval (lexical / vector / hybrid): Recall@1/3/5, MRR@20, refusal handling.

Case formats: {"question","target_chunk_ids","topic"} or {"case_id","question","chunk_ids",...}.
Cases with no gold ids are refusal cases: correct when the retriever returns no hits.
Query embeddings come from Cloudflare Workers AI (CF_ACCOUNT_ID / CF_API_TOKEN, never printed)
and are cached on disk keyed by sha256(model + text) so tuning sweeps do not re-call the API.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from campuspilot.chat_runtime import ConversationContext, filters_for
from campuspilot.config import Settings
from campuspilot.llm.embedding import CloudflareEmbedder
from campuspilot.rag import KnowledgeSnapshot
from campuspilot.retrieval.hybrid import HybridRetriever
from campuspilot.retrieval.vector import INDEX_NAME, VectorIndex

ROOT = Path(__file__).resolve().parents[1]
MODES = ("lexical", "vector", "hybrid")
DEFAULT_SNAPSHOT = ROOT / "data/cdut/rag/approved-20261011b"
CACHE = ROOT / ".cache/eval-embeddings.json"


def load_cases(path: Path) -> list[dict]:
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if line.strip():
            c = json.loads(line)
            gold = c.get("chunk_ids") or c.get("target_chunk_ids") or []
            out.append(
                {
                    "id": c.get("case_id", f"q{i + 1:03d}"),
                    "question": c["question"],
                    "gold": gold,
                    "group": c.get("topic") or c.get("split") or "all",
                }
            )
    return out


def embed_all(texts: list[str], settings: Settings) -> dict[str, list[float]]:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    key = lambda t: hashlib.sha256((settings.embedding_model + "\0" + t).encode()).hexdigest()  # noqa: E731
    missing = sorted({t for t in texts if key(t) not in cache})
    if missing:
        emb = CloudflareEmbedder(
            settings.cf_account_id,
            settings.cf_api_token,
            model=settings.embedding_model,
            timeout=30,
        )
        for t, v in zip(missing, emb.embed(missing), strict=True):
            cache[key(t)] = v
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(cache))
    return {t: cache[key(t)] for t in texts}


def evaluate(cases, snap, index, vectors, modes, retriever_kwargs=None):
    results, per_case = (
        {},
        {c["id"]: {"id": c["id"], "question": c["question"], "gold": c["gold"]} for c in cases},
    )
    for m in modes:
        r = HybridRetriever(snap, mode=m, index=index, **(retriever_kwargs or {}))
        rows, refusals = [], []
        for c in cases:
            hits = r.search(
                c["question"],
                filters_for(c["question"], ConversationContext()),
                20,
                query_vector=vectors.get(c["question"]),
            )
            ranked = [h.chunk.chunk_id for h in hits]
            per_case[c["id"]][m] = {"rank": None, "top3": ranked[:3], "n_hits": len(ranked)}
            if not c["gold"]:
                refusals.append(not ranked)
                continue
            g = set(c["gold"])
            rank = next((i + 1 for i, x in enumerate(ranked) if x in g), None)
            per_case[c["id"]][m]["rank"] = rank
            rows.append(
                ({k: len(g & set(ranked[:k])) / len(g) for k in (1, 3, 5)}, rank, not ranked)
            )
        n = len(rows) or 1
        results[m] = {
            **{f"recall@{k}": round(sum(x[0][k] for x in rows) / n, 4) for k in (1, 3, 5)},
            "hit@1": round(sum(1 for x in rows if x[1] == 1) / n, 4),
            "hit@5": round(sum(1 for x in rows if x[1] and x[1] <= 5) / n, 4),
            "mrr@20": round(sum(1 / x[1] for x in rows if x[1]) / n, 4),
            "miss@20": sum(1 for x in rows if not x[1]),
            "answerable_empty": sum(1 for x in rows if x[2]),
            "refusal_correct": f"{sum(refusals)}/{len(refusals)}",
        }
    return results, list(per_case.values())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT)
    p.add_argument("--modes", default=",".join(MODES))
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    modes = a.modes.split(",")
    s = Settings.from_env()
    snap = KnowledgeSnapshot.model_validate_json((a.snapshot_dir / "snapshot.json").read_bytes())
    cases = load_cases(a.cases)
    known = {ch.chunk_id for ch in snap.chunks}
    index, vectors = None, {}
    if any(m != "lexical" for m in modes):
        if not s.embeddings_configured:
            raise SystemExit(
                "CF_ACCOUNT_ID / CF_API_TOKEN missing: vector and hybrid cannot be measured"
            )
        index = VectorIndex.load(a.snapshot_dir / INDEX_NAME, snap, s.embedding_model)
        vectors = embed_all([c["question"] for c in cases], s)
    results, per_case = evaluate(cases, snap, index, vectors, modes)
    report = {
        "cases_file": str(a.cases),
        "knowledge_version": snap.version,
        "n": len(cases),
        "n_refusal": sum(1 for c in cases if not c["gold"]),
        "unknown_gold_ids": sorted({g for c in cases for g in c["gold"]} - known),
        "vector_backend": index.backend if index else None,
        "results": results,
        "per_case": per_case,
    }
    if a.output:
        a.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "per_case"}, ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
