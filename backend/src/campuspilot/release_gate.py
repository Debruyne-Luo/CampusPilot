"""Release evidence is bound to bytes, fixed cases and independent judgments."""

from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from campuspilot.migration_eval import load_cases
from campuspilot.rag import digest


def runtime_hashes(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for folder in ("backend/src", "data/cdut", "evaluation/runtime-migration"):
        for file in sorted((root / folder).rglob("*")):
            if (
                file.is_file()
                and "__pycache__" not in file.parts
                and file.suffix
                in {
                    ".py",
                    ".json",
                    ".jsonl",
                    ".csv",
                    ".txt",
                    ".md",
                    ".js",
                    ".css",
                    ".html",
                }
            ):
                result[file.relative_to(root).as_posix()] = digest(file.read_bytes())
    if not result:
        raise ValueError("Empty release artifact")
    return result


def valid_latency(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def assess(root: Path, documents: dict[str, Any], stage: str) -> dict[str, object]:
    cases = load_cases(root / "evaluation/runtime-migration")
    blockers: list[str] = []
    hashes = runtime_hashes(root)
    baseline = documents.get("baseline", {})
    qa = documents.get("independent_qa", {})
    api = documents.get("api_answers", {})
    shadow = documents.get("shadow", {})
    performance = documents.get("performance", {})
    golden = digest((root / "evaluation/runtime-migration/cases.jsonl").read_bytes())
    receipt = baseline.get("workflow_receipt", {})
    if (
        baseline.get("published_baseline") != "LOCKED"
        or receipt.get("export_kind") != "published"
        or receipt.get("verified_against_publish_record") is not True
        or not all(
            baseline.get(k)
            for k in (
                "published_dsl_sha256",
                "knowledge_snapshot_sha256",
                "production_files_sha256",
            )
        )
    ):
        blockers.append("current_published_baseline_not_locked")
    if qa.get("status") != "PASS" or not all(
        qa.get(k) for k in ("reviewer", "environment", "tested_at")
    ):
        blockers.append("independent_qa_not_passed")
    if qa.get("tested_files_sha256") != hashes or qa.get("golden_sha256") != golden:
        blockers.append("independent_qa_artifact_drift")
    if api.get("mode") != "api_live" or api.get("stage") != stage:
        blockers.append("complete_live_API_answers_missing")
    api_rows = api.get("cases", [])
    if (
        {row.get("case_id") for row in api_rows} != {c.case_id for c in cases}
        or len(api_rows) != 120
        or any(not row.get("response", {}).get("request_id") for row in api_rows)
        or api.get("tested_files_sha256") != hashes
        or api.get("golden_sha256") != golden
    ):
        blockers.append("complete_live_API_case_or_artifact_mismatch")
    configuration = api.get("model_configuration") or {}
    endpoint = urlsplit(str(configuration.get("base_url", "")))
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or not configuration.get("model")
        or qa.get("model_configuration") != configuration
        or api.get("environment") != qa.get("environment")
    ):
        blockers.append("tested_model_or_environment_not_bound")
    if not qa.get("answers_sha256") or qa.get("answers_sha256") != documents.get(
        "api_answers_sha256"
    ):
        blockers.append("independent_answer_reviews_not_bound")
    if not qa.get("baseline_sha256") or qa.get("baseline_sha256") != documents.get(
        "baseline_sha256"
    ):
        blockers.append("independent_baseline_review_not_bound")
    reviews = qa.get("case_reviews", {})
    expected = {c.case_id for c in cases}
    if set(reviews) != expected:
        blockers.append("independent_reviews_incomplete")
    passed = {k for k, review in reviews.items() if review.get("pass") is True}
    holdout = {c.case_id for c in cases if c.split == "holdout"}
    overall = len(passed & expected) / 120
    held = len(passed & holdout) / 40
    if overall < 0.95 or held < 0.95:
        blockers.append("quality_below_95_percent")
    for review in reviews.values():
        keys = ("critical_fact_error", "required_premise_missing", "unsupported_assertion")
        if any(review.get(k) is not False for k in keys):
            blockers.append("critical_fact_premise_or_unsupported_assertion")
            break
    original = {c.case_id for c in cases if c.group.startswith("legacy_")}
    before = qa.get("baseline_case_pass", {})
    if not original <= before.keys() or any(
        type(before[k]) is not bool or before[k] is True and k not in passed for k in original
    ):
        blockers.append("original_capability_regression_or_missing_comparison")
    if (
        shadow.get("mode") != "live_adapters"
        or shadow.get("stage") != stage
        or shadow.get("golden_sha256") != golden
    ):
        blockers.append("real_Jev_shadow_missing")
    shadow_rows = shadow.get("cases", [])
    if (
        len(shadow_rows) != 120
        or {r.get("case_id") for r in shadow_rows} != expected
        or any(r.get("jev_shadow", {}).get("status") == "NOT_RUN" for r in shadow_rows)
        or not any(r.get("jev_shadow", {}).get("status") == "ok" for r in shadow_rows)
    ):
        blockers.append("shadow_cases_missing")
    ledger = shadow.get("budget") or {}
    try:
        charged = Decimal(str(ledger.get("charged_usd", "6")))
        calls = ledger.get("calls")
        budget_valid = (
            type(calls) is int and 0 < calls <= 1000 and charged.is_finite() and 0 <= charged <= 5
        )
    except (ValueError, TypeError, ArithmeticError):
        budget_valid = False
    if not budget_valid:
        blockers.append("evaluation_budget_not_verified")
    if performance.get("scope") != "complete_api" or performance.get("concurrency") != 2:
        blockers.append("deployment_performance_not_verified")
    if (
        performance.get("environment") != qa.get("environment")
        or performance.get("tested_files_sha256") != hashes
        or performance.get("golden_sha256") != golden
    ):
        blockers.append("performance_artifact_or_environment_mismatch")
    if not qa.get("performance_sha256") or qa.get("performance_sha256") != documents.get(
        "performance_sha256"
    ):
        blockers.append("independent_performance_review_not_bound")
    if not qa.get("shadow_sha256") or qa.get("shadow_sha256") != documents.get("shadow_sha256"):
        blockers.append("independent_shadow_review_not_bound")
    measured = performance.get("paths", {})
    for name, maximum in (("simple", 2000), ("rag", 15000)):
        if name == "rag" and stage == "phase1":
            continue
        for temperature in ("warm", "cold"):
            path = measured.get(name, {}).get(temperature, {})
            if (
                path.get("valid_samples", 0) < 100
                or not valid_latency(path.get("p95_ms"))
                or path["p95_ms"] > maximum
            ):
                blockers.append(f"{name}_{temperature}_performance_gate")
    for temperature in ("warm", "cold"):
        new = measured.get("simple", {}).get(temperature, {}).get("p95_ms")
        old = measured.get("dify_simple", {}).get(temperature, {}).get("p95_ms")
        if (
            not valid_latency(old)
            or not valid_latency(new)
            or old <= 0
            or new > old * 0.5
            or measured.get("dify_simple", {}).get(temperature, {}).get("valid_samples", 0) < 100
        ):
            blockers.append(f"simple_{temperature}_speedup_comparison_missing_or_below_50_percent")
    if not performance.get("same_deployment_environment") or not performance.get(
        "cold_start_verified"
    ):
        blockers.append("cache_or_cold_start_environment_not_verified")
    faults = {
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
    }
    fault_results = qa.get("boundary_checks", {})
    if any(fault_results.get(k) != "PASS" for k in faults):
        blockers.append("boundary_or_compatibility_QA_missing")
    if stage == "phase2" and qa.get("dify_network_blocked") is not True:
        blockers.append("phase2_Dify_network_block_not_verified")
    return {
        "schema_version": 1,
        "stage": stage,
        "release_gate": "FAIL" if blockers else "PASS",
        "independent_qa": qa.get("status", "PENDING"),
        "overall_pass_rate": overall,
        "holdout_pass_rate": held,
        "blockers": blockers,
        "tested_files_sha256": hashes,
        "golden_sha256": golden,
        "baseline_sha256": documents.get("baseline_sha256"),
        "jev_shadow_sha256": documents.get("shadow_sha256"),
        "model_configuration": configuration,
        "approved_direct_rules": qa.get("approved_direct_rules", []) if not blockers else [],
    }


def approved_rules(path: Path, root: Path) -> frozenset[str]:
    report = json.loads(path.read_bytes())
    if report.get("release_gate") != "PASS" or report.get("independent_qa") != "PASS":
        raise ValueError("Direct rules need a passing independent release report")
    if report.get("tested_files_sha256") != runtime_hashes(root):
        raise ValueError("Direct response rules belong to different runtime bytes")
    if report.get("golden_sha256") != digest(
        (root / "evaluation/runtime-migration/cases.jsonl").read_bytes()
    ):
        raise ValueError("Direct response rules belong to different fixed cases")
    if not report.get("baseline_sha256") or not report.get("jev_shadow_sha256"):
        raise ValueError("Direct rules lack published baseline or real shadow evidence")
    rules = frozenset(report["approved_direct_rules"])
    if rules - {"teacher", "service"}:
        raise ValueError("Unknown direct response rule")
    return rules
