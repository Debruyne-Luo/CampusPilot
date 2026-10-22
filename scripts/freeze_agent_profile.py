"""Validate independent answer reviews before freezing/adopting an experiment profile."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from campuspilot.harness_profile import HarnessProfile
from campuspilot.knowledge_release import atomic_write


def freeze(
    candidate: Path,
    reviews: Path,
    observations: Path,
    destination: Path,
    *,
    evaluation_only: bool = False,
) -> dict[str, object]:
    profile = HarnessProfile.load(candidate)
    report = json.loads(reviews.read_bytes())
    if (
        report.get("schema_version") != 1
        or report.get("profile_sha256") != profile.sha256
        or report.get("split") not in {"development", "holdout"}
    ):
        raise ValueError("Review is not bound to this profile and split")
    rows = report.get("reviews", [])
    if len(rows) != 12 or len({r["task_id"] for r in rows}) != 12:
        raise ValueError("All twelve tasks require independent reviews")
    if evaluation_only and report["split"] != "development":
        raise ValueError("Evaluation freeze requires development reviews")
    for review in rows:
        if (
            review.get("reviewed") is not True
            or not review.get("source_notes")
            or type(review.get("critical_errors")) is not int
            or review["critical_errors"] < 0
            or type(review.get("baseline_pass")) is not bool
            or type(review.get("candidate_pass")) is not bool
            or len(review.get("observation_sha256", {})) != 2
        ):
            raise ValueError("Missing source-based answer review")
        for arm, digest in review["observation_sha256"].items():
            path = observations / arm / review["task_id"] / "result.json"
            if not path.resolve().is_relative_to(observations.resolve()):
                raise ValueError("Invalid observation path")
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("Observation changed after review")
    baseline = sum(row["baseline_pass"] is True for row in rows)
    candidate_pass = sum(row["candidate_pass"] is True for row in rows)
    critical = sum(int(row["critical_errors"]) for row in rows)
    improvement = candidate_pass > baseline or report.get("efficiency_improved") is True
    eligible = critical == 0 and candidate_pass >= baseline
    adopted = not evaluation_only and report["split"] == "holdout" and eligible and improvement
    frozen_for_evaluation = evaluation_only and eligible
    verdict = {
        "schema_version": 1,
        "profile_sha256": profile.sha256,
        "split": report["split"],
        "baseline_pass": baseline,
        "candidate_pass": candidate_pass,
        "critical_errors": critical,
        "adopted": adopted,
        "frozen_for_evaluation": frozen_for_evaluation,
        "review_sha256": hashlib.sha256(reviews.read_bytes()).hexdigest(),
    }
    if adopted or frozen_for_evaluation:
        atomic_write(destination, profile.model_dump_json(indent=2).encode())
    atomic_write(destination.with_suffix(".verdict.json"), json.dumps(verdict, indent=2).encode())
    return verdict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate", "reviews", "observations", "destination"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument(
        "--evaluation-only",
        action="store_true",
        help="Freeze a reviewed development candidate; never adopt it in production",
    )
    args = parser.parse_args()
    verdict = freeze(
        args.candidate,
        args.reviews,
        args.observations,
        args.destination,
        evaluation_only=args.evaluation_only,
    )
    print(json.dumps(verdict))
    return 0 if verdict["adopted"] or verdict["frozen_for_evaluation"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
