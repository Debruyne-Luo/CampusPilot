"""Offline diagnostics or explicitly configured, budgeted public fixture evaluation."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import cast

from campuspilot.chat_runtime import Mode
from campuspilot.evaluation_budget import BudgetExhausted, EvaluationBudget
from campuspilot.knowledge_release import atomic_write
from campuspilot.migration_config import generation_model, price, shadow_client
from campuspilot.migration_eval import BudgetedModel, evaluate, load_cases
from campuspilot.rag import canonical, digest

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("phase1", "phase2"), required=True)
    parser.add_argument("--split", choices=("development", "holdout", "all"), default="development")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "evaluation/runtime-migration")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/cdut")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Only public fixed fixtures; keys and known prices required",
    )
    parser.add_argument("--baseline", type=Path)
    parser.add_argument(
        "--shadow-only",
        action="store_true",
        help="Compare Jev against fixed labels; API quality is collected separately",
    )
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Report output exists; preserve previous measurements")
        checkpoint = args.output.with_suffix(".partial.json")
        if checkpoint.exists():
            raise ValueError("Prior checkpoint exists; use a new output path")
        cases = load_cases(args.fixtures)
        selected = tuple(c for c in cases if args.split == "all" or c.split == args.split)
        budget = None
        model = None
        jev = None
        if args.live:
            if (
                not args.baseline
                or json.loads(args.baseline.read_bytes()).get("published_baseline") != "LOCKED"
            ):
                raise ValueError("A locked published baseline is required before live comparison")
            root = Path(os.environ["CAMPUSPILOT_EVALUATION_DIR"])
            if not root.is_absolute() or root.resolve().is_relative_to(ROOT):
                raise ValueError("Evaluation ledger must be outside the repository")
            # Resolve all credentials/prices before the first external request.
            jev = shadow_client()
            budget = EvaluationBudget(root, args.stage)
            if not args.shadow_only:
                provider = generation_model()
                if provider is None:
                    raise ValueError("Configure the production generation model")
                model_price = price("CAMPUSPILOT_MODEL")
                model = BudgetedModel(provider, model_price, budget)
        result = asyncio.run(
            evaluate(
                args.data_dir,
                selected,
                cast(Mode, args.stage),
                model=model,
                jev=jev,
                budget=budget,
                progress=lambda report: atomic_write(checkpoint, canonical(report)),
            )
        )
        result["golden_sha256"] = digest((args.fixtures / "cases.jsonl").read_bytes())
        result["baseline_sha256"] = digest(args.baseline.read_bytes()) if args.baseline else None
        atomic_write(args.output, canonical(result))
        print(
            f"{len(result['cases'])} public cases evaluated; {result['mode']}; "
            "release gate NOT_EVALUATED"
        )
        if result["budget_exhausted"]:
            raise BudgetExhausted
    except BudgetExhausted:
        parser.exit(
            3,
            "Stage stopped at its $5 / 1,000 external call ceiling; "
            "acceptance standard unchanged.\n",
        )
    except OSError, ValueError, KeyError, TypeError:
        parser.exit(
            2, "Evaluation configuration or fixed artifact validation failed; no success claimed.\n"
        )


if __name__ == "__main__":
    main()
