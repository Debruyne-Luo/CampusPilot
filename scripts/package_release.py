"""Create a source/data/workflow backup using an explicit allowlist, with file hashes."""

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = (
    "backend/src",
    "data/cdut",
    "docs",
    "integrations/dify",
    "deploy",
    "scripts",
    "tests",
    "evaluation/runtime-migration",
    "tools/models",
    ".github",
)
FILES = (
    "README.md",
    "AGENTS.md",
    "OPS.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".gitattributes",
    ".gitignore",
)
SUFFIXES = {
    ".py",
    ".json",
    ".jsonl",
    ".csv",
    ".md",
    ".yml",
    ".yaml",
    ".txt",
    ".js",
    ".html",
    ".css",
    ".sh",
    ".ps1",
    ".service",
    ".mjs",
    ".png",
    ".jpg",
    ".jpeg",
    ".webm",
    ".glb",
    ".blend",
    ".woff2",
    ".webmanifest",
    ".patch",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "release-backups")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = args.output / f"campuspilot-{stamp}.zip"
    paths = [ROOT / item for item in FILES if (ROOT / item).is_file()]
    for directory in DIRECTORIES:
        paths.extend(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix in SUFFIXES
            and not p.name.startswith(".env")
        )
    # Include only the empty, checked-in template, never actual production environment files.
    paths.extend([ROOT / "deploy/Caddyfile.campuspilot", ROOT / "deploy/campuspilot.env.example"])
    hashes = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(set(paths))
    }
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT))
    manifest = {
        "created_at": stamp,
        "base_commit": head,
        "working_tree_changes": dirty,
        "files_sha256": hashes,
        "notice": "Working snapshot, not a committed release; credentials excluded.",
    }
    with ZipFile(target, "x", compression=ZIP_DEFLATED) as archive:
        for p in sorted(set(paths)):
            archive.write(p, p.relative_to(ROOT).as_posix())
        archive.writestr(
            "release-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
        )
    print(target)
    print("sha256=" + hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
