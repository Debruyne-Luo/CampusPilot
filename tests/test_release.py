"""Whole-package release: manifest/sha256, atomic switch, health-check rollback (no SSH)."""

import ast
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> ModuleType:
    sys.path.insert(0, str(ROOT / "deploy"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "deploy" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R: Any = load("_release")


def fake_root(tmp: Path, marker: str = "1") -> Path:
    root = tmp / f"src-{marker}"
    for name, text in {
        "backend/src/campuspilot/__init__.py": marker,
        "backend/src/campuspilot/web_assets/v2/index.html": "<html></html>",
        "backend/src/campuspilot/web_assets/v2/main.mjs": "export {}",
        "backend/src/campuspilot/__pycache__/x.pyc": "junk",
        "pyproject.toml": "[project]",
        "data/cdut/places.json": "[]",
        "data/cdut/rag/bootstrap.json": "{}",
        "data/cdut/rag/approved-20991231/snapshot.json": "{}",
        "data/cdut/rag/approved-20991231/raw/package/secret.json": "{}",
        "data/cdut/rag/packages/approved-20991231/chunks.jsonl": "",
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def archive(tmp: Path, marker: str = "1") -> bytes:
    out = tmp / f"rel-{marker}.tar.gz"
    if out.exists():
        return out.read_bytes()
    R.build(fake_root(tmp, marker), out, "approved-20991231")
    return out.read_bytes()


class Service:
    def __init__(self, *healthy: bool) -> None:
        self.answers = list(healthy)
        self.restarts = 0

    def restart(self) -> None:
        self.restarts += 1

    def health(self) -> bool:
        return self.answers.pop(0)


def test_real_repo_package_ships_whole_package_v2_and_bundle() -> None:
    files = R.collect(ROOT, "approved-20261011")
    assert "backend/src/campuspilot/web_assets/v2/main.mjs" in files
    assert "backend/src/campuspilot/agent/executor.py" in files
    assert "data/cdut/rag/approved-20261011/vectors.sqlite" in files
    assert not any("/raw/" in n or "/packages/" in n or "__pycache__" in n for n in files)
    with pytest.raises(ValueError, match="bundle"):
        R.collect(ROOT, "../etc")


def test_manifest_covers_every_file_and_tampering_is_rejected(tmp_path: Path) -> None:
    data = archive(tmp_path)
    manifest, files = R.read_archive(data)
    assert set(manifest["files"]) == set(files)
    assert "data/cdut/rag/packages/approved-20991231/chunks.jsonl" not in files
    tampered = io.BytesIO()
    with (
        tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as src,
        tarfile.open(fileobj=tampered, mode="w:gz") as dst,
    ):
        for m in src.getmembers():
            body = src.extractfile(m).read()  # type: ignore[union-attr]
            if m.name == "pyproject.toml":
                body, m.size = b"evil", 4
            dst.addfile(m, io.BytesIO(body))
    with pytest.raises(ValueError, match="Checksum"):
        R.read_archive(tampered.getvalue())


def test_unsafe_member_is_rejected() -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("../etc/passwd")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="Unsafe"):
        R.read_archive(buf.getvalue())


def test_healthy_release_switches_atomically_and_reinstall_is_noop(tmp_path: Path) -> None:
    base, svc = tmp_path / "opt", Service(True)
    out = R.install(base, archive(tmp_path), restart=svc.restart, health=svc.health)
    current = base / "current"
    assert out["status"] == "RELEASED" and current.is_symlink()
    assert current.resolve().name == out["version"]
    assert (current / "backend/src/campuspilot/web_assets/v2/main.mjs").exists()
    again = R.install(base, archive(tmp_path), restart=svc.restart, health=svc.health)
    assert again["status"] == "UNCHANGED" and svc.restarts == 1


def test_failed_health_check_rolls_back_to_previous_release(tmp_path: Path) -> None:
    base = tmp_path / "opt"
    first = R.install(base, archive(tmp_path, "1"), restart=lambda: None, health=lambda: True)
    svc = Service(False, True)
    with pytest.raises(RuntimeError, match="rolled_back"):
        R.install(base, archive(tmp_path, "2"), restart=svc.restart, health=svc.health)
    assert (base / "current").resolve().name == first["version"]
    assert svc.restarts == 2  # new release, then the restored one
    log = [json.loads(x) for x in (base / "deploy-log.jsonl").read_text().splitlines()]
    assert log[-1]["event"] == "rolled_back" and log[-1]["restored_healthy"] is True
    assert len([p for p in (base / "releases").iterdir()]) == 2  # failed tree kept


def test_legacy_directory_layout_is_migrated_and_used_for_rollback(tmp_path: Path) -> None:
    base = tmp_path / "opt"
    (base / "current").mkdir(parents=True)
    (base / "current" / "OLD").write_text("legacy")
    with pytest.raises(RuntimeError, match="rolled_back"):
        R.install(base, archive(tmp_path), restart=lambda: None, health=Service(False, True).health)
    current = base / "current"
    assert current.is_symlink() and (current / "OLD").read_text() == "legacy"


def test_first_release_failure_without_previous_reports_it(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no_previous"):
        R.install(tmp_path / "opt", archive(tmp_path), restart=lambda: None, health=lambda: False)


def test_old_releases_are_pruned_but_current_and_previous_kept(tmp_path: Path) -> None:
    base = tmp_path / "opt"
    versions = [
        R.install(base, archive(tmp_path, str(i)), restart=lambda: None, health=lambda: True)[
            "version"
        ]
        for i in range(4)
    ]
    R.install(base, archive(tmp_path, "9"), restart=lambda: None, health=lambda: True, keep=2)
    kept = {p.name for p in (base / "releases").iterdir()}
    assert versions[-1] in kept and len(kept) == 2


def test_remote_program_is_python312_and_carries_no_secrets(tmp_path: Path) -> None:
    publisher: Any = load("publish_release")
    program = publisher.remote_program(archive(tmp_path))
    ast.parse(program, feature_version=(3, 12))
    assert "install(Path('/opt/campuspilot')" in program and "API_KEY" not in program


def test_versioned_assets_get_immutable_cache_headers() -> None:
    from campuspilot.app.factory import asset_hash, create_web_app
    from fastapi.testclient import TestClient

    version = asset_hash()
    with TestClient(create_web_app(data_dir=ROOT / "data/cdut", asset_version="auto")) as client:
        shell = client.get("/")
        assert f'src="/assets/v-{version}/v2/main.mjs"' in shell.text
        assert shell.headers["cache-control"] == "no-cache"
        asset = client.get(f"/assets/v-{version}/v2/main.mjs")
        assert asset.status_code == 200
        assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert client.get("/assets/v2/main.mjs").headers["cache-control"] == "no-cache"
    with pytest.raises(ValueError, match="asset version"):
        create_web_app(data_dir=ROOT / "data/cdut", asset_version="../x")


def test_health_probe_sends_public_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / "campuspilot.env"
    env.write_text('PUBLIC_ORIGIN="https://campus.example"\nOTHER=1\n')
    assert R.public_host(env) == "campus.example"
    seen: list[str] = []

    class Ok:
        status = 200

    def fake(req: Any, timeout: float) -> Ok:
        seen.append(req.get_header("Host"))
        return Ok()

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert R.http_health(host="campus.example", attempts=1, wait=0)
    assert seen == ["campus.example"] * 3
