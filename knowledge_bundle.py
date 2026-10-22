"""Restore the immutable knowledge payload after Windows-friendly outer extraction."""

from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
PREFIX = "data/cdut/"
WINDOWS_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def _long_path(path: Path) -> Path:
    """Python can use extended paths without requiring a Windows policy change."""
    path = path.resolve()
    if os.name == "nt" and not str(path).startswith("\\\\?\\"):
        name = str(path)
        return Path("\\\\?\\UNC\\" + name[2:] if name.startswith("\\\\") else "\\\\?\\" + name)
    return path


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or path.as_posix() != name
        or any(part in {".", ".."} for part in path.parts)
        or any(
            any(char in part for char in '\\:<>"|?*')
            or part.endswith((".", " "))
            or WINDOWS_RESERVED.match(part)
            for part in path.parts
        )
    ):
        raise ValueError("Unsafe knowledge archive member")
    return path


def prepare_knowledge(root: Path = ROOT) -> Path:
    """Verify the bundled bytes, restore absent files, refuse modified existing evidence."""
    root = root.resolve()
    package = json.loads((root / "PACKAGE.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    bundle = root / "data/knowledge.zip"
    expected_bundle = manifest["files"].get("data/knowledge.zip")
    if not expected_bundle or hashlib.sha256(bundle.read_bytes()).hexdigest() != expected_bundle:
        raise ValueError("Knowledge bundle checksum mismatch")
    expected = {
        name.removeprefix(PREFIX): checksum
        for name, checksum in package["unchanged_source_files_sha256"].items()
        if name.startswith(PREFIX)
    }
    if not expected:
        raise ValueError("Knowledge source identity is missing")
    base = _long_path(root / "data/cdut")
    with zipfile.ZipFile(bundle) as archive:
        if len(archive.namelist()) != len(expected) or set(archive.namelist()) != set(expected):
            raise ValueError("Knowledge archive member list mismatch")
        # Validate the complete payload before writing any file.
        payload = []
        for name, checksum in expected.items():
            relative = _safe_member(name)
            target = base.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(base):
                raise ValueError("Knowledge target escapes its directory")
            content = archive.read(name)
            if hashlib.sha256(content).hexdigest() != checksum:
                raise ValueError("Knowledge member checksum mismatch")
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
                    raise ValueError("Existing knowledge was modified; use a fresh extraction")
            else:
                payload.append((target, content))
        for target, content in payload:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".agent-tmp")
            temporary.write_bytes(content)
            temporary.replace(target)
    return base
