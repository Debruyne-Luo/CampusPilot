"""First Dify connection, called through encrypted SSH stdin by connect-dify.ps1."""

import concurrent.futures
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx

ORIGIN = "https://campuspilot.38-244-61-184.sslip.io"
DIFY_URL = "https://api.dify.ai/v1/chat-messages"
LOOPBACK = "http://127.0.0.1:8766"
ENV_PATH = Path("/etc/campuspilot/campuspilot.env")
PYTHON = "/opt/campuspilot/current/.venv/bin/python"


class ConnectionFailure(Exception):
    """A controlled code, never a credential or provider response body."""


def validate_settings(settings):
    if not isinstance(settings, dict) or set(settings) != {"dify_api_key"}:
        raise ConnectionFailure("invalid_settings")
    key = settings["dify_api_key"]
    if not isinstance(key, str) or not re.fullmatch(r"app-[A-Za-z0-9_-]{16,240}", key):
        raise ConnectionFailure("invalid_application_key")
    return key


def request_json(url, payload=None, headers=None, timeout=95):
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            with client.stream(
                "GET" if payload is None else "POST",
                url,
                json=payload,
                headers={"Content-Type": "application/json", **(headers or {})},
            ) as response:
                if not 200 <= response.status_code < 300:
                    raise ConnectionFailure("http_" + str(response.status_code))
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk[: 1_000_001 - len(raw)])
                    if len(raw) > 1_000_000:
                        raise ConnectionFailure("oversized_response")
                return json.loads(raw), response.headers
    except (httpx.RequestError, ValueError):
        raise ConnectionFailure("network_or_response_error") from None


def expected_ids(query, tool_token):
    body, _ = request_json(
        LOOPBACK + "/v1/directory/assist",
        query,
        {"Host": ORIGIN.removeprefix("https://"), "Authorization": "Bearer " + tool_token},
        timeout=20,
    )
    if body.get("status") != "success":
        raise ConnectionFailure("directory_not_ready")
    return {
        key + "s": [record[key] for record in body[plural]]
        for plural, key in (
            ("services", "service_id"),
            ("teachers", "teacher_id"),
            ("places", "place_id"),
        )
    }


def validate_envelope(reply, expected):
    try:
        envelope = json.loads(reply["answer"])
        if envelope.get("schema_version") != 1 or envelope.get("status") != "success":
            raise ValueError()
        if any(envelope.get(key) != ids for key, ids in expected.items()):
            raise ValueError()
        # Use the actual installed Python contract and directory associations.
        validator = (
            "import sys; from pathlib import Path; "
            "from campuspilot.presentation import AnswerEnvelope, resolve_cards; "
            "from campuspilot.directory.repository import DirectoryRepository; "
            "e=AnswerEnvelope.model_validate_json(sys.stdin.read()); "
            "resolve_cards(DirectoryRepository.load(Path('/opt/campuspilot/current/data/cdut')),e)"
        )
        subprocess.run(
            [PYTHON, "-c", validator],
            input=json.dumps(envelope),
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=20,
        )
    except (KeyError, TypeError, ValueError, subprocess.SubprocessError):
        raise ConnectionFailure("invalid_structured_application") from None


def wait_for_health():
    for _ in range(15):
        try:
            result, _ = request_json(
                LOOPBACK + "/healthz", headers={"Host": ORIGIN.removeprefix("https://")}, timeout=2
            )
            if result == {"status": "ready"}:
                return
        except ConnectionFailure:
            pass
        time.sleep(1)
    raise ConnectionFailure("backend_restart_failed")


def validate_browser_chat(message, expected):
    headers = {
        "Host": ORIGIN.removeprefix("https://"),
        "Origin": ORIGIN,
        "X-CampusPilot-Request": "1",
    }
    session, response_headers = request_json(LOOPBACK + "/api/session", {}, headers, timeout=10)
    if session.get("configured") is not True:
        raise ConnectionFailure("backend_not_configured")
    cookie = response_headers.get("Set-Cookie", "").split(";", 1)[0]
    if not cookie.startswith("campuspilot_session="):
        raise ConnectionFailure("missing_browser_session")
    reply, _ = request_json(
        LOOPBACK + "/api/chat", {"message": message}, {**headers, "Cookie": cookie}
    )
    if not reply.get("answer") or not reply.get("request_id"):
        raise ConnectionFailure("missing_chat_answer")
    for plural, key in (
        ("services", "service_id"),
        ("teachers", "teacher_id"),
        ("places", "place_id"),
    ):
        if [record[key] for record in reply[plural]] != expected[key + "s"]:
            raise ConnectionFailure("incorrect_chat_cards")
    return cookie


def main(settings):
    key = validate_settings(settings)
    if os.geteuid() != 0:
        raise ConnectionFailure("root_required")
    if ENV_PATH.is_symlink() or not ENV_PATH.is_file():
        raise ConnectionFailure("missing_private_environment")
    info = ENV_PATH.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 16_384:
        raise ConnectionFailure("unsafe_environment_permissions")
    original = ENV_PATH.read_text(encoding="utf-8")
    values = {}
    for line in original.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, value = line.split("=", 1)
        if name in values:
            raise ConnectionFailure("duplicate_environment_key")
        values[name] = value
    if values.get("PUBLIC_ORIGIN") != ORIGIN:
        raise ConnectionFailure("unexpected_public_origin")
    if values.get("DIFY_API_KEY"):
        raise ConnectionFailure("already_configured_no_changes")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", values.get("CAMPUSPILOT_API_TOKEN", "")):
        raise ConnectionFailure("invalid_existing_tool_token")
    backup = ENV_PATH.with_name("campuspilot.env.before_dify")
    if backup.exists() or backup.is_symlink():
        raise ConnectionFailure("existing_backup_no_changes")

    # Only deployment check prompts containing public information are sent to Dify.
    cases = (
        (
            "Campus-card replacement",
            "请查询成都校区校园卡补办流程及办理地点。",
            {"kind": "service", "service_key": "campus_card_replacement"},
        ),
        (
            "Teacher office",
            "计算机与网络安全学院王洪辉老师的办公室在哪里？",
            {"kind": "teacher", "query": "王洪辉"},
        ),
    )
    expected = [expected_ids(case[2], values["CAMPUSPILOT_API_TOKEN"]) for case in cases]
    print("Checking the published Dify API before changing server settings...", flush=True)
    reply, _ = request_json(
        DIFY_URL,
        {
            "inputs": {},
            "query": cases[1][1],
            "user": "cp-deployment-check-" + uuid4().hex,
            "conversation_id": "",
            "response_mode": "blocking",
            "auto_generate_name": False,
        },
        {"Authorization": "Bearer " + key},
    )
    validate_envelope(reply, expected[1])
    print("Published API returned validated structured identifiers.", flush=True)

    updates = {
        "DIFY_API_BASE_URL": "https://api.dify.ai/v1",
        "DIFY_API_KEY": key,
        "DIFY_STRUCTURED_ANSWERS": "1",
    }
    lines = [line for line in original.splitlines() if line.split("=", 1)[0] not in updates]
    lines.extend(name + "=" + value for name, value in updates.items())
    changed = False
    try:
        shutil.copy2(ENV_PATH, backup)
        os.chmod(backup, 0o600)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=ENV_PATH.parent, delete=False
        ) as staged:
            staged.write("\n".join(lines) + "\n")
            staged.flush()
            os.fsync(staged.fileno())
            staged_path = Path(staged.name)
        os.chmod(staged_path, 0o600)
        os.replace(staged_path, ENV_PATH)
        changed = True
        subprocess.run(["systemctl", "restart", "campuspilot.service"], check=True, timeout=30)
        wait_for_health()
        print("Checking two independent backend chats with live tool callbacks...", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(validate_browser_chat, case[1], ids)
                for case, ids in zip(cases, expected, strict=True)
            ]
            cookies = [future.result() for future in futures]
        if len(set(cookies)) != 2:
            raise ConnectionFailure("browser_session_collision")
    except Exception:
        if changed:
            shutil.copy2(backup, ENV_PATH)
            os.chmod(ENV_PATH, 0o600)
            subprocess.run(["systemctl", "restart", "campuspilot.service"], check=True, timeout=30)
        print(
            "Connection failed; the previous CampusPilot settings were preserved or restored.",
            flush=True,
        )
        raise
    print("DIFY CONNECTED: both backend chat scenarios passed with separate sessions.", flush=True)
    print(
        "Public visitor login, the online map and domestic networks still need browser checks.",
        flush=True,
    )


def run(settings):
    try:
        main(settings)
    except ConnectionFailure as exc:
        raise SystemExit("Dify connection stopped: " + str(exc)) from None
    except Exception:
        raise SystemExit("Dify connection stopped: server_operation_failed") from None
