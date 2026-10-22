"""Campaign recovery and provenance never substitute probes for a finished composition."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from campuspilot.harness_profile import HarnessProfile

from scripts.run_agent_lab import candidates, new_request_cost, worker


def test_import_uses_completed_composition_and_retains_original_identity(tmp_path: Path) -> None:
    origin, evaluation = tmp_path / "original", tmp_path / "evaluation"
    run = origin / "optimizer/executions/seq/task/c1"
    run.mkdir(parents=True)
    profile = HarnessProfile.create("synthetic-composition", "SYNTHETIC guidance")
    (run / "profile.json").write_text(profile.model_dump_json())
    (run / "result.json").write_text('{"status":"SYNTHETIC finished"}')
    (origin / "binding.json").write_text('{"code_identity":"original-identity"}')
    summary = origin / "optimizer/runs/agg/task/summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(
        json.dumps(
            {
                "status": "ok",
                "selections": {"seq": {"task_id": "task", "chosen_run_dir": str(run)}},
            }
        )
    )
    unfinished = origin / "optimizer/executions/seq/unfinished/inv1"
    unfinished.mkdir(parents=True)
    (unfinished / "profile.json").write_text(HarnessProfile.create("unfinished").model_dump_json())

    assert candidates(evaluation, origin) == [profile]
    provenance = json.loads((evaluation / "candidate-provenance.json").read_bytes())
    assert provenance[0]["optimization_binding"]["code_identity"] == "original-identity"
    assert candidates(evaluation, origin) == [profile]
    (run / "result.json").write_text('{"status":"changed"}')
    with pytest.raises(ValueError, match="provenance changed"):
        candidates(evaluation, origin)


def test_no_completed_candidate_is_not_silently_baseline(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="completed"):
        candidates(tmp_path)


def test_delayed_refund_from_previous_trial_does_not_reduce_current_cost() -> None:
    before = {"reservations": {"previous": {"maximum_usd": "10"}}}
    after = {
        "reservations": {
            "previous": {"maximum_usd": "10", "actual_usd": "0.01"},
            "current": {"maximum_usd": "1", "actual_usd": "0.02"},
            "unknown": {"maximum_usd": "0.3"},
        }
    }
    assert new_request_cost(before, after) == "0.32"


def test_worker_preserves_result_and_stops_when_budget_is_exhausted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway: Any = SimpleNamespace(
        base_url="http://127.0.0.1:1",
        token="SYNTHETIC-token",
        failure={"reason": "campaign_budget_exhausted"},
        budget=SimpleNamespace(report=lambda: {"charged_usd": "20", "reservations": {}}),
    )
    monkeypatch.setattr(
        "scripts.run_agent_lab.subprocess.run",
        lambda *a, **k: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"directory_hashes": {}, "body": {"answer": "SYNTHETIC fallback"}}),
        ),
    )
    with pytest.raises(RuntimeError, match="saved partial result"):
        worker(
            tmp_path,
            gateway,
            {
                "model": "fixture",
                "jev_model": "fixture",
                "knowledge_version": "fixture",
                "directory_hashes": {},
            },
            {"id": "SYNTHETIC-task", "question": "SYNTHETIC public question"},
            "baseline",
        )
    assert (tmp_path / "observations/baseline/SYNTHETIC-task/result.json").exists()
    assert (
        json.loads((tmp_path / "stopped.json").read_bytes())["reason"]
        == "campaign_budget_exhausted"
    )


def test_interrupted_worker_is_not_automatically_replayed(tmp_path: Path) -> None:
    target = tmp_path / "observations/baseline/SYNTHETIC-task"
    target.mkdir(parents=True)
    (target / "started.json").write_text('{"status":"SYNTHETIC interrupted"}')
    unavailable: Any = None
    with pytest.raises(ValueError, match="outcome unknown"):
        worker(tmp_path, unavailable, {}, {"id": "SYNTHETIC-task"}, "baseline")
