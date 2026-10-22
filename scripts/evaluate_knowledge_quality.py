"""Offline knowledge evidence evaluation; never initializes a provider or spends credits."""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from campuspilot.knowledge_evaluation import (
    AnswerReview,
    Observation,
    QualityCase,
    evaluate_quality,
    fingerprint,
    normalized,
    sha256,
    validate_suite,
)
from campuspilot.rag import KnowledgeSnapshot, RetrievalFilters
from campuspilot.retrieval.hybrid import HybridRetriever

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "evaluation/knowledge-quality-20261017/cases.jsonl"


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def check_raw_anchors(cases: list[QualityCase]) -> dict[str, Any]:
    checked, draft, invalid = [], [], []
    for case in cases:
        for anchor in case.evidence:
            if anchor.check_status == "draft":
                draft.append(anchor.evidence_id)
                continue
            path = (ROOT / str(anchor.raw_file)).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                invalid.append(anchor.evidence_id)
                continue
            body = path.read_bytes()
            if sha256(body) != anchor.raw_sha256 or normalized(anchor.quote) not in normalized(
                body.decode("utf-8", errors="replace")
            ):
                invalid.append(anchor.evidence_id)
                continue
            checked.append(anchor.evidence_id)
    return {"checked": len(checked), "draft": len(draft), "invalid": invalid}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--observations", type=Path)
    p.add_argument("--reviews", type=Path)
    p.add_argument(
        "--split",
        choices=("development", "holdout", "all"),
        default="development",
        help="Default leaves holdout untouched; use all only for frozen final comparison",
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--required-checks-passed",
        action="store_true",
        help="Record only after the required regression suite actually passed",
    )
    p.add_argument("--require-gate", action="store_true", help="Exit 2 unless acceptance passes")
    args = p.parse_args()
    cases = [QualityCase.model_validate(row) for row in read_rows(args.cases)]
    validate_suite(cases, require_full=True)
    snapshot = KnowledgeSnapshot.model_validate_json(args.snapshot.read_bytes())
    anchors = check_raw_anchors(cases)
    if anchors["invalid"]:
        raise SystemExit(f"raw evidence binding invalid: {anchors['invalid']}")
    if args.observations:
        observations = [Observation.model_validate(row) for row in read_rows(args.observations)]
    else:
        retriever = HybridRetriever(snapshot, mode="lexical")
        observations = []
        for case in cases:
            if args.split != "all" and case.split != args.split:
                continue
            started = time.perf_counter()
            filters_args: dict[str, Any] = {
                "today": date.fromisoformat(str(case.today)),
                "audience": case.audience,
                "academic_year": case.academic_year,
            }
            if "campus" in RetrievalFilters.model_fields:
                filters_args["campus"] = case.campus or "chengdu"
            hits = retriever.search(case.question, RetrievalFilters(**filters_args), 20)
            observations.append(
                Observation(
                    case_id=case.case_id,
                    case_sha256=fingerprint(case.model_dump(mode="json")),
                    knowledge_version=snapshot.version,
                    ranked_chunk_ids=tuple(h.chunk.chunk_id for h in hits),
                    shown_chunk_ids=tuple(h.chunk.chunk_id for h in hits[:4]),
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
    reviews = (
        [AnswerReview.model_validate(row) for row in read_rows(args.reviews)]
        if args.reviews
        else []
    )
    report = evaluate_quality(
        cases,
        snapshot,
        observations,
        reviews,
        required_checks_passed=args.required_checks_passed,
        raw_anchors_validated=not anchors["invalid"] and not anchors["draft"],
    )
    report["raw_anchor_audit"] = anchors
    report["observed_split"] = args.split
    report["snapshot_file_sha256"] = sha256(args.snapshot.read_bytes())
    report["limitations"] = [
        "Lexical-only default is an offline baseline; no BGE-M3 provider calls were made.",
        "No answer text means answer and citation support are unassessed.",
        "Draft labels are diagnostic only and cannot establish release acceptance.",
        "Source and issue groups are disjoint across splits; semantic leakage still needs review.",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    observation_path = args.output.with_suffix(".observations.jsonl")
    observation_path.write_text(
        "".join(o.model_dump_json() + "\n" for o in observations), encoding="utf-8"
    )
    template = [
        AnswerReview(case_id=o.case_id, observation_sha256=fingerprint(o.model_dump(mode="json")))
        for o in observations
    ]
    args.output.with_suffix(".review-template.jsonl").write_text(
        "".join(r.model_dump_json() + "\n" for r in template), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "per_case"}, ensure_ascii=False, indent=2
        )
    )
    if args.require_gate and not report["release_gate"]["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
