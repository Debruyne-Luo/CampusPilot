#!/usr/bin/env bash
# First HTTPS activation; all paths and units are specific to CampusPilot.
set -euo pipefail
umask 077
domain=${1:?Supply the approved hostname}
if [ "$(id -u)" -ne 0 ] || [ "$(uname -m)" != x86_64 ]; then
    echo 'Root on amd64 is required.' >&2; exit 1
fi
if [ "$domain" != campuspilot.38-244-61-184.sslip.io ]; then
    echo 'Unapproved first hostname.' >&2; exit 1
fi
if [ -e /etc/systemd/system/campuspilot-gateway.service ] || [ -e /etc/campuspilot/gateway.env ]; then
    echo 'Existing gateway found; use its update/recovery procedure.' >&2; exit 1
fi
if ss -lnt | awk '{print $4}' | grep -Eq '(^|:)(80|443)$'; then
    echo 'Ports 80/443 are occupied; no existing service was stopped.' >&2; exit 1
fi
systemctl is-active --quiet campuspilot.service
install -d -m 0755 /opt/campuspilot/tooling/caddy /opt/campuspilot/gateway
package=/opt/campuspilot/tooling/caddy/caddy_2.11.7_linux_amd64.tar.gz
curl --proto '=https' --tlsv1.2 -fLsS --retry 2 \
    https://github.com/caddyserver/caddy/releases/download/v2.11.7/caddy_2.11.7_linux_amd64.tar.gz -o "$package"
printf '%s  %s\n' 727b91701a392de6ebc5027509f548bf39979e5216340d0faed8fa5e69c84f8b "$package" | sha256sum --check --status
tar -xzf "$package" -C /opt/campuspilot/tooling/caddy caddy
chmod 0755 /opt/campuspilot/tooling/caddy/caddy
if ! id campuspilot-gateway >/dev/null 2>&1; then
    useradd --system --home-dir /var/lib/campuspilot-gateway --shell /usr/sbin/nologin campuspilot-gateway
fi
install -d -o campuspilot-gateway -g campuspilot-gateway -m 0700 /var/lib/campuspilot-gateway
if [ -e /opt/campuspilot/gateway/Caddyfile ]; then
    echo 'Gateway config already exists; refusing to replace it.' >&2; exit 1
fi
cat > /opt/campuspilot/gateway/Caddyfile <<'CADDY'
{
    admin off
}
import /opt/campuspilot/current/deploy/Caddyfile.campuspilot
CADDY
chmod 0644 /opt/campuspilot/gateway/Caddyfile
# The inherited pipe supplies a bounded, base64 JSON payload; credentials are never echoed.
python3 /opt/campuspilot/current/deploy/configure_first_https.py "$domain"
systemd-analyze verify /opt/campuspilot/current/deploy/campuspilot-gateway.service
install -m 0644 /opt/campuspilot/current/deploy/campuspilot-gateway.service /etc/systemd/system/campuspilot-gateway.service
systemctl daemon-reload
systemctl restart campuspilot.service
curl --fail --silent --show-error --retry 5 --retry-connrefused --retry-delay 1 \
    -H "Host: $domain" http://127.0.0.1:8766/healthz
systemctl enable --now campuspilot-gateway.service
printf '\nWaiting up to 60 seconds for the public HTTPS certificate...\n'
ready=0
for attempt in $(seq 1 12); do
    if curl --fail --silent --show-error --max-time 4 "https://$domain/healthz"; then
        ready=1; break
    fi
    sleep 1
done
if [ "$ready" -ne 1 ]; then
    echo 'Gateway started, but public HTTPS is not verified yet. Check its journal and firewall; do not rerun the first installer.' >&2
    exit 1
fi
status=$(curl --silent --show-error --max-time 10 -o /dev/null -w '%{http_code}' "https://$domain/")
if [ "$status" != 401 ]; then
    systemctl stop campuspilot-gateway.service
    echo 'Expected visitor authentication challenge; public acceptance failed.' >&2; exit 1
fi
status=$(curl --silent --show-error --max-time 10 -o /dev/null -w '%{http_code}' \
    -H 'Content-Type: application/json' --data '{"query":"synthetic-install-check"}' "https://$domain/v1/directory/places/search")
if [ "$status" != 401 ]; then
    systemctl stop campuspilot-gateway.service
    echo 'Expected independent tool authentication; public acceptance failed.' >&2; exit 1
fi
printf '\nHTTPS READY: https://%s\nVisitor username: campuspilot\n' "$domain"
printf 'Existing nginx, sing-box and argo services were not changed. Dify remains to be configured.\n'
