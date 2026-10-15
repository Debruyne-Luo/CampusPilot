"""Verify the captured review inputs without writing files or accessing the network."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

EXCLUDED_PREFIX = "docs/architecture-review/"


def git(root: Path, *args: str) -> str:
    output = subprocess.check_output(
        ["git", "-c", "core.longpaths=true", *args], cwd=root, encoding="utf-8"
    )
    return output if "-z" in args else output.rstrip("\r\n")


def verify(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    differences: list[dict[str, str]] = []
    if git(root, "rev-parse", "HEAD") != manifest["head"]:
        differences.append({"path": "HEAD", "reason": "commit_changed"})
    if git(root, "branch", "--show-current") != manifest["branch"]:
        differences.append({"path": "branch", "reason": "branch_changed"})
    expected = {item["path"] for item in manifest["files"]}
    current = set(
        git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
    ) - {""}
    for name in sorted(current - expected):
        if not name.startswith(EXCLUDED_PREFIX):
            differences.append({"path": name, "reason": "new_input"})
    for item in manifest["files"]:
        name = item["path"]
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
            differences.append({"path": name, "reason": "invalid_manifest_path"})
            continue
        path = root.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(root):
            differences.append({"path": name, "reason": "path_outside_repository"})
        elif item.get("missing"):
            if path.exists():
                differences.append({"path": name, "reason": "previously_missing_input_created"})
        elif not path.is_file():
            differences.append({"path": name, "reason": "missing_input"})
        else:
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != item["sha256"]:
                differences.append({"path": name, "reason": "bytes_changed"})
    return {
        "matches_captured_inputs": not differences,
        "captured_at": manifest.get("captured_at"),
        "head": manifest["head"],
        "checked_files": len(manifest["files"]),
        "differences": differences,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument(
        "--manifest", type=Path, default=Path(__file__).with_name("REVIEW_INPUTS.json")
    )
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = verify(args.root, manifest)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"matches_captured_inputs": False, "error_type": type(error).__name__}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["matches_captured_inputs"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
