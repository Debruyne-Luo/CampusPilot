"""Whole-package releases: build locally, install remotely with an atomic switch.

Local side (`collect`, `build`) packs the entire campuspilot package (incl. web_assets/ and
web_assets/v2/), pyproject.toml/uv.lock and the selected data bundle into one tar.gz with a
MANIFEST.json of sha256 per file. Remote side (`install`) uses the standard library only and
runs on the VPS through `ssh ... python -`:

    /opt/campuspilot/releases/<version>/   immutable trees; older ones are the backup
    /opt/campuspilot/current -> releases/<version>   switched with one atomic rename
    /opt/campuspilot/venv/                 shared interpreter environment

If the service does not answer the health check after restart, `current` is switched back to
the previous release and the service restarted again; the failed tree is kept for inspection.
A legacy layout where `current` is a real directory is first moved to releases/legacy-<time>.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath

SCHEMA = 1
MANIFEST = "MANIFEST.json"
PACKAGE = "backend/src/campuspilot"
TOP_FILES = ("pyproject.toml", "uv.lock")
SKIP_PARTS = {"__pycache__", ".mypy_cache", ".pytest_cache"}
MAX_FILE = 25_000_000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _files_under(root: Path, rel: str) -> list[str]:
    base = root / rel
    return sorted(
        p.relative_to(root).as_posix()
        for p in base.rglob("*")
        if p.is_file() and not SKIP_PARTS & set(p.parts) and p.suffix not in {".pyc", ".pyo"}
    )


def _knowledge_bytes(directory: Path, name: str) -> bytes:
    if (
        not isinstance(name, str)
        or "\\" in name
        or ":" in name
        or any(part in {"", ".", ".."} for part in name.split("/"))
    ):
        raise ValueError("Unsafe knowledge bundle path")
    path = directory
    for part in name.split("/"):
        path = path / part
        if path.is_symlink():
            raise ValueError("Unsafe knowledge bundle symlink")
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Unsafe knowledge bundle path")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError("Missing or unreadable knowledge bundle file") from exc


def _knowledge_files(root: Path, bundle: str) -> dict[str, bytes]:
    directory = root / "data/cdut/rag" / bundle
    if (
        not bundle.startswith("approved-")
        or any(c in bundle for c in "/\\:")
        or not directory.is_dir()
    ):
        raise ValueError("Unknown knowledge bundle")
    if not directory.resolve().is_relative_to(root):
        raise ValueError("Unsafe knowledge bundle path")
    for parent in (directory, *directory.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("Unsafe knowledge bundle symlink")
    manifest_bytes = _knowledge_bytes(directory, "manifest.json")
    manifest = json.loads(manifest_bytes)
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or not isinstance(manifest.get("files_sha256"), dict)
        or "snapshot.json" not in manifest["files_sha256"]
    ):
        raise ValueError("Incomplete knowledge bundle manifest")
    prefix = directory.relative_to(root).as_posix() + "/"
    required: dict[str, bytes] = {}
    for name, checksum in manifest["files_sha256"].items():
        if (
            not isinstance(checksum, str)
            or len(checksum) != 64
            or any(c not in "0123456789abcdef" for c in checksum)
        ):
            raise ValueError("Invalid knowledge bundle checksum")
        data = _knowledge_bytes(directory, name)
        if sha256(data) != checksum:
            raise ValueError("Invalid knowledge bundle checksum")
        required[prefix + name] = data
    for name in _files_under(root, prefix):
        if "/raw/" not in name and name not in required:
            required[name] = (
                manifest_bytes if name == prefix + "manifest.json"
                else _knowledge_bytes(directory, name.removeprefix(prefix))
            )
    return required


def _published_knowledge_files(root: Path) -> dict[str, bytes]:
    """Freeze both pointer targets, including every manifest-bound original and directory."""
    rag = root / "data/cdut/rag"
    files: dict[str, bytes] = {}
    for pointer in ("current.json", "last_good.json"):
        raw_bytes = _knowledge_bytes(rag, pointer)
        raw = json.loads(raw_bytes)
        if not isinstance(raw, dict):
            raise ValueError("Invalid published knowledge reference")
        version = raw.get("version")
        if raw.get("kind", "published") != "published" or not isinstance(version, str) or not (
            re.fullmatch(r"kb-[a-f0-9]{16}", version)
        ):
            raise ValueError("Invalid published knowledge reference")
        directory = rag / "versions" / version
        for path in (rag, rag / "versions", directory):
            if path.is_symlink():
                raise ValueError("Unsafe knowledge bundle symlink")
        manifest_bytes = _knowledge_bytes(directory, "manifest.json")
        manifest = json.loads(manifest_bytes)
        if (
            not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or manifest.get("version") != version
            or not isinstance(manifest.get("files_sha256"), dict)
            or "snapshot.json" not in manifest["files_sha256"]
            or raw.get("manifest_sha256") != sha256(manifest_bytes)
        ):
            raise ValueError("Invalid published knowledge manifest")
        prefix = f"data/cdut/rag/versions/{version}/"
        for name, checksum in manifest["files_sha256"].items():
            if not isinstance(name, str) or not isinstance(checksum, str) or not (
                re.fullmatch(r"[a-f0-9]{64}", checksum)
            ):
                raise ValueError("Invalid knowledge bundle checksum")
            body = _knowledge_bytes(directory, name)
            if sha256(body) != checksum:
                raise ValueError("Invalid knowledge bundle checksum")
            files[prefix + name] = body
        if raw.get("sha256") != sha256(files[prefix + "snapshot.json"]):
            raise ValueError("Invalid published knowledge checksum")
        files[prefix + "manifest.json"] = manifest_bytes
        files["data/cdut/rag/" + pointer] = raw_bytes
    return files


def collect(root: Path, bundle: str = "", *, knowledge_current: bool = False) -> dict[str, bytes]:
    """Every file the service needs; data limited to directory JSON + the chosen knowledge."""
    root = root.resolve()
    if knowledge_current and bundle:
        raise ValueError("Knowledge current and legacy bundle are mutually exclusive")
    names = _files_under(root, PACKAGE)
    names += [n for n in TOP_FILES if (root / n).is_file()]
    data = root / "data" / "cdut"
    names += sorted(p.relative_to(root).as_posix() for p in data.glob("*.json"))
    rag = data / "rag"
    names += [
        p.relative_to(root).as_posix()
        for p in (rag / "bootstrap.json", rag / "bootstrap.vectors.sqlite")
        if p.is_file()
    ]
    knowledge_files = _knowledge_files(root, bundle) if bundle else {}
    if not any(n.endswith("web_assets/v2/index.html") for n in names):
        raise ValueError("v2 front end missing from package")
    files = {n: (root / n).read_bytes() for n in names}
    files.update(knowledge_files)
    if knowledge_current:
        files.update(_published_knowledge_files(root))
    if any(len(b) > MAX_FILE for b in files.values()):
        raise ValueError("Release file too large")
    return files


def manifest_for(files: dict[str, bytes], bundle: str, commit: str = "") -> dict[str, object]:
    hashes = {n: sha256(b) for n, b in sorted(files.items())}
    version = "r-" + sha256(json.dumps(hashes, sort_keys=True).encode())[:12]
    return {
        "schema_version": SCHEMA,
        "version": version,
        "knowledge_bundle": bundle,
        "git_commit": commit,
        "files": hashes,
    }


def source_export_commit(root: Path, files: dict[str, bytes], commit: str = "") -> str:
    """Bind a runtime built from a Git ZIP to its verified source identity."""
    source = root / "SOURCE_MANIFEST.json"
    if not source.exists():
        return commit
    try:
        manifest = json.loads(source.read_bytes())
        identity = manifest["git_commit"]
        hashes = manifest["files_sha256"]
        if (
            not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{40,64}", identity)
            or manifest.get("working_tree_changes") is not False
            or not isinstance(hashes, dict) or not hashes
            or (commit and commit != identity)
        ):
            raise ValueError("Source export identity is invalid or mismatched")
        for name, expected in hashes.items():
            if not isinstance(expected, str) or sha256(_knowledge_bytes(root, name)) != expected:
                raise ValueError("Source export file hash mismatch")
        if any(hashes.get(name) != sha256(body) for name, body in files.items()):
            raise ValueError("Source export contains unbound release files")
    except (KeyError, TypeError, OSError, ValueError) as exc:
        raise ValueError("Source export verification failed") from exc
    return identity


def build(
    root: Path, output: Path, bundle: str = "", commit: str = "", *,
    knowledge_current: bool = False,
) -> dict[str, object]:
    files = collect(root, bundle, knowledge_current=knowledge_current)
    commit = source_export_commit(root, files, commit)
    manifest = manifest_for(files, bundle, commit)
    if knowledge_current:
        manifest["knowledge_version"] = json.loads(files["data/cdut/rag/current.json"])["version"]
        previous = json.loads(files["data/cdut/rag/last_good.json"])
        manifest["knowledge_last_good"] = previous["version"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "x:gz") as tar:
        for name, data in [(MANIFEST, json.dumps(manifest, indent=1).encode()), *files.items()]:
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    return manifest


# ---- remote side (stdlib only) ------------------------------------------------------------


def _safe(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def read_archive(archive: bytes) -> tuple[dict[str, object], dict[str, bytes]]:
    """Verify the manifest against every member; any mismatch rejects the whole release."""
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or not _safe(member.name):
                raise ValueError("Unsafe archive member")
            handle = tar.extractfile(member)
            if handle is None:
                raise ValueError("Unreadable archive member")
            files[member.name] = handle.read()
    manifest = json.loads(files.pop(MANIFEST))
    expected = manifest["files"]
    if manifest.get("schema_version") != SCHEMA or set(expected) != set(files):
        raise ValueError("Manifest does not match archive")
    if any(sha256(files[n]) != h for n, h in expected.items()):
        raise ValueError("Checksum mismatch")
    version = manifest["version"]
    if manifest_for(files, manifest.get("knowledge_bundle", ""))["version"] != version:
        raise ValueError("Release version does not match content")
    return manifest, files


def _switch(base: Path, target: Path) -> None:
    link = base / "current.switch"
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(target.relative_to(base))
    os.replace(link, base / "current")  # atomic on POSIX


def _log(base: Path, event: dict[str, object]) -> None:
    with (base / "deploy-log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": int(time.time()), **event}) + "\n")


def install(
    base: Path,
    archive: bytes,
    *,
    restart: Callable[[], None],
    health: Callable[[], bool],
    keep: int = 5,
) -> dict[str, object]:
    manifest, files = read_archive(archive)
    version = str(manifest["version"])
    releases = base / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    current = base / "current"
    previous: Path | None = None
    if current.is_symlink():
        previous = current.resolve()
    elif current.is_dir():
        # One-time migration from the in-place layout; kept as the rollback target.
        previous = releases / f"legacy-{int(time.time())}"
        os.replace(current, previous)
        _switch(base, previous)
    target = releases / version
    if not target.exists():
        staging = releases / f".{version}.staging"
        shutil.rmtree(staging, ignore_errors=True)
        for name, data in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (staging / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        os.replace(staging, target)
    if previous is not None and previous == target.resolve():
        return {"status": "UNCHANGED", "version": version}
    _switch(base, target)
    restart()
    if not health():
        if previous is None:
            _log(base, {"event": "failed_no_previous", "version": version})
            raise RuntimeError("health_check_failed_no_previous_release")
        _switch(base, previous)
        restart()
        restored = health()
        _log(
            base,
            {
                "event": "rolled_back",
                "version": version,
                "restored": previous.name,
                "restored_healthy": restored,
            },
        )
        raise RuntimeError("health_check_failed_rolled_back")
    _log(
        base,
        {"event": "released", "version": version, "previous": previous.name if previous else None},
    )
    protected = {target.name, previous.name if previous else ""}
    old = sorted(
        (p for p in releases.iterdir() if p.is_dir() and not p.name.startswith(".")),
        key=lambda p: p.stat().st_mtime,
    )
    for path in old[:-keep]:
        if path.name not in protected:
            shutil.rmtree(path)
    return {
        "status": "RELEASED",
        "version": version,
        "previous": previous.name if previous else None,
    }


def public_host(env_file: Path = Path("/etc/campuspilot/campuspilot.env")) -> str:
    """The app only accepts its public Host header (TrustedHost), so probes must send it."""
    from urllib.parse import urlsplit

    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("PUBLIC_ORIGIN="):
            return urlsplit(line.split("=", 1)[1].strip().strip('"')).hostname or ""
    return "127.0.0.1"


def http_health(
    url: str = "http://127.0.0.1:8766", host: str = "", attempts: int = 15, wait: float = 2.0
) -> bool:
    import urllib.request

    host = host or public_host()
    for _ in range(attempts):
        try:
            ok = all(
                urllib.request.urlopen(
                    urllib.request.Request(url + path, headers={"Host": host}), timeout=5
                ).status
                == 200
                for path in ("/", "/api/catalog", "/api/map-config")
            )
            if ok:
                return True
        except OSError:
            pass
        time.sleep(wait)
    return False


def systemctl_restart(unit: str = "campuspilot") -> None:
    import subprocess

    subprocess.run(["systemctl", "restart", unit], check=True, timeout=60)
