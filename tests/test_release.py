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
from campuspilot.knowledge_release import embed_candidate, write_candidate
from campuspilot.rag import SnapshotStore
from test_snapshot_fallback import synthetic_snapshot

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
        "data/cdut/rag/approved-20991231/raw/package/unbound.json": "SYNTHETIC unbound raw",
        "data/cdut/rag/packages/approved-20991231/chunks.jsonl": "",
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    bundle = root / "data/cdut/rag/approved-20991231"
    (bundle / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "files_sha256": {"snapshot.json": R.sha256((bundle / "snapshot.json").read_bytes())},
    }))
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
    prefix = "data/cdut/rag/approved-20261011/"
    manifest = json.loads((ROOT / prefix / "manifest.json").read_bytes())
    required_raw = {prefix + n for n in manifest["files_sha256"] if n.startswith("raw/")}
    assert {n for n in files if "/raw/" in n} == required_raw
    assert not any(n.startswith("data/cdut/rag/packages/") or "__pycache__" in n for n in files)
    with pytest.raises(ValueError, match="bundle"):
        R.collect(ROOT, "../etc")


def test_knowledge_bundle_archive_cold_starts_with_bound_raw_and_vector(tmp_path: Path) -> None:
    root, bundle_name = fake_root(tmp_path), "approved-20991230"
    bundle = root / "data/cdut/rag" / bundle_name
    snapshot = synthetic_snapshot("release-contract")
    raw = {
        "APPROVAL_RECORD.json": b'{"SYNTHETIC": "approval fixture"}',
        "package/guide.txt": b"SYNTHETIC approved source body",
    }
    write_candidate(bundle, snapshot, raw)
    embed_candidate(bundle, lambda texts: [[1.0, 0.0] for _ in texts], "SYNTHETIC-vector", 2)
    (bundle / "raw/unbound.txt").write_bytes(b"SYNTHETIC unbound material")
    output = tmp_path / "SYNTHETIC-knowledge-release.tar.gz"
    R.build(root, output, bundle_name)
    _, files = R.read_archive(output.read_bytes())
    unpacked = tmp_path / "unpacked"
    for name, body in files.items():
        target = unpacked / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    store = SnapshotStore(unpacked / "data/cdut/rag", retrieval_mode="hybrid",
                          embedding_model="SYNTHETIC-vector", bundled=bundle_name)
    retriever = store.acquire()
    assert retriever is not None and retriever.snapshot == snapshot
    assert retriever.index is not None and not store.load_error and not store.index_error
    assert retriever.index.model == "SYNTHETIC-vector" and retriever.index.dimensions == 2
    for name, body in raw.items():
        assert files[f"data/cdut/rag/{bundle_name}/raw/{name}"] == body
    assert f"data/cdut/rag/{bundle_name}/raw/unbound.txt" not in files


@pytest.mark.parametrize("name", [
    "../outside.txt", "/outside.txt", "raw\\outside.txt", "raw/C:outside.txt",
    "raw//outside.txt", "raw/./outside.txt", "raw/../outside.txt", "",
])
def test_knowledge_manifest_unsafe_paths_are_rejected(tmp_path: Path, name: str) -> None:
    root = fake_root(tmp_path)
    manifest_path = root / "data/cdut/rag/approved-20991231/manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files_sha256"][name] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="knowledge"):
        R.collect(root, "approved-20991231")


@pytest.mark.parametrize("fault", ["missing", "mismatch", "invalid_hash"])
def test_knowledge_manifest_missing_or_invalid_bound_raw_is_rejected(
    tmp_path: Path, fault: str,
) -> None:
    root = fake_root(tmp_path)
    bundle = root / "data/cdut/rag/approved-20991231"
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    name = "raw/SYNTHETIC-required.txt"
    if fault != "missing":
        (bundle / name).write_bytes(b"SYNTHETIC source")
    manifest["files_sha256"][name] = "invalid" if fault == "invalid_hash" else "0" * 64
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / "must-not-exist.tar.gz"
    with pytest.raises(ValueError, match="knowledge"):
        R.build(root, output, "approved-20991231")
    assert not output.exists()


@pytest.mark.parametrize("manifest", [
    [], {}, {"schema_version": 2, "files_sha256": {"snapshot.json": "0" * 64}},
    {"schema_version": 1, "files_sha256": []},
    {"schema_version": 1, "files_sha256": {}},
])
def test_knowledge_incomplete_manifest_is_rejected(tmp_path: Path, manifest: object) -> None:
    root = fake_root(tmp_path)
    (root / "data/cdut/rag/approved-20991231/manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="knowledge"):
        R.collect(root, "approved-20991231")


@pytest.mark.parametrize("linked", ["manifest", "raw_file", "raw_directory", "bundle"])
def test_knowledge_bundle_symlinks_are_rejected(tmp_path: Path, linked: str) -> None:
    root = fake_root(tmp_path)
    bundle = root / "data/cdut/rag/approved-20991231"
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    raw = bundle / "raw/SYNTHETIC-required.txt"
    raw.write_bytes(b"SYNTHETIC approved body")
    manifest["files_sha256"]["raw/SYNTHETIC-required.txt"] = R.sha256(raw.read_bytes())
    manifest_path.write_text(json.dumps(manifest))
    target = {
        "manifest": manifest_path, "raw_file": raw,
        "raw_directory": raw.parent, "bundle": bundle,
    }[linked]
    saved = tmp_path / f"SYNTHETIC-{linked}"
    target.rename(saved)
    target.symlink_to(saved, target_is_directory=saved.is_dir())
    with pytest.raises(ValueError, match="knowledge"):
        R.collect(root, "approved-20991231")


def test_knowledge_bound_raw_keeps_release_file_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = fake_root(tmp_path)
    bundle = root / "data/cdut/rag/approved-20991231"
    body = b"SYNTHETIC required raw " * 200
    (bundle / "raw/SYNTHETIC-large.txt").write_bytes(body)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files_sha256"]["raw/SYNTHETIC-large.txt"] = R.sha256(body)
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(R, "MAX_FILE", 4096)
    with pytest.raises(ValueError, match="file too large"):
        R.collect(root, "approved-20991231")


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
    tree = ast.parse(program, feature_version=(3, 12))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in sys.stdlib_module_names for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None and node.module.split(".")[0] in sys.stdlib_module_names
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
