"""Build (default) or publish a whole-package CampusPilot release.

    python deploy/publish_release.py --bundle approved-20261011 --output dist/release.tar.gz
    python deploy/publish_release.py --bundle approved-20261011 --output dist/release.tar.gz \
        --publish --host campuspilot-vps        # explicit; never run by tests

Publishing streams deploy/_release.py plus the archive to `ssh HOST sudo python3 -`, which
installs under /opt/campuspilot with an atomic `current` switch and health-check rollback.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _release  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def remote_program(archive: bytes, base: str = "/opt/campuspilot") -> str:
    engine = Path(_release.__file__).read_text(encoding="utf-8")
    return (
        engine
        + "\n\nimport base64 as _b64, json as _json, sys as _sys\n"
        + f"_data = _b64.b64decode({base64.b64encode(archive).decode()!r})\n"
        + "try:\n"
        + f"    print(_json.dumps(install(Path({base!r}), _data, restart=systemctl_restart,"
        + " health=http_health)))\n"
        + "except Exception as exc:\n"
        + "    print(_json.dumps({'status': 'FAILED', 'reason': str(exc)}))\n"
        + "    _sys.exit(2)\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    knowledge = parser.add_mutually_exclusive_group()
    knowledge.add_argument(
        "--bundle", default="", help="data/cdut/rag/<bundle>, e.g. approved-20261011"
    )
    knowledge.add_argument(
        "--knowledge-current", action="store_true",
        help="Freeze current.json, last_good.json and their complete published versions",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--host", default="campuspilot-vps")
    args = parser.parse_args()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    manifest = _release.build(
        ROOT, args.output, args.bundle, commit, knowledge_current=args.knowledge_current,
    )
    print(
        json.dumps(
            {
                "version": manifest["version"],
                "files": len(manifest["files"]),  # type: ignore[arg-type]
                "bundle": args.bundle,
                "knowledge_version": manifest.get("knowledge_version"),
                "archive": str(args.output),
            }
        )
    )
    if not args.publish:
        return
    program = remote_program(args.output.read_bytes())
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            args.host,
            "sudo /usr/bin/python3 -",
        ],
        input=program,
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
    )
    print(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "{}")
    if result.returncode:
        parser.exit(2, "Release failed; service was switched back if a previous release existed.\n")


if __name__ == "__main__":
    main()
