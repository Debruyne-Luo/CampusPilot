"""Update web assets and optionally unconfirmed map candidates, with rollback."""

import base64
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

NAMES = (
    "app.js",
    "style.css",
    "map-shell.css",
    "map-frame.css",
    "map-frame.html",
    "map-frame.js",
    "index.html",  # Publish the document after its dependencies.
)
BASE = {
    "app.js": "76486d927369c0a1e0be980a9a7457a42163689feda9a433e9ee9df036150c76",
    "index.html": "f55293696fc75884f7ffb7b64beb283ddca654b3eae451ae73e6000b681119b8",
    "map-frame.css": "347d05b7fd4227abc71e8b0477ce9c51e1fc6a22b1d22eff4f49bc89d69bbf51",
    "map-frame.html": "e9a0942c4b300531ce95fa93085e01fe620bcffe7f483b696e8ab425b00458ae",
    "map-frame.js": "6817937125226382847fc69e733617f683d72a79512935c292c502e0030b7eb1",
    "style.css": "3ebbaf8fd16f2e599ba38d61fde53418ea5f123f6b88a91ce0610fce97f77532",
    "map-shell.css": None,
}
LAYOUT_BASE = {
    "app.js": "4125cdc177fd68ce9efc95d38029ef02a98d4749b45b1fa6ac99320b94f21c12",
    "index.html": "df647b7881ba4174ad5f170b5a8578ed33e2c0a54278147c74356470f5160373",
    "map-frame.css": BASE["map-frame.css"],
    "map-frame.html": BASE["map-frame.html"],
    "map-frame.js": "826716260a469b2e64dc8bd2e3cbd8b65d74f8f37de85232eb48397090e3fe2b",
    "map-shell.css": "bc04b16dde39b8b20409f07c488387fcd2c15accaf2a18c048f3345afe0a78a2",
    "style.css": BASE["style.css"],
}
CANDIDATE_BASE = {
    "app.js": "fbd796b91fd66510f7503e166cc201ef088bdd6db4865c20864012ecf4865fef",
    "index.html": LAYOUT_BASE["index.html"],
    "map-frame.css": "0799ce6a8ecf07297b574c0a800ce82e1fb070d8982b6b00334bd785505a2f60",
    "map-frame.html": BASE["map-frame.html"],
    "map-frame.js": "8a0c8668d4740df1a18a2fda9a31b24c213d5b2741acd915477bdb2a78ea43cc",
    "map-shell.css": LAYOUT_BASE["map-shell.css"],
    "style.css": BASE["style.css"],
}
PLACES_BASE = "523c42e44120888049262aebefb81dc60b0cf663275ddcc0dc32d90cdcbf953f"
ROOT = Path("/opt/campuspilot")
ORIGIN = "https://campuspilot.38-244-61-184.sslip.io"
LOOPBACK = "http://127.0.0.1:8766"


class UpdateFailure(Exception):
    """Only controlled error codes may reach terminal output."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode_assets(settings):
    if not isinstance(settings, dict) or set(settings) != {"files"}:
        raise UpdateFailure("invalid_payload")
    records = settings["files"]
    if not isinstance(records, dict) or set(records) != set(NAMES):
        raise UpdateFailure("invalid_asset_names")
    assets = {}
    for name, record in records.items():
        if not isinstance(record, dict) or set(record) != {"data", "sha256"}:
            raise UpdateFailure("invalid_asset_record")
        if not isinstance(record["data"], str) or len(record["data"]) > 280_000:
            raise UpdateFailure("oversized_asset")
        try:
            data = base64.b64decode(record["data"], validate=True)
            data.decode("utf-8")
        except (ValueError, UnicodeError):
            raise UpdateFailure("invalid_asset_encoding") from None
        if not re.fullmatch(r"[a-f0-9]{64}", str(record["sha256"])):
            raise UpdateFailure("invalid_asset_hash")
        if digest(data) != record["sha256"]:
            raise UpdateFailure("asset_checksum_mismatch")
        assets[name] = data
    if sum(map(len, assets.values())) > 600_000:
        raise UpdateFailure("oversized_bundle")
    return assets


def read_regular(path):
    if path.is_symlink():
        raise UpdateFailure("asset_is_symlink")
    if not path.exists():
        return None, None
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 200_000:
        raise UpdateFailure("invalid_existing_asset")
    return path.read_bytes(), {
        "mode": stat.S_IMODE(metadata.st_mode),
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
    }


def write_atomic(path, data, metadata):
    fd, temporary = tempfile.mkstemp(prefix=".map-update-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, metadata["mode"])
        if hasattr(os, "chown"):
            os.chown(temporary, metadata["uid"], metadata["gid"])
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def apply_assets(target, assets, backup_root, verify):
    """Reject drift before any writes, and restore only files changed by this call."""
    previous = {}
    metadata = {}
    changed = []
    for name in NAMES:
        old, info = read_regular(target / name)
        old_hash = digest(old) if old is not None else None
        if old_hash not in {
            BASE[name],
            LAYOUT_BASE[name],
            CANDIDATE_BASE[name],
            digest(assets[name]),
        }:
            raise UpdateFailure("existing_assets_changed")
        previous[name], metadata[name] = old, info
        if old != assets[name]:
            changed.append(name)
    if not changed:
        verify(assets)
        return None
    backup_root.mkdir(mode=0o700, exist_ok=True)
    if backup_root.is_symlink() or backup_root.resolve() != backup_root:
        raise UpdateFailure("invalid_backup_directory")
    backup_root.chmod(0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    backup = backup_root / stamp
    backup.mkdir(mode=0o700)
    directory_meta = target.stat()
    defaults = {"mode": 0o644, "uid": directory_meta.st_uid, "gid": directory_meta.st_gid}
    manifest = {"target": str(target), "files": {}}
    for name in changed:
        old = previous[name]
        if old is not None:
            (backup / name).write_bytes(old)
            (backup / name).chmod(0o600)
        manifest["files"][name] = {
            "before_sha256": digest(old) if old is not None else None,
            "after_sha256": digest(assets[name]),
            "metadata": metadata[name] or defaults,
        }
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (backup / "manifest.json").chmod(0o600)
    replaced = []
    try:
        for name in changed:
            write_atomic(target / name, assets[name], metadata[name] or defaults)
            replaced.append(name)
        verify(assets)
    except Exception:
        for name in reversed(replaced):
            old = previous[name]
            if old is None:
                (target / name).unlink()
            else:
                write_atomic(target / name, old, metadata[name])
        raise UpdateFailure("update_failed_old_assets_restored") from None
    return backup


def verify_served(assets):
    headers = {"Host": ORIGIN.removeprefix("https://")}
    try:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            health = client.get(LOOPBACK + "/healthz", headers=headers)
            if health.status_code != 200 or health.json() != {"status": "ready"}:
                raise UpdateFailure("backend_not_ready")
            for name in NAMES:
                response = client.get(LOOPBACK + "/assets/" + name, headers=headers)
                expected = assets[name]
                if expected is None:
                    if response.status_code != 404:
                        raise UpdateFailure("served_asset_mismatch")
                elif response.status_code != 200 or digest(response.content) != digest(expected):
                    raise UpdateFailure("served_asset_mismatch")
            page = client.get(LOOPBACK + "/", headers=headers)
            if page.status_code != 200 or digest(page.content) != digest(assets["index.html"]):
                raise UpdateFailure("served_document_mismatch")
            public = client.get(ORIGIN + "/healthz")
            if public.status_code != 200 or public.json() != {"status": "ready"}:
                raise UpdateFailure("public_gateway_not_ready")
    except (httpx.RequestError, ValueError):
        raise UpdateFailure("verification_request_failed") from None


def restore_backup(target, backup, verify):
    if backup.is_symlink() or backup.resolve() != backup or not backup.is_dir():
        raise UpdateFailure("invalid_backup_directory")
    raw, _ = read_regular(backup / "manifest.json")
    manifest = json.loads(raw or b"{}")
    if not isinstance(manifest, dict) or set(manifest) != {"target", "files"}:
        raise UpdateFailure("invalid_backup_manifest")
    records = manifest["files"]
    if manifest["target"] != str(target) or not isinstance(records, dict) or not records:
        raise UpdateFailure("backup_release_mismatch")
    if not set(records).issubset(NAMES):
        raise UpdateFailure("invalid_backup_names")
    old_assets = {}
    current_assets = {}
    current_metadata = {}
    for name in NAMES:
        current, info = read_regular(target / name)
        current_assets[name], current_metadata[name] = current, info
        if name not in records:
            old_assets[name] = current
            continue
        record = records[name]
        if not isinstance(record, dict) or set(record) != {
            "before_sha256",
            "after_sha256",
            "metadata",
        }:
            raise UpdateFailure("invalid_backup_record")
        info = record["metadata"]
        if not isinstance(info, dict) or set(info) != {"mode", "uid", "gid"}:
            raise UpdateFailure("invalid_backup_metadata")
        if (
            any(type(value) is not int or value < 0 for value in info.values())
            or info["mode"] > 0o777
        ):
            raise UpdateFailure("invalid_backup_metadata")
        current_hash = digest(current) if current is not None else None
        if current_hash != record["after_sha256"]:
            raise UpdateFailure("assets_changed_after_update")
        before = record["before_sha256"]
        if before not in {BASE[name], LAYOUT_BASE[name], CANDIDATE_BASE[name]}:
            raise UpdateFailure("backup_baseline_mismatch")
        old, _ = read_regular(backup / name)
        if (digest(old) if old is not None else None) != before:
            raise UpdateFailure("backup_checksum_mismatch")
        old_assets[name] = old
    restored = []
    try:
        for name in NAMES:
            if name not in records:
                continue
            old = old_assets[name]
            if old is None:
                (target / name).unlink()
            else:
                write_atomic(target / name, old, records[name]["metadata"])
            restored.append(name)
        verify(old_assets)
    except Exception:
        for name in reversed(restored):
            write_atomic(target / name, current_assets[name], current_metadata[name])
        raise UpdateFailure("rollback_failed_current_assets_restored") from None


def decode_places(record):
    if not isinstance(record, dict) or set(record) != {"data", "sha256"}:
        raise UpdateFailure("invalid_places_record")
    if not isinstance(record["data"], str) or len(record["data"]) > 280_000:
        raise UpdateFailure("oversized_places")
    try:
        data = base64.b64decode(record["data"], validate=True)
        data.decode("utf-8")
    except (ValueError, UnicodeError):
        raise UpdateFailure("invalid_places_encoding") from None
    if digest(data) != record["sha256"]:
        raise UpdateFailure("places_checksum_mismatch")
    return data


def validate_candidate_places(old, incoming):
    from campuspilot.domain import CampusPlace
    from pydantic import TypeAdapter

    adapter = TypeAdapter(tuple[CampusPlace, ...])
    previous = adapter.validate_json(old)
    candidates = adapter.validate_json(incoming)
    before = {p.place_id: p for p in previous}
    after = {p.place_id: p for p in candidates}
    if len(after) != len(candidates) or set(before) != set(after):
        raise UpdateFailure("place_identifiers_changed")
    for ident, candidate in after.items():
        # This increment can change only positions and explanatory notes.
        if candidate.model_dump(exclude={"position", "notes"}) != before[ident].model_dump(
            exclude={"position", "notes"}
        ):
            raise UpdateFailure("place_business_fields_changed")
        if candidate.position and candidate.position.verification_status != "needs_review":
            raise UpdateFailure("candidate_update_cannot_approve_navigation")
    return [p.model_dump(mode="json") for p in candidates]


def restart_backend():
    try:
        subprocess.run(
            ["systemctl", "restart", "campuspilot.service"],
            check=True,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 20
        with httpx.Client(timeout=2, follow_redirects=False, trust_env=False) as client:
            while time.monotonic() < deadline:
                try:
                    reply = client.get(
                        LOOPBACK + "/healthz", headers={"Host": ORIGIN.removeprefix("https://")}
                    )
                    if reply.status_code == 200 and reply.json() == {"status": "ready"}:
                        return
                except (httpx.RequestError, ValueError):
                    pass
                time.sleep(1)
    except (subprocess.SubprocessError, OSError):
        pass
    raise UpdateFailure("backend_restart_failed")


def verify_places(expected):
    try:
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = client.get(
                LOOPBACK + "/api/places", headers={"Host": ORIGIN.removeprefix("https://")}
            )
            actual = response.json().get("places", []) if response.status_code == 200 else []
        normalized = {
            p["place_id"]: {k: v for k, v in p.items() if k != "navigation_url"} for p in actual
        }
        if normalized != {p["place_id"]: p for p in expected} or any(
            p.get("navigation_url") is not None for p in actual
        ):
            raise UpdateFailure("served_places_mismatch")
    except (httpx.RequestError, ValueError, KeyError, TypeError):
        raise UpdateFailure("places_verification_failed") from None


def apply_candidates(target, data_directory, assets, incoming, backup_root, restart, verify):
    """Restore data and UI together if restart, API, or static-file checks fail."""
    from campuspilot.directory.repository import DirectoryRepository

    places_path = data_directory / "places.json"
    old, metadata = read_regular(places_path)
    if old is None or digest(old) not in {PLACES_BASE, digest(incoming)}:
        raise UpdateFailure("existing_places_changed")
    expected = validate_candidate_places(old, incoming)
    DirectoryRepository.load(data_directory)
    # Reject unrelated UI drift before even creating a backup or changing data.
    for name in NAMES:
        before, _ = read_regular(target / name)
        if (digest(before) if before is not None else None) not in {
            BASE[name],
            LAYOUT_BASE[name],
            CANDIDATE_BASE[name],
            digest(assets[name]),
        }:
            raise UpdateFailure("existing_assets_changed")
    data_backup = None
    if old != incoming:
        backup_root.mkdir(mode=0o700, exist_ok=True)
        if backup_root.is_symlink() or backup_root.resolve() != backup_root:
            raise UpdateFailure("invalid_backup_directory")
        backup_root.chmod(0o700)
        data_backup = backup_root / (
            datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        )
        data_backup.mkdir(mode=0o700)
        (data_backup / "places.json").write_bytes(old)
        (data_backup / "places.json").chmod(0o600)
        (data_backup / "manifest.json").write_text(
            json.dumps(
                {
                    "target": str(places_path),
                    "before_sha256": digest(old),
                    "after_sha256": digest(incoming),
                    "metadata": metadata,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (data_backup / "manifest.json").chmod(0o600)
    try:
        if data_backup:
            write_atomic(places_path, incoming, metadata)

        def check(updated_assets):
            if data_backup:
                restart()
            verify(updated_assets, expected)

        ui_backup = apply_assets(target, assets, ROOT / "ui-backups", check)
    except Exception:
        if data_backup:
            write_atomic(places_path, old, metadata)
            try:
                restart()
            except Exception:
                raise UpdateFailure("old_files_restored_backend_unavailable") from None
        raise UpdateFailure("candidate_update_failed_old_files_restored") from None
    return data_backup, ui_backup


def restore_candidates(data_directory, backup, restart, verify):
    if backup.is_symlink() or backup.resolve() != backup or not backup.is_dir():
        raise UpdateFailure("invalid_backup_directory")
    raw, _ = read_regular(backup / "manifest.json")
    manifest = json.loads(raw or b"{}")
    if not isinstance(manifest, dict) or set(manifest) != {
        "target",
        "before_sha256",
        "after_sha256",
        "metadata",
    }:
        raise UpdateFailure("invalid_backup_manifest")
    target = data_directory / "places.json"
    if manifest["target"] != str(target) or manifest["before_sha256"] != PLACES_BASE:
        raise UpdateFailure("backup_release_mismatch")
    old, _ = read_regular(backup / "places.json")
    current, current_metadata = read_regular(target)
    if old is None or digest(old) != manifest["before_sha256"]:
        raise UpdateFailure("backup_checksum_mismatch")
    if current is None or digest(current) != manifest["after_sha256"]:
        raise UpdateFailure("places_changed_after_update")
    metadata = manifest["metadata"]
    if (
        not isinstance(metadata, dict)
        or set(metadata) != {"mode", "uid", "gid"}
        or (any(type(v) is not int or v < 0 for v in metadata.values()) or metadata["mode"] > 0o777)
    ):
        raise UpdateFailure("invalid_backup_metadata")
    # The backed-up snapshot is the exact known pre-candidate JSON.
    from campuspilot.domain import CampusPlace
    from pydantic import TypeAdapter

    expected = [
        p.model_dump(mode="json") for p in TypeAdapter(tuple[CampusPlace, ...]).validate_json(old)
    ]
    try:
        write_atomic(target, old, metadata)
        restart()
        verify(expected)
    except Exception:
        write_atomic(target, current, current_metadata)
        try:
            restart()
        except Exception:
            raise UpdateFailure("current_files_restored_backend_unavailable") from None
        raise UpdateFailure("data_rollback_failed_current_snapshot_restored") from None


def run(settings):
    try:
        rollback_id = settings.get("rollback_id") if isinstance(settings, dict) else None
        data_rollback_id = settings.get("data_rollback_id") if isinstance(settings, dict) else None
        if data_rollback_id is not None:
            if set(settings) != {"data_rollback_id"} or not isinstance(data_rollback_id, str):
                raise UpdateFailure("invalid_rollback_id")
            if not re.fullmatch(r"\d{8}T\d{6}Z-[a-f0-9]{8}", data_rollback_id):
                raise UpdateFailure("invalid_rollback_id")
            assets = None
            incoming_places = None
        elif rollback_id is not None:
            if set(settings) != {"rollback_id"} or not isinstance(rollback_id, str):
                raise UpdateFailure("invalid_rollback_id")
            if not re.fullmatch(r"\d{8}T\d{6}Z-[a-f0-9]{8}", rollback_id):
                raise UpdateFailure("invalid_rollback_id")
            assets = None
        else:
            if isinstance(settings, dict) and set(settings) == {"files", "places"}:
                incoming_places = decode_places(settings["places"])
                assets = decode_assets({"files": settings["files"]})
            else:
                incoming_places = None
                assets = decode_assets(settings)
        if os.geteuid() != 0:
            raise UpdateFailure("root_required")
        current = (ROOT / "current").resolve(strict=True)
        if current.parent != ROOT / "releases":
            raise UpdateFailure("unexpected_release_directory")
        from campuspilot.web import ASSETS

        target = ASSETS.resolve(strict=True)
        if not target.is_relative_to(current) or target.name != "web_assets":
            raise UpdateFailure("unexpected_asset_directory")
        import fcntl

        with (ROOT / ".map-layout-update.lock").open("a") as lock:
            os.chmod(lock.name, 0o600)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            if data_rollback_id:
                data_directory = current / "data/cdut"
                if data_directory.is_symlink() or data_directory.resolve() != data_directory:
                    raise UpdateFailure("unexpected_data_directory")

                def check_restored_places(expected):
                    current_assets = {name: read_regular(target / name)[0] for name in NAMES}
                    verify_served(current_assets)
                    verify_places(expected)

                restore_candidates(
                    data_directory,
                    ROOT / "data-backups" / data_rollback_id,
                    restart_backend,
                    check_restored_places,
                )
                print("CAMPUS MAP DATA ROLLED BACK: place snapshot and HTTPS health verified.")
                print("Start a new conversation after the backend restart.")
                return
            if rollback_id:
                restore_backup(target, ROOT / "ui-backups" / rollback_id, verify_served)
                print("MAP LAYOUT ROLLED BACK: original web assets and HTTPS health verified.")
                return
            if incoming_places is not None:
                data_directory = current / "data/cdut"
                if data_directory.is_symlink() or data_directory.resolve() != data_directory:
                    raise UpdateFailure("unexpected_data_directory")

                def check_candidates(updated_assets, expected):
                    verify_served(updated_assets)
                    verify_places(expected)

                data_backup, ui_backup = apply_candidates(
                    target,
                    data_directory,
                    assets,
                    incoming_places,
                    ROOT / "data-backups",
                    restart_backend,
                    check_candidates,
                )
                print("CAMPUS MAP UPDATED: served assets, place records and HTTPS health verified.")
                if data_backup:
                    print("Private data backup: " + str(data_backup))
                if ui_backup:
                    print("Private UI backup: " + str(ui_backup))
                print("Credentials unchanged. Start a new conversation after the backend restart.")
                return
            backup = apply_assets(target, assets, ROOT / "ui-backups", verify_served)
        print("MAP LAYOUT UPDATED: served assets and public HTTPS health verified.")
        if backup:
            print("Private UI backup: " + str(backup))
        else:
            print("The same layout was already installed; no files changed.")
        print("No backend restart or credential changes. Refresh the website.")
    except (UpdateFailure, OSError, ValueError) as error:
        code = str(error) if isinstance(error, UpdateFailure) else "local_update_error"
        print("Map layout update stopped: " + code)
        raise SystemExit(1) from None
