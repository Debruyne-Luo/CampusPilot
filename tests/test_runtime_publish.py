"""Exercise the existing updater with disposable files and synthetic private configuration."""

import hashlib
import json
import os
import runpy
import stat
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = "backend/src/campuspilot/web.py"
NEW = "data/cdut/rag/versions/SYNTHETIC-new/snapshot.json"


def transaction(tmp_path: Path) -> tuple[dict[str, Any], Path, Path]:
    loaded = runpy.run_path(str(ROOT / "deploy/update_routes.py"))
    engine = loaded["apply"].__globals__
    publisher = runpy.run_path(str(ROOT / "deploy/publish_runtime.py"))
    target = tmp_path / "release"
    (target / WEB).parent.mkdir(parents=True)
    (target / WEB).write_bytes(b"# SYNTHETIC original\n")
    environment = tmp_path / "synthetic.env"
    environment.write_bytes(b"SYNTHETIC_OLD_SETTING=1\n")
    engine["FILES"] = (WEB, NEW)
    namespace: dict[str, Any] = {
        "Path": Path,
        "hashlib": hashlib,
        "json": json,
        "ns": engine,
        "settings": {
            "mode": "phase2",
            "base_url": "https://example.com/v1",
            "model": "SYNTHETIC test model",
            "api_key": "SYNTHETIC test credential",
        },
        "expected_env_hash": hashlib.sha256(environment.read_bytes()).hexdigest(),
    }
    code = publisher["TRANSACTION"].replace(
        "Path('/etc/campuspilot/campuspilot.env')", f"Path({str(environment)!r})"
    )
    exec(compile(code, "synthetic runtime transaction", "exec"), namespace)
    return engine, target, environment


def test_runtime_failure_restores_new_files_and_environment_together(tmp_path: Path) -> None:
    engine, target, environment = transaction(tmp_path)
    old = environment.read_bytes()
    calls: list[bool] = []

    def verify(restored: bool = False) -> None:
        calls.append(restored)
        if not restored:
            # This also checks actual newline encoding in the remote transaction.
            lines = environment.read_text().splitlines()
            assert len(lines) == 7 and (target / NEW).exists()
            assert 'CAMPUSPILOT_RUNTIME_MODE="phase2"' in lines
            raise RuntimeError("SYNTHETIC failed health check")
        assert environment.read_bytes() == old
        assert not (target / NEW).exists()

    records = {
        WEB: (engine["digest"]((target / WEB).read_bytes()), b"# SYNTHETIC updated\n"),
        NEW: (None, b'{"SYNTHETIC": true}'),
    }
    with pytest.raises(engine["UpdateFailure"], match="update_failed_restored"):
        engine["apply"](target, records, tmp_path / "backups", verify)
    assert calls == [False, True]
    assert (target / WEB).read_bytes() == b"# SYNTHETIC original\n"
    backups = list((tmp_path / "backups").glob("environment-*/environment.before"))
    assert len(backups) == 1 and backups[0].read_bytes() == old


def test_environment_backup_failure_prevents_source_mutation(tmp_path: Path) -> None:
    engine, target, environment = transaction(tmp_path)
    original = engine["write_atomic"]

    def fail_backup(path: Path, data: bytes, metadata: Any) -> None:
        if path.name == "environment.before":
            raise OSError("SYNTHETIC backup failure")
        original(path, data, metadata)

    engine["write_atomic"] = fail_backup
    records = {WEB: (engine["digest"]((target / WEB).read_bytes()), b"# SYNTHETIC updated")}
    with pytest.raises(OSError):
        engine["apply"](target, records, tmp_path / "backups", lambda **_: None)
    assert (target / WEB).read_bytes() == b"# SYNTHETIC original\n"
    assert environment.read_bytes() == b"SYNTHETIC_OLD_SETTING=1\n"


def test_new_source_directories_inherit_existing_read_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = runpy.run_path(str(ROOT / "deploy/update_routes.py"))
    target = tmp_path / "target"
    target.mkdir()
    original = os.chmod
    calls: list[tuple[Path, int]] = []

    def mode(path: str | Path, value: int) -> None:
        calls.append((Path(path), value))
        original(path, value)

    monkeypatch.setattr(os, "chmod", mode)
    engine["ensure_public_parent"](target / "data/rag/version", target)
    assert len(calls) == 3
    assert all(value == stat.S_IMODE(target.stat().st_mode) for _, value in calls)
    with pytest.raises(engine["UpdateFailure"], match="unsafe"):
        engine["ensure_public_parent"](tmp_path / "outside", target)
