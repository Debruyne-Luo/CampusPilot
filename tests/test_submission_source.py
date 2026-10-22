"""Submission exports are the reviewed commit, with no local promotional experiments."""

import json
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.package_release import committed_source


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def repository(tmp_path: Path) -> Path:
    root = tmp_path / "SYNTHETIC-repository"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "SYNTHETIC fixture")
    git(root, "config", "user.email", "synthetic@example.invalid")
    (root / "README.md").write_text("SYNTHETIC committed source", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "SYNTHETIC initial source")
    return root


def test_submission_source_uses_commit_and_excludes_untracked_materials(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "README.md").write_text("SYNTHETIC uncommitted edit", encoding="utf-8")
    (root / "宣传片").mkdir()
    (root / "宣传片/experiment.mp4").write_bytes(b"SYNTHETIC experimental video")
    target = tmp_path / "source.zip"
    manifest = committed_source(root, target)
    with ZipFile(target) as archive:
        assert archive.read("README.md") == b"SYNTHETIC committed source"
        assert set(archive.namelist()) == {"README.md", "SOURCE_MANIFEST.json"}
        assert json.loads(archive.read("SOURCE_MANIFEST.json")) == manifest


def test_submission_source_refuses_accidentally_committed_promotional_materials(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path)
    (root / "宣传片").mkdir()
    (root / "宣传片/experiment.mp4").write_bytes(b"SYNTHETIC experimental video")
    git(root, "add", ".")
    git(root, "commit", "-m", "SYNTHETIC forbidden material")
    with pytest.raises(ValueError, match="Promotional experiments"):
        committed_source(root, tmp_path / "forbidden.zip")
    assert not (tmp_path / "forbidden.zip").exists()
