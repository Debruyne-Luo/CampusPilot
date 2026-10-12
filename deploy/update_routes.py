"""Publish the bounded route increment with drift detection and complete file rollback."""

import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

ASSETS = "backend/src/campuspilot/web_assets/"
FILES = (
    ASSETS + "journey.js",
    ASSETS + "journey.css",
    ASSETS + "map-frame.js",
    ASSETS + "map-frame.css",
    ASSETS + "app.js",
    "backend/src/campuspilot/web.py",
    ASSETS + "index.html",
)
ROOT = Path("/opt/campuspilot")
HOST = "campuspilot.38-244-61-184.sslip.io"
BACKUP_DIRECTORY = "route-backups"
SUCCESS_LABEL = "ROUTES UPDATED"


class UpdateFailure(Exception):
    """Only controlled messages cross the remote command boundary."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode(payload):
    if not isinstance(payload, dict) or set(payload) != set(FILES):
        raise UpdateFailure("invalid_file_set")
    result = {}
    for name in FILES:
        item = payload[name]
        if not isinstance(item, dict) or set(item) != {"before", "sha256", "data"}:
            raise UpdateFailure("invalid_record")
        try:
            data = base64.b64decode(item["data"], validate=True)
            data.decode("utf-8")
        except (ValueError, UnicodeError, TypeError):
            raise UpdateFailure("invalid_encoding") from None
        if len(data) > 200_000 or digest(data) != item["sha256"]:
            raise UpdateFailure("invalid_checksum")
        if name.endswith(".py"):
            compile(data, name, "exec")
        result[name] = (item["before"], data)
    return result


def write_atomic(path, data, metadata):
    fd, temp = tempfile.mkstemp(prefix=".route-update-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, stat.S_IMODE(metadata.st_mode))
        if hasattr(os, "chown"):
            os.chown(temp, metadata.st_uid, metadata.st_gid)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def ensure_public_parent(path, target):
    """New source directories inherit the existing branch, despite the private umask."""
    if not path.resolve().is_relative_to(target.resolve()):
        raise UpdateFailure("unsafe_target")
    missing = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    metadata = cursor.stat()
    for directory in reversed(missing):
        directory.mkdir()
        os.chmod(directory, stat.S_IMODE(metadata.st_mode))
        if hasattr(os, "chown"):
            os.chown(directory, metadata.st_uid, metadata.st_gid)


def apply(target, records, backups, verify):
    previous, metadata = {}, {}
    template = (target / "backend/src/campuspilot/web.py").stat()
    for name in records:
        path = target / name
        if path.is_symlink() or not path.resolve().is_relative_to(target.resolve()):
            raise UpdateFailure("unsafe_target")
        if path.exists() and not path.is_file():
            raise UpdateFailure("invalid_target")
        old = path.read_bytes() if path.exists() else None
        previous[name] = old
        metadata[name] = path.stat() if path.exists() else template
    if all(previous[n] == records[n][1] for n in records):
        verify()
        return None
    for name, (before, _) in records.items():
        actual = digest(previous[name]) if previous[name] is not None else None
        if actual != before:
            raise UpdateFailure("remote_drift")
    identifier = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    backup = backups / identifier
    backup.mkdir(parents=True, mode=0o700)
    manifest = {
        name: {
            "before": digest(old) if old is not None else None,
            "after": digest(records[name][1]),
        }
        for name, old in previous.items()
    }
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name, old in previous.items():
        if old is not None:
            destination = backup / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(old)
    changed = []
    try:
        for name in FILES:
            ensure_public_parent((target / name).parent, target)
            write_atomic(target / name, records[name][1], metadata[name])
            changed.append(name)
        verify()
    except Exception as failure:
        safe_failures = {
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
            "data_place_count_failed",
            "data_position_state_failed",
            "data_lead_note_failed",
            "data_provenance_failed",
        }
        # A known phase code is echoed verbatim. Anything else reports only the exception
        # class name: enough to tell a JSON decode failure from a timeout, without echoing
        # a message that could carry response bodies, cookies or upstream text.
        failure_code = str(failure) if str(failure) in safe_failures else type(failure).__name__
        for name in reversed(changed):
            if previous[name] is None:
                (target / name).unlink(missing_ok=True)
            else:
                write_atomic(target / name, previous[name], metadata[name])
        try:
            verify(restored=True)
        except Exception:
            raise UpdateFailure("rollback_health_failed") from None
        suffix = ":" + failure_code if failure_code else ""
        raise UpdateFailure("update_failed_restored" + suffix) from None
    return identifier


def main(verify_extra=None):
    os.umask(0o077)
    target = (ROOT / "current").resolve()
    if not target.is_relative_to(ROOT / "releases"):
        raise UpdateFailure("unexpected_release_path")
    records = decode(json.load(sys.stdin))
    # Existing service explicitly disables access logs, so origins cannot enter the journal.
    unit = subprocess.run(
        ["systemctl", "cat", "campuspilot.service"], capture_output=True, text=True, check=True
    ).stdout
    if "--no-access-log" not in unit:
        raise UpdateFailure("access_logging_enabled")

    def verify(restored=False):
        subprocess.run(
            ["systemctl", "restart", "campuspilot.service"],
            check=True,
            capture_output=True,
            timeout=40,
        )
        for _ in range(20):
            try:
                with httpx.Client(timeout=5, trust_env=False, headers={"Host": HOST}) as client:
                    response = client.get("http://127.0.0.1:8766/healthz")
                    if response.status_code == 200 and response.json() == {"status": "ready"}:
                        if restored:
                            return
                        for name in FILES:
                            if "/web_assets/" not in name:
                                continue
                            endpoint = (
                                "/" if name.endswith("index.html") else "/assets/" + Path(name).name
                            )
                            served = client.get("http://127.0.0.1:8766" + endpoint)
                            if served.status_code != 200 or served.content != records[name][1]:
                                raise UpdateFailure("served_file_mismatch")
                        if verify_extra is not None:
                            verify_extra(client)
                        return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise UpdateFailure("health_failed")

    identifier = apply(target, records, ROOT / BACKUP_DIRECTORY, verify)
    print(json.dumps({"status": SUCCESS_LABEL, "backup_id": identifier, "files": len(FILES)}))


if __name__ == "__main__":
    try:
        main()
    except UpdateFailure as exc:
        print("ROUTE UPDATE FAILED: " + str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("ROUTE UPDATE FAILED: controlled operation failure", file=sys.stderr)
        sys.exit(1)
