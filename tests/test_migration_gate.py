"""Synthetic release evidence exercises gates; it is never campus acceptance evidence."""

import json
from pathlib import Path
from typing import Any

import pytest
from campuspilot.migration_eval import load_cases
from campuspilot.rag import canonical, digest
from campuspilot.release_gate import approved_rules, assess, runtime_hashes

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64


def evidence() -> dict[str, Any]:
    cases = load_cases(ROOT / "evaluation/runtime-migration")
    hashes = runtime_hashes(ROOT)
    golden = digest((ROOT / "evaluation/runtime-migration/cases.jsonl").read_bytes())
    config = {"base_url": "https://example.com/v1", "model": "SYNTHETIC test model"}
    faults = (
        "dify_disconnected",
        "model_timeout",
        "jev_timeout",
        "publication_interrupted",
        "rollback",
        "historical_misuse",
        "ambiguity",
        "context_pollution",
        "session_isolation",
        "unknown_citation",
        "cards",
        "teacher",
        "maps",
        "mobile",
        "permissions",
    )
    qa = {
        "status": "PASS",
        "reviewer": "SYNTHETIC TEST REVIEWER",
        "environment": "SYNTHETIC TEST ENVIRONMENT",
        "tested_at": "2026-10-10T00:00:00Z",
        "tested_files_sha256": hashes,
        "golden_sha256": golden,
        "model_configuration": config,
        "answers_sha256": SHA,
        "baseline_sha256": SHA,
        "performance_sha256": SHA,
        "shadow_sha256": SHA,
        "case_reviews": {
            c.case_id: {
                "pass": True,
                "critical_fact_error": False,
                "required_premise_missing": False,
                "unsupported_assertion": False,
            }
            for c in cases
        },
        "baseline_case_pass": {c.case_id: True for c in cases if c.group.startswith("legacy_")},
        "approved_direct_rules": ["teacher", "service"],
        "boundary_checks": dict.fromkeys(faults, "PASS"),
        "dify_network_blocked": True,
    }
    return {
        "baseline": {
            "published_baseline": "LOCKED",
            "workflow_receipt": {
                "export_kind": "published",
                "verified_against_publish_record": True,
            },
            "published_dsl_sha256": SHA,
            "knowledge_snapshot_sha256": SHA,
            "production_files_sha256": {"SYNTHETIC.py": SHA},
        },
        "baseline_sha256": SHA,
        "independent_qa": qa,
        "api_answers_sha256": SHA,
        "api_answers": {
            "mode": "api_live",
            "stage": "phase2",
            "golden_sha256": golden,
            "tested_files_sha256": hashes,
            "environment": qa["environment"],
            "model_configuration": config,
            "cases": [
                {"case_id": c.case_id, "response": {"request_id": "SYNTHETIC request"}}
                for c in cases
            ],
        },
        "shadow_sha256": SHA,
        "shadow": {
            "mode": "live_adapters",
            "stage": "phase2",
            "golden_sha256": golden,
            "budget": {"calls": 240, "charged_usd": "0.01"},
            "cases": [{"case_id": c.case_id, "jev_shadow": {"status": "ok"}} for c in cases],
        },
        "performance_sha256": SHA,
        "performance": {
            "scope": "complete_api",
            "concurrency": 2,
            "cold_start_verified": True,
            "same_deployment_environment": True,
            "environment": qa["environment"],
            "tested_files_sha256": hashes,
            "golden_sha256": golden,
            "paths": {
                name: {t: {"valid_samples": 100, "p95_ms": ms} for t in ("warm", "cold")}
                for name, ms in (("simple", 100), ("rag", 1000), ("dify_simple", 300))
            },
        },
    }


def test_complete_synthetic_gate_binds_model_and_files(tmp_path: Path) -> None:
    result = assess(ROOT, evidence(), "phase2")
    assert result["release_gate"] == "PASS" and not result["blockers"]
    assert result["model_configuration"] == evidence()["api_answers"]["model_configuration"]
    path = tmp_path / "gate.json"
    path.write_bytes(canonical(result))
    assert approved_rules(path, ROOT) == {"teacher", "service"}
    result["tested_files_sha256"] = {}
    path.write_bytes(canonical(result))
    with pytest.raises(ValueError):
        approved_rules(path, ROOT)


@pytest.mark.parametrize(
    "fault",
    (
        "offline",
        "partial_shadow",
        "all_shadow_failed",
        "critical_fact",
        "wrong_model",
        "unlocked_baseline",
        "stale_files",
        "no_network_block",
        "incomplete_api",
        "budget",
        "nan_timing",
        "negative_budget",
        "untyped_baseline_comparison",
    ),
)
def test_gate_never_promotes_missing_or_bad_evidence(fault: str) -> None:
    documents = evidence()
    if fault == "offline":
        documents["performance"]["scope"] = "offline_complete_API"
    elif fault == "partial_shadow":
        documents["shadow"]["cases"].pop()
    elif fault == "all_shadow_failed":
        for case in documents["shadow"]["cases"]:
            case["jev_shadow"]["status"] = "unknown"
    elif fault == "critical_fact":
        documents["independent_qa"]["case_reviews"]["cp-001"]["critical_fact_error"] = True
    elif fault == "wrong_model":
        documents["independent_qa"]["model_configuration"] = {}
    elif fault == "unlocked_baseline":
        documents["baseline"]["workflow_receipt"]["export_kind"] = "draft"
    elif fault == "stale_files":
        documents["independent_qa"]["tested_files_sha256"] = {}
    elif fault == "no_network_block":
        documents["independent_qa"]["dify_network_blocked"] = False
    elif fault == "incomplete_api":
        documents["api_answers"]["cases"].pop()
    elif fault == "nan_timing":
        documents["performance"]["paths"]["simple"]["warm"]["p95_ms"] = float("nan")
    elif fault == "negative_budget":
        documents["shadow"]["budget"]["charged_usd"] = "-0.1"
    elif fault == "untyped_baseline_comparison":
        documents["independent_qa"]["baseline_case_pass"]["cp-001"] = "PASS"
    else:
        documents["shadow"]["budget"]["charged_usd"] = "5.01"
    result = assess(ROOT, json.loads(canonical(documents)), "phase2")
    assert result["release_gate"] == "FAIL"
    assert result["approved_direct_rules"] == [] and result["blockers"]
