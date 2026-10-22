"""Offline baseline checks cover complete active/rollback knowledge exports."""

import runpy
from pathlib import Path

from test_release import R, published_root

CHECK = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/check_live_baseline.py"))


def test_active_knowledge_baseline_covers_the_same_scope_as_the_release(tmp_path: Path) -> None:
    root, _ = published_root(tmp_path)
    manifest = R.build(root, tmp_path / "release.tar.gz", knowledge_current=True)
    result = CHECK["check"](root, manifest)
    assert result["matches_live_manifest"], result


def test_active_knowledge_baseline_rejects_unbound_runtime_additions(tmp_path: Path) -> None:
    root, _ = published_root(tmp_path)
    manifest = R.build(root, tmp_path / "release.tar.gz", knowledge_current=True)
    name = "backend/src/campuspilot/unexpected.py"
    (root / name).write_text("SYNTHETIC unbound module")
    result = CHECK["check"](root, manifest)
    assert not result["matches_live_manifest"]
    assert name in result["added"]
