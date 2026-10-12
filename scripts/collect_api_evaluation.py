"""Explicit live complete-API collection; fixed public cases and shared budget only."""

import argparse
import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

import httpx
from campuspilot.api_evaluation import PublicAPICollector
from campuspilot.evaluation_budget import EvaluationBudget
from campuspilot.knowledge_release import atomic_write
from campuspilot.migration_config import price
from campuspilot.migration_eval import load_cases
from campuspilot.rag import canonical, digest
from campuspilot.release_gate import runtime_hashes

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--stage", choices=("phase1", "phase2"), required=True)
    parser.add_argument("--mode", choices=("answers", "timing"), required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--environment-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-input-tokens", type=int, required=True)
    parser.add_argument("--max-output-tokens", type=int, required=True)
    parser.add_argument("--max-inferences-per-request", type=int, required=True)
    parser.add_argument(
        "--price-prefix",
        choices=("CAMPUSPILOT_MODEL", "DIFY_EVALUATION"),
        default="CAMPUSPILOT_MODEL",
    )
    parser.add_argument("--split", choices=("development", "holdout", "all"), default="development")
    parser.add_argument("--case-id")
    parser.add_argument("--path", choices=("simple", "rag", "dify_simple"))
    parser.add_argument("--temperature", choices=("warm", "cold"), default="warm")
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument(
        "--restart-argv-file",
        type=Path,
        help="Explicit operator command for the independent test service only",
    )
    args = parser.parse_args()
    try:
        if args.output.exists() or args.output.with_suffix(".partial.json").exists():
            raise ValueError("Use a new output path")
        baseline = json.loads(args.baseline.read_bytes())
        if baseline.get("published_baseline") != "LOCKED":
            raise ValueError("Published baseline must be locked before paid evaluation")
        artifact = json.loads(args.artifact_manifest.read_bytes())
        hashes = runtime_hashes(ROOT)
        if artifact["files_sha256"] != hashes:
            raise ValueError("Candidate source changed")
        receipt = json.loads(args.environment_receipt.read_bytes())
        if not receipt.get("environment") or not receipt.get("model_configuration"):
            raise ValueError("Independent test environment and model receipt required")
        ledger = Path(os.environ["CAMPUSPILOT_EVALUATION_DIR"])
        if not ledger.is_absolute() or ledger.resolve().is_relative_to(ROOT):
            raise ValueError("Ledger must be outside the repository")
        budget = EvaluationBudget(ledger, args.stage)
        runtime_mode = "legacy" if args.path == "dify_simple" else args.stage
        collector = PublicAPICollector(
            args.endpoint,
            runtime_mode,
            budget,
            price(args.price_prefix),
            args.max_input_tokens,
            args.max_output_tokens,
            args.max_inferences_per_request,
        )
        cases = load_cases(ROOT / "evaluation/runtime-migration")
        if args.mode == "answers":
            selected = tuple(c for c in cases if args.split == "all" or c.split == args.split)
            result = asyncio.run(
                collector.answers(
                    selected,
                    progress=lambda rows: atomic_write(
                        args.output.with_suffix(".partial.json"),
                        canonical(
                            {
                                "cases": rows,
                                "collection_complete": False,
                                "release_gate": "NOT_EVALUATED",
                            }
                        ),
                    ),
                )
            )
        else:
            case = next(c for c in cases if c.case_id == args.case_id)
            if case.messages or args.path is None or not 100 <= args.samples <= 1000:
                raise ValueError("Timing needs one fixed single-turn case and >=100 samples")
            restarts: list[dict[str, object]] = []
            restart = None
            if args.temperature == "cold":
                if not args.restart_argv_file:
                    raise ValueError("Cold measurement requires a real test-process restart")
                command = json.loads(args.restart_argv_file.read_bytes())
                if (
                    not isinstance(command, list)
                    or not command
                    or any(not isinstance(arg, str) or not arg for arg in command)
                ):
                    raise ValueError("Restart command must be an explicit argv array")

                def restart() -> None:
                    started = time.time()
                    subprocess.run(
                        command, check=True, capture_output=True, timeout=45, shell=False
                    )
                    restarts.append(
                        {
                            "started_at_unix": started,
                            "completed_at_unix": time.time(),
                            "command_sha256": digest(canonical(command)),
                        }
                    )
                    # A successful supervisor restart need not mean HTTP is ready yet.
                    with httpx.Client(
                        base_url=args.endpoint, timeout=0.5, trust_env=False
                    ) as probe:
                        for _ in range(40):
                            try:
                                if probe.get("/healthz").json() == {"status": "ready"}:
                                    return
                            except httpx.HTTPError, ValueError:
                                pass
                            time.sleep(0.25)
                    raise ValueError("Independent test service did not become ready")

            timing = asyncio.run(
                collector.timing(case.question, args.samples, cold_restart=restart)
            )
            result = {
                "schema_version": 1,
                "scope": "complete_api",
                "stage": args.stage,
                "concurrency": 2,
                "paths": {args.path: {args.temperature: timing}},
                "cold_start_verified": bool(restarts) and len(restarts) * 2 >= args.samples,
                "cold_restart_receipts": restarts,
                "same_deployment_environment": receipt.get("same_deployment_environment") is True,
                "case_id": case.case_id,
                "budget": budget.report(),
                "budget_exhausted": timing["budget_exhausted"],
                "release_gate": "NOT_EVALUATED",
            }
        result.update(
            {
                "environment": receipt["environment"],
                "model_configuration": receipt["model_configuration"],
                "tested_files_sha256": hashes,
                "golden_sha256": digest(
                    (ROOT / "evaluation/runtime-migration/cases.jsonl").read_bytes()
                ),
                "baseline_sha256": digest(args.baseline.read_bytes()),
                "environment_receipt_sha256": digest(args.environment_receipt.read_bytes()),
            }
        )
        atomic_write(args.output, canonical(result))
        print("Complete API evidence saved; independent judgments remain pending.")
        if result.get("budget_exhausted"):
            parser.exit(3, "Shared stage budget reached; partial evidence retained.\n")
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        StopIteration,
        subprocess.SubprocessError,
        httpx.HTTPError,
    ):
        parser.exit(2, "API evaluation configuration or measurement failed; gate stays closed.\n")


if __name__ == "__main__":
    main()
