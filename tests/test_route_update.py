"""Exercise deployment rollback on synthetic files; never contact a server."""

import importlib.util
import runpy
from pathlib import Path
from types import ModuleType

import pytest


def updater() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "deploy/update_routes.py"
    spec = importlib.util.spec_from_file_location("route_updater", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("fail", [False, True])
@pytest.mark.parametrize("profile", ["routes", "knowledge", "workspace", "data"])
def test_route_release_restores_all_files_on_failure(
    tmp_path: Path, fail: bool, profile: str
) -> None:
    mod = updater()
    if profile != "routes":
        mod.__dict__["FILES"] = runpy.run_path(
            str(Path(__file__).resolve().parents[1] / f"deploy/publish_{profile}.py")
        )["FILES"]
    target = tmp_path / "release"
    records = {}
    old_files = {}
    for name in mod.FILES:
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        added = any(
            part in name
            for part in ("journey.", "knowledge.", "workspace.", "guidance.", "map-discovery.")
        )
        old = None if added else b"SYNTHETIC PREVIOUS FILE"
        if old is not None:
            path.write_bytes(old)
        old_files[name] = old
        records[name] = (mod.digest(old) if old is not None else None, b"SYNTHETIC NEXT FILE")
    # The engine reads this file's metadata as the template for newly added files, so a
    # profile that does not publish it still needs the path to exist.
    template = target / "backend/src/campuspilot/web.py"
    if not template.exists():
        template.parent.mkdir(parents=True, exist_ok=True)
        template.write_bytes(b"SYNTHETIC TEMPLATE FILE")
    checks = []

    def verify(restored: bool = False) -> None:
        checks.append(restored)
        if fail and not restored:
            raise RuntimeError("SYNTHETIC failed health check")

    if fail:
        with pytest.raises(mod.UpdateFailure, match="update_failed_restored"):
            mod.apply(target, records, tmp_path / "backups", verify)
        for name, old in old_files.items():
            assert (target / name).read_bytes() == old if old else not (target / name).exists()
        assert checks == [False, True]
    else:
        identifier = mod.apply(target, records, tmp_path / "backups", verify)
        assert (tmp_path / "backups" / identifier / "manifest.json").exists()
        assert all((target / name).read_bytes() == records[name][1] for name in records)
        assert mod.apply(target, records, tmp_path / "backups", verify) is None


def test_route_release_rejects_drift_before_writing(tmp_path: Path) -> None:
    mod = updater()
    path = tmp_path / "backend/src/campuspilot/web.py"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"SYNTHETIC CONCURRENT EDIT")
    records = {"backend/src/campuspilot/web.py": ("incorrect", b"SYNTHETIC NEXT")}
    with pytest.raises(mod.UpdateFailure, match="remote_drift"):
        mod.apply(tmp_path, records, tmp_path / "backups", lambda: None)
    assert path.read_bytes() == b"SYNTHETIC CONCURRENT EDIT"
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "workspace_provider_search_failed",
            "update_failed_restored:workspace_provider_search_failed",
        ),
        ("SYNTHETIC sensitive response", "update_failed_restored"),
    ],
)
def test_release_failure_exposes_only_safe_phase_codes(
    tmp_path: Path, message: str, expected: str
) -> None:
    mod = updater()
    name = "backend/src/campuspilot/web.py"
    mod.__dict__["FILES"] = (name,)
    path = tmp_path / name
    path.parent.mkdir(parents=True)
    old = b"SYNTHETIC PREVIOUS FILE"
    path.write_bytes(old)

    def verify(restored: bool = False) -> None:
        if not restored:
            raise RuntimeError(message)

    with pytest.raises(mod.UpdateFailure) as failure:
        mod.apply(
            tmp_path, {name: (mod.digest(old), b"SYNTHETIC NEXT")}, tmp_path / "backups", verify
        )
    assert str(failure.value) == expected
    assert path.read_bytes() == old


@pytest.mark.parametrize("profile", ["data"])
def test_data_publisher_probe_reads_the_local_snapshot(profile: str) -> None:
    """The remote probe is the release gate; run it against the real snapshot locally."""
    pytest.importorskip("fastapi")
    from campuspilot.web import create_web_app  # noqa: PLC0415
    from fastapi.testclient import TestClient  # noqa: PLC0415

    root = Path(__file__).resolve().parents[1]
    module = runpy.run_path(str(root / f"deploy/publish_{profile}.py"))
    namespace: dict[str, object] = {"PLAN_SHA256": module["PLAN_SHA256"]}
    exec(module["VERIFY"], namespace)  # noqa: S102
    app = create_web_app(data_dir=root / "data" / "cdut")
    with TestClient(app) as client:
        namespace["verify_data"](client)  # type: ignore[operator]
