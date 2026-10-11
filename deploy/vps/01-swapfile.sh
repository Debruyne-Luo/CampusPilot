#!/usr/bin/env bash
# One-time: 1 GB swapfile for a 1 vCPU / ~1 GB RAM Ubuntu 24.04 VPS. Run as root. Not run by CI.
set -euo pipefail
if swapon --show | grep -q /swapfile; then echo "swap already active"; exit 0; fi
fallocate -l 1G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
sysctl -w vm.swappiness=10
echo 'vm.swappiness=10' > /etc/sysctl.d/90-campuspilot-swap.conf
free -h
