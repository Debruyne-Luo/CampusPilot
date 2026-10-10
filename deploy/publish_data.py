"""Publish two fixed directory-data files using the existing transactional update engine.

The map-layout updater also owns `places.json`, but its baseline constants predate the
2026-10-09 workspace release and it would republish the static assets that release already
replaced. This entry point is deliberately data-only: two validated JSON files, one restart,
served-snapshot verification, and the same backup/rollback boundary as the other publishers.
"""

import argparse
import ast
import base64
import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "data/cdut/places.json",
    "data/cdut/sources.json",
)
BACKUP_DIRECTORY = "data-backups"
SUCCESS_LABEL = "DATA UPDATED"
RELEASE_LABEL = "Data"
VERIFY_FUNCTION = "verify_data"
PLAN_SHA256 = "2d354d434f72657a77c8f2ec8d96f36735654e8623518ef6d636006c00a31481"

# A failed semantic probe raises inside the engine's rollback boundary.
VERIFY = """
def verify_data(client):
    base = "http://127.0.0.1:8766"
    served = client.get(base + "/api/places").json()
    places = served["places"]
    if len(places) != 40:
        raise RuntimeError("data_place_count_failed")
    located = [p for p in places if p.get("position")]
    if len(located) != 32 or any(p.get("navigation_url") for p in places):
        raise RuntimeError("data_position_state_failed")
    expected = {
        "cdut:place:card-centre": "\\u540c\\u4e00\\u7f16\\u53f7\\u5efa\\u7b51",
        "cdut:place:network-security": "同楼",
    }
    for place_id, marker in expected.items():
        record = next(p for p in places if p["place_id"] == place_id)
        if not any(marker in note for note in record["notes"]):
            raise RuntimeError("data_lead_note_failed")
    # The campus plan is referenced by place records, not by the service catalogue.
    plan = next(s for s in served["sources"] if s["evidence_id"] == "cdut:evidence:campus-plan")
    if plan["access_method"] != "direct" or plan["source_file_sha256"] != PLAN_SHA256:
        raise RuntimeError("data_provenance_failed")
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    engine = (ROOT / "deploy/update_routes.py").read_text(encoding="utf-8")
    ast.parse(engine, feature_version=(3, 12))
    payload = {}
    with ZipFile(args.baseline) as archive:
        manifest = json.loads(archive.read("release-manifest.json"))["files_sha256"]
        for name in FILES:
            before = archive.read(name) if name in archive.namelist() else None
            checksum = hashlib.sha256(before).hexdigest() if before is not None else None
            if checksum != manifest.get(name):
                raise ValueError("Baseline manifest mismatch")
            data = (ROOT / name).read_bytes()
            # Both files are loaded as strict Pydantic snapshots; reject an invalid payload
            # here rather than after the service has already been restarted.
            json.loads(data.decode("utf-8"))
            payload[name] = {
                "before": checksum,
                "sha256": hashlib.sha256(data).hexdigest(),
                "data": base64.b64encode(data).decode("ascii"),
            }
    encoded_payload = base64.b64encode(json.dumps(payload).encode()).decode()
    program = (
        "import base64, io, sys\n"
        "ns = {'__name__':'campuspilot_update_engine'}\n"
        f"exec(compile(base64.b64decode('{base64.b64encode(engine.encode()).decode()}'),"
        " 'update_engine', 'exec'), ns)\n"
        f"ns['FILES'] = {FILES!r}\n"
        f"ns['BACKUP_DIRECTORY'] = {BACKUP_DIRECTORY!r}\n"
        f"ns['SUCCESS_LABEL'] = {SUCCESS_LABEL!r}\n"
        "sys.stdin = io.StringIO(base64.b64decode('"
        + encoded_payload
        + "').decode())\n"
        # The probe is defined in this top-level namespace, so anything it reads must live
        # here too; names placed only in `ns` are invisible to it.
        + f"PLAN_SHA256 = {PLAN_SHA256!r}\n"
        + VERIFY
        + f"\nns['main'](verify_extra={VERIFY_FUNCTION})\n"
    )
    compile(program, "data_publish", "exec")
    if args.check_only:
        print(
            f"{RELEASE_LABEL.upper()} RELEASE CHECK OK: {len(FILES)} fixed files; "
            "hashes, JSON syntax and Python 3.12 syntax checked."
        )
        return
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
        encoding="utf-8",
        capture_output=True,
        check=False,
        timeout=150,
    )
    # Do not echo arbitrary upstream stderr or exceptions containing response data.
    if result.returncode:
        known = (
            "remote_drift",
            "invalid_file_set",
            "invalid_record",
            "invalid_encoding",
            "invalid_checksum",
            "unsafe_target",
            "access_logging_enabled",
            "rollback_health_failed",
            "update_failed_restored",
            "SyntaxError",
            "NameError",
        )
        reason = next((code for code in known if code in result.stderr), "remote_operation_failed")
        if reason == "update_failed_restored":
            phases = (
                "served_file_mismatch",
                "health_failed",
                "data_place_count_failed",
                "data_position_state_failed",
                "data_lead_note_failed",
                "data_provenance_failed",
            )
            phase = next((code for code in phases if code in result.stderr), "")
            if phase:
                reason += ": " + phase
        print(RELEASE_LABEL + " publish failed: " + reason)
        raise SystemExit(result.returncode)
    for line in result.stdout.splitlines():
        try:
            outcome = json.loads(line)
        except ValueError:
            continue
        if outcome.get("status") == SUCCESS_LABEL:
            print(json.dumps(outcome))


if __name__ == "__main__":
    main()
