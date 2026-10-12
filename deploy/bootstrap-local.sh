#!/usr/bin/env bash
# First installation only: loopback service, preserving existing public services.
set -euo pipefail
# Source and interpreter files must be readable by the dedicated unprivileged service.
# Secret files below still use explicit 0600 modes inside the private 0700 directory.
umask 022
archive=${1:?Supply archive path}
expected=${2:?Supply locally verified SHA256}
uv_bin=${CAMPUSPILOT_UV_BIN:-/root/.local/bin/uv}
if [ "$(id -u)" -ne 0 ]; then echo 'Root required for first installation.' >&2; exit 1; fi
if [ -e /opt/campuspilot/current ] || [ -e /etc/systemd/system/campuspilot.service ]; then
    echo 'Existing installation found; use release/rollback procedure.' >&2; exit 1
fi
if [ ! -x "$uv_bin" ]; then echo 'Install uv separately first.' >&2; exit 1; fi
if ss -lnt | awk '{print $4}' | grep -Eq '(^|:)8766$'; then
    echo 'Port 8766 is already used.' >&2; exit 1
fi
actual=$(sha256sum "$archive" | cut -d ' ' -f 1)
if [ "$actual" != "$expected" ]; then echo 'Archive checksum mismatch.' >&2; exit 1; fi
if [ -e /etc/campuspilot/campuspilot.env ]; then
    echo 'Existing credential file found; no changes made.' >&2; exit 1
fi
release=/opt/campuspilot/releases/$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 0755 "$release" /opt/campuspilot/tooling
python3 - "$archive" "$release" <<'PY'
import hashlib, json, pathlib, sys, zipfile
archive, destination = sys.argv[1:]
with zipfile.ZipFile(archive) as z:
    manifest = json.loads(z.read('release-manifest.json'))['files_sha256']
    if set(z.namelist()) != set(manifest) | {'release-manifest.json'}:
        raise SystemExit('Archive manifest membership mismatch')
    if sum(i.file_size for i in z.infolist()) > 20_000_000:
        raise SystemExit('Archive too large')
    for entry in z.infolist():
        path = pathlib.PurePosixPath(entry.filename)
        if path.is_absolute() or '..' in path.parts or ':' in entry.filename:
            raise SystemExit('Unsafe archive path')
        if (entry.external_attr >> 16) & 0o170000 == 0o120000:
            raise SystemExit('Archive symlinks rejected')
        content = z.read(entry)
        if entry.filename in manifest and hashlib.sha256(content).hexdigest() != manifest[entry.filename]:
            raise SystemExit('File checksum mismatch')
    z.extractall(destination)
PY
# Keep the managed interpreter outside /root for the service's ProtectHome boundary.
export UV_PYTHON_INSTALL_DIR=/opt/campuspilot/tooling/python
export UV_CACHE_DIR=/opt/campuspilot/tooling/cache
export UV_PROJECT_ENVIRONMENT="$release/.venv"
"$uv_bin" sync --project "$release" --locked --extra api --no-dev --python 3.14.7
"$release/.venv/bin/python" - "$release/data/cdut" <<'PY'
from pathlib import Path
import sys
from campuspilot.directory.repository import DirectoryRepository
DirectoryRepository.load(Path(sys.argv[1]))
PY
if ! id campuspilot >/dev/null 2>&1; then
    useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin campuspilot
fi
install -d -m 0700 /etc/campuspilot
python3 - <<'PY'
import os, secrets
content = 'CAMPUSPILOT_DATA_DIR=/opt/campuspilot/current/data/cdut\n'
content += 'CAMPUSPILOT_API_TOKEN=' + secrets.token_urlsafe(40) + '\n'
content += 'CAMPUSPILOT_DAILY_CHAT_LIMIT=100\nDIFY_API_BASE_URL=https://api.dify.ai/v1\n'
content += 'DIFY_API_KEY=\nDIFY_STRUCTURED_ANSWERS=0\nAMAP_JS_KEY=\nAMAP_SECURITY_JS_CODE=\n'
fd = os.open('/etc/campuspilot/campuspilot.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write(content)
PY
ln -s "$release" /opt/campuspilot/current
systemd-analyze verify "$release/deploy/campuspilot.service"
install -m 0644 "$release/deploy/campuspilot.service" /etc/systemd/system/campuspilot.service
systemctl daemon-reload
systemctl enable --now campuspilot.service
sleep 2
curl --fail --silent --show-error --retry 5 --retry-connrefused --retry-delay 1 http://127.0.0.1:8766/healthz
printf '\nLoopback service installed. Configure credentials locally; HTTPS/domain still required.\n'
printf 'Existing nginx, sing-box and tunnels were not changed.\n'
