"""Exercise knowledge publication/rollback only in an isolated temporary store.

No network, model, embedding or real pointer writes occur. This verifies the RAG release
mechanism and whole-package guard; it does not approve the candidate or deploy a release.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from campuspilot.knowledge_release import (
    atomic_write,
    current_version,
    publish,
    read_candidate,
    rollback,
)
from campuspilot.rag import SnapshotStore, canonical, digest

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "data/cdut/rag"
RAG_CANDIDATE = ROOT / "output/knowledge-rebuild-20261017/recollected-final"
JOINT_CANDIDATE = KNOWLEDGE / "candidates/rebuild-20261017"
REPORT = ROOT / "output/knowledge-rebuild-20261017/rollback-drill.json"


def protected_files(root: Path) -> dict[str, str | None]:
    paths = {root / name for name in ("current.json", "last_good.json", "bootstrap.json")}
    for pattern in ("versions/*/snapshot.json", "approved-*/snapshot.json"):
        paths.update(root.glob(pattern))
    version = current_version(root)
    if version:
        paths.update(root / "versions" / version / name
                     for name in ("manifest.json", "vectors.sqlite"))
    return {p.relative_to(root).as_posix(): digest(p.read_bytes()) if p.exists() else None
            for p in sorted(paths)}


def clone_candidate(source: Path, target: Path) -> str:
    """Copy only checked manifest entries into the explicitly created temporary directory."""
    snapshot = read_candidate(source)
    manifest = json.loads((source / "manifest.json").read_bytes())
    for name in (*manifest["files_sha256"], "manifest.json"):
        atomic_write(target / name, (source / name).read_bytes())
    if read_candidate(target) != snapshot:
        raise ValueError("cloned_candidate_mismatch")
    return snapshot.version


def run(
    *, knowledge: Path = KNOWLEDGE, rag_candidate: Path = RAG_CANDIDATE,
    joint_candidate: Path = JOINT_CANDIDATE, report: Path = REPORT,
) -> dict[str, Any]:
    knowledge, rag_candidate, joint_candidate = (
        p.resolve() for p in (knowledge, rag_candidate, joint_candidate)
    )
    if any(report.resolve().is_relative_to(p) for p in (knowledge, rag_candidate, joint_candidate)):
        raise ValueError("report_cannot_overwrite_inputs")
    old_version = current_version(knowledge)
    if old_version is None:
        raise ValueError("real_active_baseline_required")
    old_candidate = knowledge / "versions" / old_version
    before = protected_files(knowledge)
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": passed, **details})
        if not passed:
            raise ValueError("rollback_drill_failed:" + name)
        if protected_files(knowledge) != before:
            raise ValueError("protected_knowledge_changed:" + name)

    with tempfile.TemporaryDirectory(prefix="campuspilot-rollback-drill-") as temporary:
        scratch = Path(temporary).resolve()
        if scratch.parent != Path(tempfile.gettempdir()).resolve():
            raise ValueError("unexpected_temporary_directory")
        isolated = scratch / "store"
        check("temporary_store_isolated", not isolated.is_relative_to(knowledge))
        old = clone_candidate(old_candidate, scratch / "old")
        new = clone_candidate(rag_candidate, scratch / "new")
        joint = clone_candidate(joint_candidate, scratch / "joint")
        joint_manifest = json.loads((scratch / "joint/manifest.json").read_bytes())
        check("joint_binding_present", bool(joint_manifest.get("directory_binding")), version=joint)
        check("distinct_old_new_versions", old == old_version and new != old, old=old, new=new)

        check("publish_old", publish(scratch / "old", isolated, None) == old)
        pointer_before = (isolated / "current.json").read_bytes()
        retriever_store = SnapshotStore(isolated)
        pinned = retriever_store.acquire()
        check("old_loaded", pinned is not None and pinned.snapshot.version == old)
        with retriever_store.pin(pinned):
            check("publish_new", publish(scratch / "new", isolated, old) == new)
            held = retriever_store.acquire()
            check("inflight_request_keeps_old", held is not None and held.snapshot.version == old)
        fresh = retriever_store.acquire()
        check("next_request_loads_new", fresh is not None and fresh.snapshot.version == new)

        active_new = (isolated / "current.json").read_bytes()
        try:
            publish(scratch / "old", isolated, old)
        except ValueError as exc:
            drift_rejected = str(exc) == "Published knowledge drifted; preview again"
        else:
            drift_rejected = False
        check("stale_expected_version_rejected", drift_rejected)
        check("rejected_publish_preserves_temporary_pointer",
              (isolated / "current.json").read_bytes() == active_new)

        try:
            publish(scratch / "joint", isolated, new)
        except ValueError as exc:
            joint_rejected = str(exc) == "Structured knowledge requires a whole-package release"
        else:
            joint_rejected = False
        check("joint_candidate_rejects_rag_only_publication", joint_rejected, version=joint)
        check("joint_rejection_preserves_temporary_pointer",
              (isolated / "current.json").read_bytes() == active_new)

        check("rollback_to_old", rollback(isolated, old, new) == old)
        restored = SnapshotStore(isolated).acquire()
        check("cold_request_loads_rolled_back_version",
              restored is not None and restored.snapshot.version == old)
        check("rollback_restores_exact_temporary_pointer",
              (isolated / "current.json").read_bytes() == pointer_before)
        last_good = json.loads((isolated / "last_good.json").read_bytes())
        check("rollback_retains_new_as_last_good", last_good["version"] == new)
        temporary_pointer_hashes = {
            "old": digest(pointer_before), "new": digest(active_new),
            "rolled_back": digest((isolated / "current.json").read_bytes()),
        }
    after = protected_files(knowledge)
    check("temporary_directory_cleaned_up", not scratch.exists())
    check("real_pointers_and_immutable_snapshots_unchanged", before == after)
    result: dict[str, Any] = {
        "schema_version": 1, "status": "passed", "performed_at": datetime.now(UTC).isoformat(),
        "exercise": "isolated_local_rag_publication_and_rollback",
        "old_version": old, "new_rag_version": new, "joint_version": joint,
        "checks": checks, "passed_checks": len(checks),
        "protected_files": {name: {"sha256_before": checksum, "sha256_after": after[name],
                                   "unchanged": checksum == after[name]}
                            for name, checksum in before.items()},
        "temporary_pointer_sha256": temporary_pointer_hashes,
        "temporary_store_removed": True, "real_pointer_written": False,
        "online_environment_accessed": False, "provider_calls": 0,
        "candidate_approved": False,
        "limitations": ["RAG mechanism exercised in lexical mode; no quality or vector acceptance",
                        "Joint directory/RAG release was intentionally rejected, not deployed"],
    }
    atomic_write(report, canonical(result))
    if protected_files(knowledge) != before:
        raise ValueError("protected_knowledge_changed_after_report")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rag-candidate", type=Path, default=RAG_CANDIDATE)
    parser.add_argument("--joint-candidate", type=Path, default=JOINT_CANDIDATE)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    result = run(rag_candidate=args.rag_candidate, joint_candidate=args.joint_candidate,
                 report=args.report)
    print(json.dumps({
        "status": result["status"], "passed_checks": result["passed_checks"],
        "old_version": result["old_version"], "new_rag_version": result["new_rag_version"],
        "joint_version": result["joint_version"], "report": str(args.report),
    }, indent=2))


if __name__ == "__main__":
    main()
