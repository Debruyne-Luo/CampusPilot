"""Refusal eval for the local grounding policy (retrieval level, hybrid mode, top-4 shown).

insufficient-policy recall = explicitly labeled refuse/clarify cases marked ``insufficient``
false-insufficient rate = answerable cases marked ``insufficient``
These retrieval-policy decisions do not establish answer-level refusal correctness.
baseline ("before") = the previous behaviour: refuse only when retrieval returns zero hits.
Also re-reports hybrid Recall@5 / MRR@20 to show ranking is unchanged by this work.

Query embeddings: Cloudflare Workers AI via eval_colloquial.embed_all (disk cache).
Use --sweep on dev sets only; thresholds must never be picked on test files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from campuspilot.chat_runtime import ConversationContext, filters_for
from campuspilot.config import Settings
from campuspilot.knowledge_evaluation import legacy_behavior
from campuspilot.rag import KnowledgeSnapshot
from campuspilot.retrieval import grounding
from campuspilot.retrieval.hybrid import HybridRetriever
from campuspilot.retrieval.vector import INDEX_NAME, VectorIndex
from eval_colloquial import DEFAULT_SNAPSHOT, embed_all, evaluate, load_cases

SHOWN = grounding.SHOWN


def measure(cases, results) -> dict[str, object]:
    ans = [c for c in cases if legacy_behavior(c) in {"answer", "partial"}]
    ref = [c for c in cases if legacy_behavior(c) in {"refuse", "clarify"}]
    out: dict[str, object] = {
        "n_answerable": len(ans),
        "n_explicit_refusal_or_clarification": len(ref),
        "n_unlabeled": sum(legacy_behavior(c) == "unlabeled" for c in cases),
        "answer_refusal_correctness": "UNASSESSED_RETRIEVAL_POLICY_ONLY",
    }
    for name, refused in (
        ("before", lambda c: not results[c["id"]].hits),
        (
            "after",
            lambda c: grounding.assess(c["question"], results[c["id"]]).decision == "insufficient",
        ),
    ):
        rr = [c for c in ref if refused(c)]
        fr = [c for c in ans if refused(c)]
        out[name] = {
            "insufficient_policy_recall": f"{len(rr)}/{len(ref)}"
            + (f" ({len(rr) / len(ref):.1%})" if ref else ""),
            "false_insufficient_policy": f"{len(fr)}/{len(ans)}"
            + (f" ({len(fr) / len(ans):.1%})" if ans else ""),
            "missed_refusals": [c["question"] for c in ref if not refused(c)],
            "false_refusals": [c["question"] for c in ans if refused(c)],
        }
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", type=Path, nargs="+", required=True)
    p.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT)
    p.add_argument("--sweep", action="store_true", help="threshold sweep (dev only)")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    s = Settings.from_env()
    snap = KnowledgeSnapshot.model_validate_json((a.snapshot_dir / "snapshot.json").read_bytes())
    index = VectorIndex.load(a.snapshot_dir / INDEX_NAME, snap, s.embedding_model)
    cases = [c for f in a.cases for c in load_cases(f)]
    vectors = embed_all([c["question"] for c in cases], s)
    retriever = HybridRetriever(snap, mode="hybrid", index=index)
    results = {
        c["id"]: retriever.search_channels(
            c["question"],
            filters_for(c["question"], ConversationContext()),
            SHOWN,
            query_vector=vectors[c["question"]],
        )
        for c in cases
    }
    ranking, _ = evaluate(cases, snap, index, vectors, ["hybrid"])
    report: dict[str, object] = {
        "cases_files": [str(f) for f in a.cases],
        "knowledge_version": snap.version,
        "policy": grounding.POLICY_VERSION,
        "thresholds": {
            "strong_similarity": grounding.STRONG_SIMILARITY,
            "floor_similarity": grounding.FLOOR_SIMILARITY,
            "agree_rank": grounding.AGREE_RANK,
            "shown": SHOWN,
        },
        "refusal": measure(cases, results),
        "hybrid_ranking": ranking["hybrid"],
    }
    if a.sweep:
        rows = []
        saved = (grounding.STRONG_SIMILARITY, grounding.FLOOR_SIMILARITY, grounding.AGREE_RANK)
        for strong in (0.55, 0.58, 0.60, 0.62, 0.65):
            for floor in (0.48, 0.50, 0.52, 0.54, 0.56, 0.58):
                for agree in (1, 3, 5):
                    if floor > strong:
                        continue
                    grounding.STRONG_SIMILARITY, grounding.FLOOR_SIMILARITY = strong, floor
                    grounding.AGREE_RANK = agree
                    m = measure(cases, results)["after"]
                    rows.append(
                        [
                            strong,
                            floor,
                            agree,
                            m["insufficient_policy_recall"],
                            m["false_insufficient_policy"],
                        ]
                    )
        grounding.STRONG_SIMILARITY, grounding.FLOOR_SIMILARITY, grounding.AGREE_RANK = saved
        report["sweep"] = rows
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if a.output:
        a.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
