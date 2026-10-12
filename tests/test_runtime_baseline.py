"""Published receipts never accept drafts or inline credentials."""

import runpy
from pathlib import Path
from typing import Any

import pytest
from campuspilot.rag import digest

ROOT = Path(__file__).resolve().parents[1]
DSL = b"workflow:\n  graph:\n    nodes:\n      - data: {}\n"


def receipt() -> dict[str, Any]:
    return {
        "export_kind": "published",
        "verified_against_publish_record": True,
        "app_id": "SYNTHETIC",
        "workflow_id": "SYNTHETIC",
        "published_version": "SYNTHETIC",
        "observed_at": "2026-10-10T00:00:00Z",
        "dsl_sha256": digest(DSL),
    }


def test_draft_and_wrong_DSL_cannot_become_published_baseline() -> None:
    validate = runpy.run_path(str(ROOT / "scripts/lock_runtime_baseline.py"))["validate_published"]
    valid = receipt()
    validate(DSL, valid)
    valid["export_kind"] = "draft"
    with pytest.raises(ValueError):
        validate(DSL, valid)
    with pytest.raises(ValueError):
        validate(DSL + b"# SYNTHETIC changed", receipt())


def test_inline_credential_cannot_hide_beside_template_placeholder() -> None:
    validate = runpy.run_path(str(ROOT / "scripts/lock_runtime_baseline.py"))["validate_published"]
    value = DSL.replace(
        b"data: {}", b"data:\n          headers: 'Bearer SYNTHETIC-SECRET; X-Other: {{test}}'"
    )
    proof = receipt()
    proof["dsl_sha256"] = digest(value)
    with pytest.raises(ValueError, match="credentials"):
        validate(value, proof)
