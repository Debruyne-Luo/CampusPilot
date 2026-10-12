"""Lock a workspace or an operator-verified published baseline; never use a draft as published."""

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml
from campuspilot.knowledge_release import atomic_write
from campuspilot.rag import canonical, digest

ROOT = Path(__file__).resolve().parents[1]


def validate_published(dsl: bytes, receipt: dict[str, object]) -> None:
    if (
        receipt.get("export_kind") != "published"
        or receipt.get("verified_against_publish_record") is not True
    ):
        raise ValueError("Published version verification required")
    if not all(
        receipt.get(k) for k in ("app_id", "workflow_id", "published_version", "observed_at")
    ):
        raise ValueError("Missing publish record identifiers")
    if receipt.get("dsl_sha256") != digest(dsl):
        raise ValueError("Published DSL receipt checksum mismatch")
    try:
        value = yaml.safe_load(dsl)
    except yaml.YAMLError:
        raise ValueError("Invalid redacted workflow YAML") from None
    if not isinstance(value, dict) or not isinstance(value.get("workflow"), dict):
        raise ValueError("Workflow graph missing")
    workflow = value["workflow"]
    graph = workflow.get("graph")
    if (
        not isinstance(graph, dict)
        or not isinstance(graph.get("nodes"), list)
        or not graph["nodes"]
    ):
        raise ValueError("Workflow graph missing")
    for variable in workflow.get("environment_variables", []):
        if variable.get("value_type") == "secret" and variable.get("value"):
            raise ValueError("Remove secret environment values before locking")
    for node in graph["nodes"]:
        headers = node.get("data", {}).get("headers", "")
        redacted = re.sub(r"Bearer\s+\{\{[^{}\r\n]+\}\}", "", str(headers))
        if re.search(r"Bearer\s+\S+", redacted):
            raise ValueError("Remove inline tool credentials before locking")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workspace-only", action="store_true")
    parser.add_argument("--published-dsl", type=Path)
    parser.add_argument("--published-receipt", type=Path)
    parser.add_argument("--knowledge-snapshot", type=Path)
    parser.add_argument("--production-manifest", type=Path)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Baseline output already exists")
        names = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
        )
        files = {
            n: digest((ROOT / n).read_bytes())
            for n in names.decode().split("\0")
            if n and (ROOT / n).is_file()
        }
        manifest: dict[str, object] = {
            "schema_version": 1,
            "captured_at": datetime.now(UTC).isoformat(),
            "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip(),
            "working_tree_status": subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT
            ).decode(),
            "files_sha256": files,
            "published_baseline": "NOT_CAPTURED",
        }
        if not args.workspace_only:
            paths = (
                args.published_dsl,
                args.published_receipt,
                args.knowledge_snapshot,
                args.production_manifest,
            )
            if any(p is None for p in paths):
                raise ValueError("Published workflow, knowledge and production bytes are required")
            assert (
                args.published_dsl
                and args.published_receipt
                and args.knowledge_snapshot
                and args.production_manifest
            )
            dsl = args.published_dsl.read_bytes()
            receipt = json.loads(args.published_receipt.read_bytes())
            validate_published(dsl, receipt)
            raw = json.loads(args.knowledge_snapshot.read_bytes())
            if not raw.get("datasets"):
                raise ValueError("Empty published knowledge snapshot")
            production = json.loads(args.production_manifest.read_bytes())
            if production.get("verified_live_bytes") is not True or not production.get(
                "files_sha256"
            ):
                raise ValueError("Live backend byte verification required")
            manifest.update(
                {
                    "published_baseline": "LOCKED",
                    "workflow_receipt": receipt,
                    "published_dsl_sha256": digest(dsl),
                    "knowledge_snapshot_sha256": digest(canonical(raw)),
                    "production_manifest_sha256": digest(canonical(production)),
                    "production_files_sha256": production["files_sha256"],
                }
            )
        atomic_write(args.output, canonical(manifest))
        print(f"BASELINE {manifest['published_baseline']}; {len(files)} workspace files hashed")
    except OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError:
        parser.exit(2, "Baseline could not be locked; no published baseline claimed.\n")


if __name__ == "__main__":
    main()
