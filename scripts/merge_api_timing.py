"""Merge independent timing runs without dropping invalid samples or missing paths."""

import argparse
import json
from pathlib import Path

from campuspilot.knowledge_release import atomic_write
from campuspilot.rag import canonical, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--reuse-frozen-dify-baseline",
        action="store_true",
        help="Reuse original Dify timings only when artifact/env/baseline are unchanged",
    )
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Output exists")
        reports = [json.loads(path.read_bytes()) for path in args.input]
        keys = ("stage", "environment", "tested_files_sha256", "golden_sha256", "baseline_sha256")
        first = next((r for r in reports if set(r.get("paths", {})) != {"dify_simple"}), reports[0])
        paths = {}
        cold = []
        for report in reports:
            if (
                report.get("scope") != "complete_api"
                or report.get("concurrency") != 2
                or any(
                    report.get(key) != first.get(key)
                    for key in keys
                    if not (
                        key == "stage"
                        and args.reuse_frozen_dify_baseline
                        and set(report.get("paths", {})) == {"dify_simple"}
                    )
                )
            ):
                raise ValueError("Measurements belong to different artifacts or environments")
            for name, temperatures in report["paths"].items():
                for temperature, result in temperatures.items():
                    if temperature in paths.setdefault(name, {}):
                        raise ValueError("Duplicate path temperature; preserve raw measurements")
                    paths[name][temperature] = result
                    if temperature == "cold":
                        cold.append(report.get("cold_start_verified") is True)
        result = {
            **{key: first[key] for key in keys},
            "schema_version": 1,
            "scope": "complete_api",
            "concurrency": 2,
            "paths": paths,
            "cold_start_verified": bool(cold) and all(cold),
            "same_deployment_environment": all(
                r.get("same_deployment_environment") is True for r in reports
            ),
            "input_sha256": [digest(path.read_bytes()) for path in args.input],
            "release_gate": "NOT_EVALUATED",
        }
        atomic_write(args.output, canonical(result))
        print("Timing evidence merged; missing paths and thresholds remain release gates.")
    except OSError, ValueError, KeyError, TypeError:
        parser.exit(2, "Incompatible or invalid measurements; no performance success claimed.\n")


if __name__ == "__main__":
    main()
