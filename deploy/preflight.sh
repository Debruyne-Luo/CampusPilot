#!/usr/bin/env bash
# Read-only inventory. Does not print environment variables or authentication files.
set -u
printf '\n[os]\n'
uname -a
cat /etc/os-release
printf '\n[resources]\n'
free -m
df -h / /var /tmp
printf '\n[listen sockets]\n'
ss -lntup
printf '\n[running services]\n'
systemctl list-units --type=service --state=running --no-pager
printf '\n[existing web configuration paths only]\n'
for item in /etc/caddy/Caddyfile /etc/nginx/nginx.conf /opt/campuspilot /etc/campuspilot; do
    if [ -e "$item" ]; then ls -ld "$item"; fi
done
printf '\n[runtimes]\n'
command -v python3 || true
command -v uv || true
command -v caddy || true
printf '\n[clock]\n'
date -u
