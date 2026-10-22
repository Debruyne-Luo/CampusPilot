"""Local-only campaign CLI: smoke, real Harness² optimization, six-arm evaluation, export.

Run with the optional Linux CampusPilot interpreter. No public endpoint launches jobs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

from campuspilot.evaluation_budget import TokenPrice
from campuspilot.experiment_budget import CampaignBudget, ExperimentGateway, MeteredProvider
from campuspilot.harness_profile import HarnessProfile
from campuspilot.knowledge_release import atomic_write

ROOT = Path(__file__).resolve().parents[1]
PIN = "1cfe254e8d25b15f37048c3730134686abe60335"
TASKS = ROOT / "evaluation/agent-lab-20261020/tasks.json"
DEFAULT = ROOT / "output/harness-jev-20261020"


def identity() -> str:
    digest = hashlib.sha256()
    for base in [ROOT / "backend/src", ROOT / "scripts", ROOT / "integrations/harness2"]:
        for path in sorted(base.rglob("*.py")):
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    git = ["git"]
    pointer = ROOT / ".git"
    if os.name != "nt" and pointer.is_file():
        location = pointer.read_text().strip().removeprefix("gitdir: ")
        if len(location) > 2 and location[1] == ":":
            location = "/mnt/" + location[0].lower() + location[2:].replace("\\", "/")
            git.append("--git-dir=" + location)
    revision = subprocess.check_output(git + ["rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    return revision + "+" + digest.hexdigest()[:16]


def config_file(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    if path.is_relative_to(ROOT) or path.stat().st_size > 65536:
        raise ValueError("Experiment credentials configuration must stay outside the repository")
    raw = json.loads(path.read_bytes())
    if set(raw) != {"deepseek_key_file", "jev_key_file"}:
        raise ValueError("Configure only the two external key file paths")
    result: dict[str, Any] = {}
    for name, value in raw.items():
        p = Path(value).resolve(strict=True)
        if p.is_relative_to(ROOT) or p.stat().st_size > 8192:
            raise ValueError("Invalid external credential file")
        secret = p.read_text(encoding="utf-8-sig").strip()
        if not secret or any(ch.isspace() for ch in secret):
            raise ValueError("Expected one credential per file")
        result[name] = secret
    result["budget_dir"] = path.parent / "campaign-harness-jev-20261020"
    return result


def prepare(out: Path) -> dict[str, Any]:
    """Freeze current proven knowledge and directory bytes; never switch active pointers."""
    binding = out / "binding.json"
    if binding.exists():
        raw = dict(json.loads(binding.read_bytes()))
        if raw["code_identity"] != identity():
            raise ValueError("Code changed; choose a new output directory, same campaign ledger")
        return raw
    from campuspilot.rag import SnapshotStore

    code = identity()
    source = ROOT / "data/cdut"
    retriever = SnapshotStore(source / "rag", "lexical").acquire()
    if retriever is None:
        raise ValueError("No valid current knowledge snapshot")
    target = out / "frozen-data"
    target.mkdir(parents=True, exist_ok=True)
    for p in source.glob("*.json"):
        shutil.copy2(p, target / p.name)
    version = retriever.snapshot.version
    shutil.copytree(
        source / "rag/versions" / version, target / "rag/versions" / version, dirs_exist_ok=True
    )
    shutil.copy2(source / "rag/current.json", target / "rag/current.json")
    data = {
        "code_identity": code,
        "knowledge_version": retriever.snapshot.version,
        "model": "deepseek-flash",
        "jev_model": "typesafe/jev-1.13",
        "directory_hashes": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(target.glob("*.json"))
        },
        "tasks_sha256": hashlib.sha256(TASKS.read_bytes()).hexdigest(),
        "retrieval_mode": "lexical",
        "upstream_commit": PIN,
    }
    atomic_write(binding, json.dumps(data, indent=2).encode())
    return data


def worker(
    out: Path,
    gateway: ExperimentGateway,
    binding: dict[str, Any],
    task: dict[str, Any],
    arm: str,
    profile: HarnessProfile | None = None,
) -> dict[str, Any]:
    target = out / "observations" / arm / task["id"]
    result_path = target / "result.json"
    if result_path.exists():
        return dict(json.loads(result_path.read_bytes()))
    if (target / "started.json").exists():
        raise ValueError("Interrupted task outcome unknown; do not automatically redispatch")
    target.mkdir(parents=True, exist_ok=True)
    atomic_write(target / "started.json", json.dumps({"task": task["id"], "arm": arm}).encode())
    payload = {
        "question": task["question"],
        "data_dir": str(out / "frozen-data"),
        "knowledge_version": binding["knowledge_version"],
        "gateway": gateway.base_url,
        "gateway_token": gateway.token,
        "model": binding["model"],
        "jev_model": binding["jev_model"],
        "jev_routing": arm in {"routing", "jev", "combined"},
        "jev_evidence": arm in {"evidence", "jev", "combined"},
        "profile": profile.model_dump() if profile else None,
        "scratch": str(target / "scratch"),
    }
    before = gateway.budget.report()
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/harness_worker.py")],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=160,
        cwd=ROOT,
    )
    if completed.returncode:
        raise RuntimeError("Campus worker failed (no automatic replay)")
    observed = dict(json.loads(completed.stdout))
    if observed.get("directory_hashes") != binding["directory_hashes"]:
        raise ValueError("Experiment directory bytes changed during execution")
    observed["cost_upper_usd"] = new_request_cost(before, gateway.budget.report())
    observed["task_id"], observed["arm"] = task["id"], arm
    atomic_write(result_path, json.dumps(observed, ensure_ascii=False, indent=2).encode())
    if gateway.failure is not None:
        atomic_write(out / "stopped.json", json.dumps(gateway.failure, indent=2).encode())
        atomic_write(out / "budget-summary.json", json.dumps(gateway.budget.report()).encode())
        raise RuntimeError("Provider unavailable; saved partial result, no automatic replay")
    return observed


def new_request_cost(before: dict[str, Any], after: dict[str, Any]) -> str:
    """Attribute only new reservations; earlier delayed refunds cannot make a trial negative."""
    old = set(before.get("reservations", {}))
    return str(
        sum(
            (
                Decimal(str(value.get("actual_usd", value["maximum_usd"])))
                for key, value in after.get("reservations", {}).items()
                if key not in old
            ),
            Decimal(0),
        )
    )


def candidates(out: Path, source: Path | None = None) -> list[HarnessProfile]:
    """Import only completed compositions, keeping optimization provenance separate."""
    origin = (source or out).resolve()
    profiles: dict[str, HarnessProfile] = {}
    receipts = []
    for path in sorted((origin / "optimizer/runs").glob("*/*/summary.json")):
        summary = json.loads(path.read_bytes())
        if summary.get("status") != "ok":
            continue
        for selected in summary.get("selections", {}).values():
            run = Path(selected["chosen_run_dir"]).resolve()
            if not run.is_relative_to((origin / "optimizer/executions").resolve()):
                raise ValueError("Selected optimizer execution is outside its run")
            if not (run / "result.json").is_file():
                raise ValueError("Selected optimizer execution did not finish")
            raw = json.loads((run / "profile.json").read_bytes())
            if not raw:
                continue
            value = HarnessProfile.model_validate(raw)
            profiles[value.sha256] = value
            receipts.append(
                {
                    "profile_sha256": value.sha256,
                    "task_id": selected["task_id"],
                    "summary_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "execution_sha256": hashlib.sha256(
                        (run / "result.json").read_bytes()
                    ).hexdigest(),
                    "optimization_binding": json.loads((origin / "binding.json").read_bytes()),
                }
            )
    if not profiles or len(profiles) > 4:
        raise ValueError("Expected one to four completed optimizer candidates")
    receipt = out / "candidate-provenance.json"
    encoded = json.dumps(receipts, sort_keys=True, indent=2).encode()
    if receipt.exists() and receipt.read_bytes() != encoded:
        raise ValueError("Candidate provenance changed; use a new evaluation directory")
    atomic_write(receipt, encoded)
    for value in profiles.values():
        atomic_write(
            out / "candidate-profiles" / (value.sha256 + ".json"),
            value.model_dump_json(indent=2).encode(),
        )
    return list(profiles.values())


def export(
    out: Path, binding: dict[str, Any], budget: CampaignBudget, running: bool = False
) -> None:
    from campuspilot.lab_export import export_optimizer_run

    export_optimizer_run(
        out,
        ROOT / "evaluation/agent-lab-20261020/public",
        binding,
        json.loads(TASKS.read_bytes()),
        float(str(budget.report()["charged_usd"])),
        running,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "optimize", "development", "holdout", "export"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT)
    parser.add_argument(
        "--candidates-from",
        type=Path,
        help="Completed optimizer run; development only, preserves its identity",
    )
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.mode != "export" and (out / "stopped.json").exists():
        raise ValueError("This run stopped on a provider fault; inspect before starting a new run")
    config = config_file(args.config)
    budget = CampaignBudget(config["budget_dir"])
    binding = prepare(out)
    if hashlib.sha256(TASKS.read_bytes()).hexdigest() != binding["tasks_sha256"]:
        raise ValueError("Task suite changed")
    tasks = json.loads(TASKS.read_bytes())
    if args.mode == "export":
        export(out, binding, budget)
        return 0
    providers = {
        "/v1/chat/completions": MeteredProvider(
            "https://api.deepseek.com/chat/completions",
            "deepseek-flash",
            config["deepseek_key_file"],
            TokenPrice(Decimal("0.3"), Decimal("1.2")),
        ),
        "/v1/decisions": MeteredProvider(
            "https://openrouter.ai/api/alpha/decisions",
            "typesafe/jev-1.13",
            config["jev_key_file"],
            TokenPrice(Decimal("0.042"), Decimal(0)),
        ),
    }
    with ExperimentGateway(budget, providers) as gateway:
        if args.mode == "smoke":
            chosen = [t for t in tasks if t["split"] == "development"][:2]
            for task in chosen:
                result = worker(out, gateway, binding, task, "jev")
                print(
                    json.dumps(
                        {
                            "task": task["id"],
                            "status": result["body"]["result_status"],
                            "decisions": result["body"].get("decisions", []),
                            "charged_upper_usd": result["cost_upper_usd"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
        elif args.mode == "optimize":
            launch = {
                **binding,
                "data_dir": str(out / "frozen-data"),
                "gateway": gateway.base_url,
                "gateway_token": gateway.token,
                "tasks_file": str(TASKS),
                "run_dir": str(out / "optimizer"),
                "campus_python": sys.executable,
                "worker": str(ROOT / "scripts/harness_worker.py"),
                "workspace": str(ROOT),
            }
            finished = threading.Event()

            def progress() -> None:
                while not finished.wait(3):
                    export(out, binding, budget, running=True)

            monitor = threading.Thread(target=progress, daemon=True)
            monitor.start()
            try:
                optimized = subprocess.run(
                    [
                        str(ROOT / ".cache/harness-env/bin/python"),
                        str(ROOT / "integrations/harness2/run_optimizer.py"),
                    ],
                    input=json.dumps(launch),
                    text=True,
                    cwd=ROOT,
                    check=False,
                )
            finally:
                finished.set()
                monitor.join(timeout=5)
                export(out, binding, budget)
                if gateway.failure is not None:
                    atomic_write(out / "stopped.json", json.dumps(gateway.failure).encode())
                atomic_write(out / "budget-summary.json", json.dumps(budget.report()).encode())
            if optimized.returncode:
                return optimized.returncode
            if gateway.failure is not None:
                return 2
        else:
            frozen = out / "frozen-profile.json"
            if args.mode == "development":
                available = candidates(out, args.candidates_from)
                chosen = [t for t in tasks if t["split"] == "development"]
                for task in chosen:
                    worker(out, gateway, binding, task, "baseline")
                    for candidate in available:
                        worker(
                            out,
                            gateway,
                            binding,
                            task,
                            "candidate-" + candidate.sha256[:12],
                            candidate,
                        )
                    print("completed development", task["id"], flush=True)
                # Freeze only after explicit independent development reviews; no model
                # self-rating or last-task profile is silently selected.
                print("Development observations ready; review before freezing a profile.")
            else:
                if not frozen.exists():
                    raise ValueError("Independent development review must freeze a profile first")
                profile = HarnessProfile.load(frozen)
                chosen = [t for t in tasks if t["split"] == "holdout"]
                for task in chosen:
                    for arm in ("baseline", "routing", "evidence", "jev", "harness", "combined"):
                        worker(
                            out,
                            gateway,
                            binding,
                            task,
                            arm,
                            profile if arm in {"harness", "combined"} else None,
                        )
                    print("completed", task["id"], flush=True)
    atomic_write(out / "budget-summary.json", json.dumps(budget.report(), indent=2).encode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
