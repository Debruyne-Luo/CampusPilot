"""Synthetic static assets exercise deployment drift and recovery, not campus facts."""

import base64
import json
import runpy
import shutil
from pathlib import Path
from typing import Any

import pytest

HELPER = Path(__file__).resolve().parents[1] / "deploy/update_map_layout.py"

# deploy/update_map_layout.py is loaded with runpy, so helper values stay dynamically typed.
Helper = dict[str, Any]
Layout = tuple[Helper, Path, dict[str, bytes], dict[str, bytes], Path]
Candidate = tuple[Helper, Path, Path, bytes, bytes, dict[str, bytes], dict[str, bytes]]


def sample_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Layout:
    helper = runpy.run_path(str(HELPER))
    namespace = helper["apply_assets"].__globals__
    target = tmp_path / "web_assets"
    target.mkdir()
    old = {
        name: b"SYNTHETIC-OLD-STATIC-ASSET:" + name.encode()
        for name in helper["NAMES"]
        if name != "map-shell.css"
    }
    new = {name: b"SYNTHETIC-NEW-STATIC-ASSET:" + name.encode() for name in helper["NAMES"]}
    for name, data in old.items():
        (target / name).write_bytes(data)
    baseline = {name: helper["digest"](old[name]) if name in old else None for name in new}
    monkeypatch.setitem(namespace, "BASE", baseline)
    return helper, target, old, new, tmp_path / "ui-backups"


@pytest.mark.parametrize("damage", ["path", "checksum", "oversized"])
def test_bundle_rejects_untrusted_names_hashes_and_size(damage: str) -> None:
    helper = runpy.run_path(str(HELPER))
    records = {
        name: {
            "data": base64.b64encode(b"SYNTHETIC").decode(),
            "sha256": helper["digest"](b"SYNTHETIC"),
        }
        for name in helper["NAMES"]
    }
    if damage == "path":
        records["../campuspilot.env"] = records.pop("index.html")
    elif damage == "checksum":
        records["index.html"]["sha256"] = "0" * 64
    else:
        records["index.html"]["data"] = "A" * 280_001
    with pytest.raises(helper["UpdateFailure"]):
        helper["decode_assets"]({"files": records})


def test_installed_drift_stops_before_backup_or_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper, target, old, new, backups = sample_layout(tmp_path, monkeypatch)
    (target / "app.js").write_bytes(b"SYNTHETIC-UNRELATED-CHANGE")
    with pytest.raises(helper["UpdateFailure"], match="^existing_assets_changed$"):
        helper["apply_assets"](
            target, new, backups, lambda assets: pytest.fail("unexpected verification")
        )
    assert not backups.exists()
    assert (target / "index.html").read_bytes() == old["index.html"]
    assert not (target / "map-shell.css").exists()


def test_failed_verification_restores_old_assets_and_new_file_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper, target, old, new, backups = sample_layout(tmp_path, monkeypatch)
    (target / "unrelated.txt").write_bytes(b"SYNTHETIC-PRESERVE")

    def fail(assets: dict[str, bytes | None]) -> None:
        assert all((target / name).read_bytes() == value for name, value in assets.items())
        raise helper["UpdateFailure"]("synthetic_failed_health")

    with pytest.raises(helper["UpdateFailure"], match="^update_failed_old_assets_restored$"):
        helper["apply_assets"](target, new, backups, fail)
    assert all((target / name).read_bytes() == value for name, value in old.items())
    assert not (target / "map-shell.css").exists()
    assert (target / "unrelated.txt").read_bytes() == b"SYNTHETIC-PRESERVE"


def test_success_is_idempotent_and_supports_verified_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper, target, old, new, backups = sample_layout(tmp_path, monkeypatch)
    calls: list[str] = []
    backup = helper["apply_assets"](target, new, backups, lambda assets: calls.append("update"))
    assert backup.is_dir()
    assert (
        helper["apply_assets"](target, new, backups, lambda assets: calls.append("repeat")) is None
    )

    def check_restored(assets: dict[str, bytes | None]) -> None:
        assert assets["map-shell.css"] is None
        assert all((target / name).read_bytes() == value for name, value in old.items())
        calls.append("rollback")

    helper["restore_backup"](target, backup, check_restored)
    assert calls == ["update", "repeat", "rollback"]
    assert not (target / "map-shell.css").exists()


def test_rollback_refuses_a_later_edit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    helper, target, old, new, backups = sample_layout(tmp_path, monkeypatch)
    backup = helper["apply_assets"](target, new, backups, lambda assets: None)
    (target / "app.js").write_bytes(b"SYNTHETIC-LATER-EDIT")
    with pytest.raises(helper["UpdateFailure"], match="^assets_changed_after_update$"):
        helper["restore_backup"](
            target, backup, lambda assets: pytest.fail("unexpected verification")
        )
    assert (target / "index.html").read_bytes() == new["index.html"]
    assert (target / "app.js").read_bytes() == b"SYNTHETIC-LATER-EDIT"


def candidate_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Candidate:
    helper, target, old_ui, new_ui, _ = sample_layout(tmp_path, monkeypatch)
    data = tmp_path / "data/cdut"
    shutil.copytree(HELPER.parents[1] / "data/cdut", data)
    current = json.loads((data / "places.json").read_bytes())
    for record in current:
        record["notes"].append("SYNTHETIC TEST COPY; NOT A REVIEW OR PRODUCTION UPDATE")
        # This legacy helper only ships unreviewed candidates; present on-site confirmed
        # points to it as candidates so the copy stays a valid candidate increment.
        if record["position"] and record["position"]["verification_status"] == "confirmed":
            record["position"].update(
                verification_status="needs_review", source_kind="map_provider"
            )
            record["position"].pop("confirmed_at", None)
            record["position"].pop("reviewer", None)
    incoming = json.dumps(current, ensure_ascii=False).encode()
    for record in current:
        record["position"] = None
    old = json.dumps(current, ensure_ascii=False).encode()
    (data / "places.json").write_bytes(old)
    namespace = helper["apply_candidates"].__globals__
    monkeypatch.setitem(namespace, "ROOT", tmp_path)
    monkeypatch.setitem(namespace, "PLACES_BASE", helper["digest"](old))
    return helper, target, data, old, incoming, old_ui, new_ui


@pytest.mark.parametrize("damage", ["name", "identity", "confirmed"])
def test_candidate_increment_refuses_business_changes_and_automatic_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    helper, _, _, old, incoming, _, _ = candidate_snapshot(tmp_path, monkeypatch)
    records = json.loads(incoming)
    if damage == "name":
        records[0]["name"] = "SYNTHETIC UNAUTHORIZED NEW NAME"
    elif damage == "identity":
        records[0]["place_id"] = "cdut:place:synthetic-unapproved"
    else:
        position = next(p["position"] for p in records if p["position"] is not None)
        position.update(
            verification_status="confirmed",
            confirmed_at="2026-10-08",
            reviewer="SYNTHETIC TEST REVIEWER; NOT REAL APPROVAL",
        )
    with pytest.raises(helper["UpdateFailure"]):
        helper["validate_candidate_places"](old, json.dumps(records, ensure_ascii=False).encode())


@pytest.mark.parametrize("damage", ["data", "ui"])
def test_candidate_drift_is_rejected_before_writes_or_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    helper, target, data, old, incoming, _, new_ui = candidate_snapshot(tmp_path, monkeypatch)
    if damage == "data":
        (data / "places.json").write_bytes(b"SYNTHETIC UNRELATED EDIT")
    else:
        (target / "app.js").write_bytes(b"SYNTHETIC UNRELATED EDIT")
    before = (data / "places.json").read_bytes()
    with pytest.raises(helper["UpdateFailure"], match="^existing_(places|assets)_changed$"):
        helper["apply_candidates"](
            target,
            data,
            new_ui,
            incoming,
            tmp_path / "data-backups",
            lambda: pytest.fail("unexpected restart"),
            lambda assets, expected: pytest.fail("unexpected verification"),
        )
    assert (data / "places.json").read_bytes() == before
    assert not (tmp_path / "data-backups").exists()
    assert not (tmp_path / "ui-backups").exists()


def test_candidate_failure_restores_ui_data_and_restarts_original_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper, target, data, old, incoming, old_ui, new_ui = candidate_snapshot(tmp_path, monkeypatch)
    restarts: list[str] = []
    unrelated = tmp_path / "unrelated-private-config"
    unrelated.write_bytes(b"SYNTHETIC PRESERVE")

    def fail(assets: dict[str, bytes | None], expected: object) -> None:
        assert (data / "places.json").read_bytes() == incoming
        assert all((target / name).read_bytes() == value for name, value in new_ui.items())
        raise helper["UpdateFailure"]("synthetic_post_restart_failure")

    with pytest.raises(
        helper["UpdateFailure"], match="^candidate_update_failed_old_files_restored$"
    ):
        helper["apply_candidates"](
            target,
            data,
            new_ui,
            incoming,
            tmp_path / "data-backups",
            lambda: restarts.append("restart"),
            fail,
        )
    assert (data / "places.json").read_bytes() == old
    assert all((target / name).read_bytes() == value for name, value in old_ui.items())
    assert not (target / "map-shell.css").exists()
    assert len(restarts) == 2 and unrelated.read_bytes() == b"SYNTHETIC PRESERVE"


def test_candidates_repeat_without_restart_and_data_rollback_refuses_later_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper, target, data, old, incoming, _, new_ui = candidate_snapshot(tmp_path, monkeypatch)
    restarts: list[str] = []
    checks: list[object] = []
    callbacks = (
        lambda: restarts.append("restart"),
        lambda assets, expected: checks.append(expected),
    )
    backup, _ = helper["apply_candidates"](
        target,
        data,
        new_ui,
        incoming,
        tmp_path / "data-backups",
        *callbacks,
    )
    assert backup.is_dir() and len(restarts) == 1
    assert helper["apply_candidates"](
        target,
        data,
        new_ui,
        incoming,
        tmp_path / "data-backups",
        *callbacks,
    ) == (None, None)
    assert len(restarts) == 1 and len(checks) == 2
    (data / "places.json").write_bytes(incoming + b"\n")
    with pytest.raises(helper["UpdateFailure"], match="^places_changed_after_update$"):
        helper["restore_candidates"](data, backup, callbacks[0], lambda expected: None)
    assert (data / "places.json").read_bytes() == incoming + b"\n"
    (data / "places.json").write_bytes(incoming)
    helper["restore_candidates"](
        data, backup, callbacks[0], lambda expected: checks.append(expected)
    )
    assert (data / "places.json").read_bytes() == old and len(restarts) == 2
