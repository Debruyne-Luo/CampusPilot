"""Publish seven fixed knowledge files using the existing transactional update engine."""

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
    "backend/src/campuspilot/knowledge.py",
    "backend/src/campuspilot/web.py",
    "backend/src/campuspilot/web_assets/app.js",
    "backend/src/campuspilot/web_assets/index.html",
    "backend/src/campuspilot/web_assets/knowledge.js",
    "backend/src/campuspilot/web_assets/knowledge.css",
    "data/cdut/knowledge.json",
)
BACKUP_DIRECTORY = "knowledge-backups"
SUCCESS_LABEL = "KNOWLEDGE UPDATED"
RELEASE_LABEL = "Knowledge"
VERIFY_FUNCTION = "verify_knowledge"

# A failed semantic probe raises inside the engine's rollback boundary.
VERIFY = """
def verify_knowledge(client):
    headers = {"Origin": "https://campuspilot.38-244-61-184.sslip.io",
               "X-CampusPilot-Request": "1"}
    base = "http://127.0.0.1:8766"
    start = client.post(base + "/api/session", headers=headers)
    if start.status_code != 200 or not start.json().get("knowledge_available"):
        raise RuntimeError("knowledge_session_failed")
    cookie = start.cookies.get("campuspilot_session")
    headers["Cookie"] = "campuspilot_session=" + cookie
    found = client.post(base + "/api/knowledge/search", json={"query":"校庆"}, headers=headers)
    if found.status_code != 200 or found.json().get("result_status") != "success":
        raise RuntimeError("knowledge_search_failed")
    if found.json()["knowledge"][0]["time_status"] != "ended":
        raise RuntimeError("knowledge_expiry_failed")
    answer = client.post(base + "/api/chat", json={"message":"校园网无法上网怎么办"},
                         headers=headers)
    if answer.status_code != 200 or answer.json().get("answer_mode") != "official_retrieval":
        raise RuntimeError("knowledge_chat_failed")
"""


def main():
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
            if name.endswith(".py"):
                ast.parse(data.decode(), feature_version=(3, 12))
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
        f"sys.stdin = io.StringIO(base64.b64decode('{encoded_payload}').decode())\n"
        + VERIFY
        + f"\nns['main'](verify_extra={VERIFY_FUNCTION})\n"
    )
    compile(program, "knowledge_publish", "exec")
    if args.check_only:
        print(
            f"{RELEASE_LABEL.upper()} RELEASE CHECK OK: {len(FILES)} fixed files; "
            "hashes and Python 3.12 syntax checked."
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
    # Do not echo arbitrary upstream stderr or exceptions containing response/cookie data.
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
                "knowledge_session_failed",
                "knowledge_search_failed",
                "knowledge_expiry_failed",
                "knowledge_chat_failed",
                "workspace_asset_failed",
                "workspace_provider_search_failed",
                "workspace_provider_detail_failed",
                "workspace_provider_route_failed",
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
