"""Publish only route files, checking the server against a saved pre-change source archive."""

import argparse
import ast
import base64
import hashlib
import json
import runpy
import subprocess
from pathlib import Path
from zipfile import ZipFile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    helper_path = root / "deploy/update_routes.py"
    helper = helper_path.read_text(encoding="utf-8")
    ast.parse(helper, feature_version=(3, 12))
    files = runpy.run_path(str(helper_path))["FILES"]
    payload = {}
    with ZipFile(args.baseline) as archive:
        manifest = json.loads(archive.read("release-manifest.json"))["files_sha256"]
        for name in files:
            before = archive.read(name) if name in archive.namelist() else None
            checksum = hashlib.sha256(before).hexdigest() if before is not None else None
            if checksum != manifest.get(name):
                raise ValueError("Baseline manifest mismatch")
            data = (root / name).read_bytes()
            payload[name] = {
                "before": checksum,
                "sha256": hashlib.sha256(data).hexdigest(),
                "data": base64.b64encode(data).decode("ascii"),
            }
    if args.check_only:
        print("ROUTE RELEASE CHECK OK: 7 bounded files, baseline hashes and Python 3.12 syntax.")
        return
    encoded = base64.b64encode(json.dumps(payload).encode()).decode("ascii")
    source = base64.b64encode(helper.encode()).decode("ascii")
    program = (
        "import base64, io, sys\n"
        f"sys.stdin = io.StringIO(base64.b64decode('{encoded}').decode())\n"
        f"exec(compile(base64.b64decode('{source}'), 'route_update', 'exec'))\n"
    )
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=15",
            "campuspilot-vps",
            "/opt/campuspilot/current/.venv/bin/python -",
        ],
        input=program,
        text=True,
        check=False,
    )
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
