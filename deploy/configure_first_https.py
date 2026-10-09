"""Consume encrypted-transport stdin to configure this first installation only."""

import base64
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path


def main() -> None:
    domain = sys.argv[1]
    if domain != "campuspilot.38-244-61-184.sslip.io":
        raise SystemExit("Only the approved first hostname may be configured")
    settings = json.loads(base64.b64decode(sys.stdin.buffer.read(4096), validate=True))
    for key in ("AMAP_JS_KEY", "AMAP_SECURITY_JS_CODE"):
        if not re.fullmatch(r"[0-9a-fA-F]{32}", settings.get(key, "")):
            raise SystemExit("Invalid Amap credential shape")
    password = settings.get("visitor_password", "")
    if not re.fullmatch(r"[!-~]{12,72}", password):
        raise SystemExit("Invalid visitor password shape")
    env_path = Path("/etc/campuspilot/campuspilot.env")
    gateway_env = env_path.with_name("gateway.env")
    old_stat = env_path.lstat()
    if not stat.S_ISREG(old_stat.st_mode) or old_stat.st_uid != 0:
        raise SystemExit("Expected a root-owned regular backend environment file")
    if gateway_env.exists():
        raise SystemExit("Gateway credentials already exist; refusing to replace them")
    original = env_path.read_text()
    if "PUBLIC_ORIGIN=" in original:
        raise SystemExit("Backend origin already configured; use the existing deployment")
    caddy = "/opt/campuspilot/tooling/caddy/caddy"
    hashed = (
        subprocess.run(
            [caddy, "hash-password", "--algorithm", "bcrypt", "--bcrypt-cost", "12"],
            input=(password + "\n").encode(),
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )
    if not hashed.startswith("$2"):
        raise SystemExit("Unexpected visitor password hash")
    gateway_values = {
        "CAMPUSPILOT_DOMAIN": domain,
        "CAMPUSPILOT_VISITOR_USER": "campuspilot",
        "CAMPUSPILOT_VISITOR_HASH": hashed,
    }
    validation_env = (
        os.environ
        | gateway_values
        | {
            "XDG_DATA_HOME": "/var/lib/campuspilot-gateway",
            "XDG_CONFIG_HOME": "/var/lib/campuspilot-gateway",
        }
    )
    subprocess.run(
        [
            "runuser",
            "-u",
            "campuspilot-gateway",
            "--",
            caddy,
            "validate",
            "--config",
            "/opt/campuspilot/gateway/Caddyfile",
            "--adapter",
            "caddyfile",
        ],
        env=validation_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=True,
    )
    backup = env_path.with_name("campuspilot.env.before_https")
    with backup.open("x") as stream:
        stream.write(original)
    backup.chmod(0o600)
    lines = original.splitlines()
    for key in ("AMAP_JS_KEY", "AMAP_SECURITY_JS_CODE"):
        lines = [line for line in lines if not line.startswith(key + "=")]
        lines.append(key + "=" + settings[key])
    lines.append("PUBLIC_ORIGIN=https://" + domain)
    # Parent directory is 0700; atomically replace rather than exposing a partial file.
    temporary = env_path.with_name("campuspilot.env.new")
    with temporary.open("x") as stream:
        stream.write("\n".join(lines) + "\n")
    temporary.chmod(0o600)
    fd = os.open(gateway_env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.writelines(f"{key}={value}\n" for key, value in gateway_values.items())
    temporary.replace(env_path)
    shutil.copymode(backup, env_path)
    print("Backend origin, Amap settings and independent gateway hash configured.")


if __name__ == "__main__":
    main()
