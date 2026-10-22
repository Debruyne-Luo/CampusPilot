import hashlib
import json
from pathlib import Path

import pytest
from campuspilot.harness_profile import HarnessProfile

from scripts.freeze_agent_profile import freeze


def review_fixture(root: Path, *, improvement: bool = True) -> tuple[Path, Path, Path, Path]:
    profile = HarnessProfile.create("synthetic-candidate", "SYNTHETIC strategy")
    candidate, reviews = root / "candidate.json", root / "reviews.json"
    candidate.write_text(profile.model_dump_json(), encoding="utf-8")
    rows = []
    for i in range(12):
        ident = f"synthetic-{i}"
        hashes = {}
        for arm in ("baseline", "candidate"):
            path = root / "observations" / arm / ident / "result.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"answer": "SYNTHETIC answer", "arm": arm}))
            hashes[arm] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(
            {
                "task_id": ident,
                "reviewed": True,
                "source_notes": "SYNTHETIC source",
                "critical_errors": 0,
                "baseline_pass": i > 0,
                "candidate_pass": i > 0 or improvement,
                "observation_sha256": hashes,
            }
        )
    reviews.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_sha256": profile.sha256,
                "split": "holdout",
                "reviews": rows,
            }
        )
    )
    return candidate, reviews, root / "observations", root / "frozen.json"


def test_adoption_requires_measured_improvement_and_unchanged_observations(tmp_path: Path) -> None:
    args = review_fixture(tmp_path)
    assert freeze(*args)["adopted"] is True
    observation = args[2] / "candidate/synthetic-0/result.json"
    observation.write_text('{"answer":"SYNTHETIC modified"}')
    with pytest.raises(ValueError, match="Observation changed"):
        freeze(*args)


def test_no_gain_or_critical_error_does_not_publish_profile(tmp_path: Path) -> None:
    args = review_fixture(tmp_path, improvement=False)
    assert freeze(*args)["adopted"] is False
    assert not args[3].exists()
    data = json.loads(args[1].read_bytes())
    data["reviews"][0]["critical_errors"] = 1
    data["reviews"][0]["candidate_pass"] = True
    args[1].write_text(json.dumps(data))
    assert freeze(*args)["adopted"] is False
    assert not args[3].exists()


def test_unreviewed_or_missing_task_cannot_certify_profile(tmp_path: Path) -> None:
    args = review_fixture(tmp_path)
    data = json.loads(args[1].read_bytes())
    data["reviews"].pop()
    args[1].write_text(json.dumps(data))
    with pytest.raises(ValueError, match="twelve"):
        freeze(*args)


def test_development_freeze_is_distinct_from_production_adoption(tmp_path: Path) -> None:
    args = review_fixture(tmp_path, improvement=False)
    data = json.loads(args[1].read_bytes())
    data["split"] = "development"
    args[1].write_text(json.dumps(data))
    verdict = freeze(*args, evaluation_only=True)
    assert verdict["frozen_for_evaluation"] is True
    assert verdict["adopted"] is False
    assert args[3].exists()
    assert freeze(*args)["adopted"] is False
