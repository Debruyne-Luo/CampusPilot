#!/usr/bin/env bash
# Prepare a new Ubuntu host; does not switch the Pages origin or deploy application code.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo 'Run as root' >&2; exit 1; }
BASE=/opt/campuspilot
install -d -m 755 "$BASE/tooling" "$BASE/python" "$BASE/releases"
install -d -m 700 /etc/campuspilot
if ! id campuspilot >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/campuspilot --shell /usr/sbin/nologin campuspilot
fi
install -d -m 700 -o campuspilot -g campuspilot /var/lib/campuspilot
if [ "$(awk '/SwapTotal:/ {print $2}' /proc/meminfo)" -eq 0 ]; then
  [ ! -e /campuspilot.swap ] || { echo 'Inspect existing inactive swap file first' >&2; exit 1; }
  fallocate -l 1G /campuspilot.swap
  chmod 600 /campuspilot.swap
  mkswap /campuspilot.swap >/dev/null
  swapon /campuspilot.swap
  printf '/campuspilot.swap none swap sw 0 0\n' >> /etc/fstab
  printf 'vm.swappiness=10\n' > /etc/sysctl.d/90-campuspilot-swap.conf
  sysctl -w vm.swappiness=10
fi
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl ca-certificates gnupg
if ! command -v caddy >/dev/null; then
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key -o "$BASE/tooling/caddy.gpg.asc"
  gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    "$BASE/tooling/caddy.gpg.asc"
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    -o /etc/apt/sources.list.d/caddy-stable.list
  chmod 644 /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq caddy
fi
if [ ! -x "$BASE/tooling/uv" ]; then
  curl -fsSL https://astral.sh/uv/0.12.19/install.sh -o "$BASE/tooling/install-uv.sh"
  UV_UNMANAGED_INSTALL="$BASE/tooling" sh "$BASE/tooling/install-uv.sh"
fi
UV_PYTHON_INSTALL_DIR="$BASE/python" "$BASE/tooling/uv" python install 3.14.7
if [ ! -x "$BASE/venv/bin/python" ]; then
  UV_PYTHON_INSTALL_DIR="$BASE/python" "$BASE/tooling/uv" venv --python 3.14.7 "$BASE/venv"
fi
chmod -R a+rX "$BASE/python"
"$BASE/venv/bin/python" --version
"$BASE/tooling/uv" --version
caddy version
free -m
