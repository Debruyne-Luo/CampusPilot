"""Read-only comparison with the captured live release; no credentials or network."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "docs/releases/live-20261012.manifest.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def release_paths(root: Path, bundle: str) -> set[str]:
    """Match the published scopes in deploy/_release.py; exclude runtime caches/raw sources."""
    paths: set[Path] = set()
    for folder in (root / "backend/src/campuspilot", root / "data/cdut/rag" / bundle):
        paths.update(
            p
            for p in folder.rglob("*")
            if p.is_file()
            and not {"__pycache__", ".mypy_cache", ".pytest_cache", "raw"}.intersection(p.parts)
            and p.suffix not in {".pyc", ".pyo"}
        )
    paths.update((root / "data/cdut").glob("*.json"))
    for name in (
        "pyproject.toml",
        "uv.lock",
        "data/cdut/rag/bootstrap.json",
        "data/cdut/rag/bootstrap.vectors.sqlite",
    ):
        if (root / name).is_file():
            paths.add(root / name)
    return {p.relative_to(root).as_posix() for p in paths}


def check(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    hashes = manifest["files"]
    missing, changed, line_endings = [], [], []
    for name, expected in hashes.items():
        path = root / name
        if not path.is_file():
            missing.append(name)
            continue
        data = path.read_bytes()
        if digest(data) == expected:
            continue
        if b"\0" not in data and digest(data.replace(b"\r\n", b"\n")) == expected:
            line_endings.append(name)
        else:
            changed.append(name)
    added = sorted(release_paths(root, manifest["knowledge_bundle"]) - hashes.keys())
    version_valid = (
        manifest["version"] == "r-" + digest(json.dumps(hashes, sort_keys=True).encode())[:12]
    )
    return {
        "matches_live_manifest": not (missing or changed or added) and version_valid,
        "release": manifest["version"],
        "source_commit": manifest["git_commit"],
        "manifest_files": len(hashes),
        "manifest_version_valid": version_valid,
        "missing": missing,
        "changed": changed,
        "added": added,
        "crlf_only_count": len(line_endings),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = check(args.root.resolve(), json.loads(RECEIPT.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["matches_live_manifest"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
