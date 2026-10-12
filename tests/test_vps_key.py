"""SSH setup policies use synthetic configurations and never contact a server."""

import importlib.util
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "vps_key_setup", Path(__file__).resolve().parents[1] / "deploy/enable_vps_key.py"
)
assert SPEC and SPEC.loader
KEY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(KEY)
SYNTHETIC = b"# SYNTHETIC SSH CONFIG FOR TESTS\nPort 22\nPubkeyAuthentication no\n"
BEFORE = {
    "pubkeyauthentication": "no",
    "passwordauthentication": "yes",
    "permitrootlogin": "yes",
    "authenticationmethods": "any",
    "authorizedkeysfile": ".ssh/authorized_keys .ssh/authorized_keys2",
    "pubkeyacceptedalgorithms": "ssh-ed25519,rsa-sha2-512",
    "port": "22",
}
CONTEXT = "user=root,host=192.0.2.10,addr=192.0.2.10,laddr=192.0.2.20,lport=22"


def test_root_rule_preserves_globals_and_other_user_sections() -> None:
    other = b"Match User synthetic-user\n    AllowTcpForwarding no\n"
    changed = KEY.candidate_config(SYNTHETIC + other, BEFORE)
    assert changed.startswith(SYNTHETIC) and changed.endswith(other)
    assert changed.index(b"Match User root") < changed.index(b"Match User synthetic-user")
    assert b"PasswordAuthentication" not in changed and b"PermitRootLogin" not in changed
    assert b"    PubkeyAuthentication yes\n" in changed


@pytest.mark.parametrize("methods", ["password,publickey", "publickey,publickey"])
def test_multi_factor_authentication_is_never_weakened(methods: str) -> None:
    with pytest.raises(KEY.KeySetupFailure, match="custom_authentication_policy"):
        KEY.candidate_config(SYNTHETIC, {**BEFORE, "authenticationmethods": methods})


def test_password_only_policy_gets_two_alternatives_not_two_required_factors() -> None:
    changed = KEY.candidate_config(SYNTHETIC, {**BEFORE, "authenticationmethods": "password"})
    assert b"AuthenticationMethods publickey password\n" in changed
    assert b"AuthenticationMethods publickey,password" not in changed


def test_disabled_key_file_is_enabled_only_inside_root_rule() -> None:
    changed = KEY.candidate_config(SYNTHETIC, {**BEFORE, "authorizedkeysfile": "none"})
    assert b"Match User root\n" in changed
    assert b"    AuthorizedKeysFile .ssh/authorized_keys\n" in changed


def test_existing_password_login_and_private_key_algorithm_must_be_preserved() -> None:
    for delta, reason in (
        ({"passwordauthentication": "no"}, "existing_password_login"),
        ({"permitrootlogin": "prohibit-password"}, "existing_password_login"),
        ({"pubkeyacceptedalgorithms": "rsa-sha2-512"}, "deployment_key_algorithm"),
    ):
        with pytest.raises(KEY.KeySetupFailure, match=reason):
            KEY.candidate_config(SYNTHETIC, {**BEFORE, **delta})


def fixture_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = tmp_path / "sshd_config.synthetic"
    config.write_bytes(SYNTHETIC)
    # Unix root ownership is not present in Windows fixtures; all other logic runs.
    monkeypatch.setattr(
        KEY, "read_config", lambda path: (path.read_bytes(), {"mode": 0o600, "uid": 0, "gid": 0})
    )
    return config


Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def fake_runner(
    after: dict[str, str], *, syntax_fail: bool = False, reload_fail: bool = False
) -> tuple[Runner, list[list[str]]]:
    calls: list[list[str]] = []
    settings_count = 0
    reload_count = 0

    def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal settings_count, reload_count
        calls.append(arguments)
        if "-T" in arguments:
            values = BEFORE if settings_count == 0 else after
            settings_count += 1
            return subprocess.CompletedProcess(
                arguments, 0, "\n".join(f"{k} {v}" for k, v in values.items())
            )
        if "-t" in arguments:
            return subprocess.CompletedProcess(arguments, int(syntax_fail), "")
        assert arguments == ["systemctl", "reload", "ssh.service"]
        reload_count += 1
        return subprocess.CompletedProcess(arguments, int(reload_fail and reload_count == 1), "")

    return run, calls


def test_syntax_failure_never_writes_config_or_reloads_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = fixture_config(tmp_path, monkeypatch)
    runner, calls = fake_runner({**BEFORE, "pubkeyauthentication": "yes"}, syntax_fail=True)
    with pytest.raises(KEY.KeySetupFailure, match="ssh_config_syntax_failed"):
        KEY.configure_root_auth(config, tmp_path / "backups", CONTEXT, runner)
    assert config.read_bytes() == SYNTHETIC
    assert not (tmp_path / "backups").exists()
    assert all("systemctl" not in call for call in calls)


@pytest.mark.parametrize("delta", [{"port": "2222"}, {"passwordauthentication": "no"}])
def test_unrelated_or_password_effective_change_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delta: dict[str, str]
) -> None:
    config = fixture_config(tmp_path, monkeypatch)
    runner, calls = fake_runner({**BEFORE, "pubkeyauthentication": "yes", **delta})
    with pytest.raises(KEY.KeySetupFailure, match="ssh_change_exceeds_root_auth_scope"):
        KEY.configure_root_auth(config, tmp_path / "backups", CONTEXT, runner)
    assert config.read_bytes() == SYNTHETIC
    assert all("systemctl" not in call for call in calls)


def test_reload_failure_restores_original_and_preserves_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = fixture_config(tmp_path, monkeypatch)
    runner, calls = fake_runner({**BEFORE, "pubkeyauthentication": "yes"}, reload_fail=True)
    with pytest.raises(KEY.KeySetupFailure, match="old_config_restored"):
        KEY.configure_root_auth(config, tmp_path / "backups", CONTEXT, runner)
    assert config.read_bytes() == SYNTHETIC
    assert next((tmp_path / "backups").glob("*/sshd_config")).read_bytes() == SYNTHETIC
    assert sum("systemctl" in call for call in calls) == 2


def test_success_keeps_old_file_and_enables_only_root_key_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = fixture_config(tmp_path, monkeypatch)
    runner, calls = fake_runner({**BEFORE, "pubkeyauthentication": "yes"})
    backup = KEY.configure_root_auth(config, tmp_path / "backups", CONTEXT, runner)
    assert backup and (backup / "sshd_config").read_bytes() == SYNTHETIC
    assert config.read_bytes().startswith(SYNTHETIC)
    assert b"Match User root" in config.read_bytes()
    assert sum("systemctl" in call for call in calls) == 1
