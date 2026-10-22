"""Collect real Agent answers with an external confirmed-free model profile; never score."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from campuspilot.knowledge_answer_eval import CollectionError, collect_answers, load_free_config
from campuspilot.knowledge_evaluation import QualityCase, validate_suite

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, required=True, help="Repository-external free-only JSON"
    )
    parser.add_argument("--snapshot", type=Path, required=True, help="Candidate snapshot.json")
    parser.add_argument("--directory", type=Path, default=ROOT / "data/cdut")
    parser.add_argument(
        "--cases", type=Path, default=ROOT / "evaluation/knowledge-quality-20261017/cases.jsonl"
    )
    parser.add_argument("--split", choices=("development", "holdout", "all"), default="development")
    parser.add_argument(
        "--limit", type=int, help="First run requires --limit 2; omit later for full split"
    )
    parser.add_argument(
        "--query-vectors", type=Path, help="Local cache; never calls an embed provider"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Observation JSONL; reuse to resume"
    )
    args = parser.parse_args()
    try:
        config = load_free_config(args.config, ROOT)
        cases = [
            QualityCase.model_validate_json(line)
            for line in args.cases.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        validate_suite(cases, require_full=True)
        report = asyncio.run(
            collect_answers(
                cases,
                config=config,
                release=args.snapshot.parent,
                directory=args.directory,
                output=args.output,
                split=args.split,
                limit=args.limit,
                query_vectors=args.query_vectors,
            )
        )
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
    except Exception:
        raise SystemExit("answer_collection_input_or_local_io_invalid") from None
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] == "blocked":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
