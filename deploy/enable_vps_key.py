"""Enable the requested root deployment key without disabling password login."""

import hashlib
import ipaddress
import os
import re
import stat
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

BEGIN = "# CampusPilot root key authentication begin"
END = "# CampusPilot root key authentication end"
AUTH_FIELDS = {"pubkeyauthentication", "authenticationmethods", "authorizedkeysfile"}


class KeySetupFailure(Exception):
    """Only controlled diagnostics reach the terminal."""


def run_command(arguments):
    try:
        return subprocess.run(arguments, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        raise KeySetupFailure("ssh_command_unavailable") from None


def root_context():
    peer = os.environ.get("SSH_CONNECTION", "").split()
    if len(peer) != 4:
        raise KeySetupFailure("missing_ssh_connection")
    try:
        remote, local = str(ipaddress.ip_address(peer[0])), str(ipaddress.ip_address(peer[2]))
        if not 1 <= int(peer[3]) <= 65535:
            raise ValueError()
    except ValueError:
        raise KeySetupFailure("invalid_ssh_connection") from None
    return f"user=root,host={remote},addr={remote},laddr={local},lport={peer[3]}"


def settings(path, context, runner):
    result = runner(["/usr/sbin/sshd", "-T", "-f", str(path), "-C", context])
    if result.returncode:
        raise KeySetupFailure("ssh_config_unreadable")
    return dict(line.split(" ", 1) for line in result.stdout.splitlines() if " " in line)


def candidate_config(raw, current):
    if current.get("passwordauthentication") != "yes" or current.get("permitrootlogin") != "yes":
        raise KeySetupFailure("existing_password_login_not_preserved")
    methods = current.get("authenticationmethods")
    if methods not in {"any", "password", "publickey password", "password publickey"}:
        raise KeySetupFailure("custom_authentication_policy_requires_review")
    keys = current.get("authorizedkeysfile", "")
    if not re.fullmatch(r"[A-Za-z0-9_./%~ -]{1,512}", keys):
        raise KeySetupFailure("custom_authorized_keys_path_requires_review")
    key_paths = keys.split()
    has_path = ".ssh/authorized_keys" in key_paths or "/root/.ssh/authorized_keys" in key_paths
    if current.get("pubkeyauthentication") == "yes" and methods != "password" and has_path:
        return raw
    if BEGIN.encode() in raw or END.encode() in raw:
        raise KeySetupFailure("existing_deployment_auth_rule_changed")
    if "ssh-ed25519" not in current.get("pubkeyacceptedalgorithms", "").split(","):
        raise KeySetupFailure("deployment_key_algorithm_not_enabled")
    body = [BEGIN, "Match User root", "    PubkeyAuthentication yes"]
    if methods == "password":
        body.append("    AuthenticationMethods publickey password")
    if not has_path:
        prior = "" if keys == "none" else keys + " "
        body.append("    AuthorizedKeysFile " + prior + ".ssh/authorized_keys")
    body.append(END)
    # Put the root rule before existing Match sections, leaving all globals intact.
    match = re.search(rb"(?im)^[ \t]*Match[ \t]+", raw)
    position = match.start() if match else len(raw)
    prefix, suffix = raw[:position], raw[position:]
    separator = b"\n" if prefix and not prefix.endswith(b"\n") else b""
    return prefix + separator + ("\n".join(body) + "\n").encode() + suffix


def read_config(path):
    if path.is_symlink() or not path.is_file():
        raise KeySetupFailure("ssh_config_not_regular")
    info = path.stat()
    if info.st_uid != 0 or info.st_size > 1_000_000 or stat.S_IMODE(info.st_mode) & 0o022:
        raise KeySetupFailure("unexpected_ssh_config_permissions")
    return path.read_bytes(), {
        "mode": stat.S_IMODE(info.st_mode),
        "uid": info.st_uid,
        "gid": info.st_gid,
    }


def write_atomic(path, data, metadata):
    fd, temporary = tempfile.mkstemp(prefix=".campuspilot-ssh-", dir=path.parent)
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


def configure_root_auth(config, backup_root, context, runner=run_command):
    original, metadata = read_config(config)
    before = settings(config, context, runner)
    incoming = candidate_config(original, before)
    if incoming == original:
        if runner(["/usr/sbin/sshd", "-t", "-f", str(config)]).returncode:
            raise KeySetupFailure("ssh_config_syntax_failed")
        if runner(["systemctl", "reload", "ssh.service"]).returncode:
            raise KeySetupFailure("ssh_reload_failed")
        return None
    fd, temporary = tempfile.mkstemp(prefix=".campuspilot-ssh-check-", dir=config.parent)
    preview = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(incoming)
        if runner(["/usr/sbin/sshd", "-t", "-f", str(preview)]).returncode:
            raise KeySetupFailure("ssh_config_syntax_failed")
        after = settings(preview, context, runner)
        changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
        if changed - AUTH_FIELDS or after.get("pubkeyauthentication") != "yes":
            raise KeySetupFailure("ssh_change_exceeds_root_auth_scope")
        if after.get("authenticationmethods") not in {
            "any",
            "publickey password",
            "password publickey",
        }:
            raise KeySetupFailure("key_authentication_not_enabled")
        if read_config(config)[0] != original:
            raise KeySetupFailure("ssh_config_changed_during_setup")
        if backup_root.is_symlink() or backup_root.resolve() != backup_root:
            raise KeySetupFailure("invalid_ssh_backup_directory")
        backup_root.mkdir(mode=0o700, exist_ok=True)
        backup_root.chmod(0o700)
        backup = backup_root / (
            datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        )
        backup.mkdir(mode=0o700)
        saved = backup / "sshd_config"
        saved.write_bytes(original)
        saved.chmod(0o600)
        write_atomic(config, incoming, metadata)
        if runner(["systemctl", "reload", "ssh.service"]).returncode:
            # Keep the already authenticated session and recover the old configuration.
            if hashlib.sha256(config.read_bytes()).digest() != hashlib.sha256(incoming).digest():
                raise KeySetupFailure("ssh_config_changed_after_reload_failure")
            write_atomic(config, original, metadata)
            if runner(["systemctl", "reload", "ssh.service"]).returncode:
                raise KeySetupFailure("ssh_reload_failed_old_config_restored")
            raise KeySetupFailure("ssh_reload_failed_old_config_restored")
        return backup
    finally:
        preview.unlink(missing_ok=True)


def enable_root_key_authentication():
    try:
        if os.geteuid() != 0:
            raise KeySetupFailure("root_required")
        backup = configure_root_auth(
            Path("/etc/ssh/sshd_config"), Path("/opt/campuspilot/ssh-backups"), root_context()
        )
        print("Root public-key authentication enabled; existing password login preserved.")
        if backup:
            print("Private SSH configuration backup: " + str(backup))
    except KeySetupFailure as error:
        raise SystemExit("SSH key setup stopped: " + str(error)) from None
    except OSError:
        raise SystemExit("SSH key setup stopped: ssh_config_io_failed") from None
