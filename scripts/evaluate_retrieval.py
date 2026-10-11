"""Compare lexical (BM25) / vector / hybrid (RRF) retrieval: Recall@5 and MRR@20.

Uses evaluation/runtime-migration/cases.jsonl cases that label gold chunk_ids, the bootstrap
snapshot and its vector index. Query embeddings call Cloudflare Workers AI with credentials
from the environment (CF_ACCOUNT_ID / CF_API_TOKEN); they are never printed. Results are
reported per split; the holdout split is reported only and must not be used for tuning.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from campuspilot.chat_runtime import ConversationContext, filters_for
from campuspilot.config import Settings
from campuspilot.llm.embedding import CloudflareEmbedder
from campuspilot.rag import KnowledgeSnapshot
from campuspilot.retrieval.hybrid import HybridRetriever, RetrievalMode
from campuspilot.retrieval.vector import INDEX_NAME, VectorIndex

ROOT = Path(__file__).resolve().parents[1]
MODES: tuple[RetrievalMode, ...] = ("lexical", "vector", "hybrid")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path, default=ROOT / "evaluation/runtime-migration/cases.jsonl"
    )
    parser.add_argument("--store", type=Path, default=ROOT / "data/cdut/rag")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    settings = Settings.from_env()
    snapshot = KnowledgeSnapshot.model_validate_json((args.store / "bootstrap.json").read_bytes())
    index = VectorIndex.load(
        args.store / ("bootstrap." + INDEX_NAME), snapshot, settings.embedding_model
    )
    embedder = CloudflareEmbedder(
        settings.cf_account_id, settings.cf_api_token, model=settings.embedding_model, timeout=30
    )
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines()]
    cases = [c for c in cases if c["chunk_ids"]]
    vectors = dict(
        zip(
            [c["case_id"] for c in cases],
            embedder.embed([c["question"] for c in cases]),
            strict=True,
        )
    )
    retrievers = {m: HybridRetriever(snapshot, mode=m, index=index) for m in MODES}
    report: dict[str, object] = {
        "knowledge_version": snapshot.version,
        "embedding_model": settings.embedding_model,
        "vector_backend": index.backend,
        "rrf_k": 60,
        "k": args.k,
        "cases": len(cases),
        "results": {},
    }
    results: dict[str, dict[str, dict[str, float]]] = {}
    for mode, retriever in retrievers.items():
        per_split: dict[str, list[tuple[float, float]]] = {}
        for case in cases:
            filters = filters_for(case["question"], ConversationContext())
            hits = retriever.search(
                case["question"], filters, 20, query_vector=vectors[case["case_id"]]
            )
            ranked = [h.chunk.chunk_id for h in hits]
            gold = set(case["chunk_ids"])
            recall = len(gold & set(ranked[: args.k])) / len(gold)
            rr = next((1 / (i + 1) for i, cid in enumerate(ranked) if cid in gold), 0.0)
            for split in (case["split"], "all"):
                per_split.setdefault(split, []).append((recall, rr))
        results[mode] = {
            split: {
                "n": len(rows),
                f"recall@{args.k}": round(sum(r for r, _ in rows) / len(rows), 4),
                "mrr@20": round(sum(m for _, m in rows) / len(rows), 4),
            }
            for split, rows in sorted(per_split.items())
        }
    report["results"] = results
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
