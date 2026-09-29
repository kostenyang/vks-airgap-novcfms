#!/bin/bash
# Bastion (internet side): install Docker from the official repo, and stage an offline bundle for the air-gapped side:
#   ~/airgap/docker-debs/*.deb  +  ~/airgap/harbor-offline-installer-<ver>.tgz
set -euo pipefail
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release; echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update -qq
PKGS="containerd.io docker-ce docker-ce-cli docker-buildx-plugin docker-compose-plugin"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $PKGS >/dev/null
sudo usermod -aG docker ubuntu
mkdir -p ~/airgap/docker-debs && cd ~/airgap/docker-debs && apt-get download $PKGS 2>&1 | tail -1
echo "docker debs:"; ls -1 ~/airgap/docker-debs
VER=$(curl -fsSL https://api.github.com/repos/goharbor/harbor/releases/latest | jq -r .tag_name)
echo "harbor latest: $VER"
cd ~/airgap
[ -f harbor-offline-installer-$VER.tgz ] || curl -fsSL -o harbor-offline-installer-$VER.tgz https://github.com/goharbor/harbor/releases/download/$VER/harbor-offline-installer-$VER.tgz
curl -fsSL -o harbor-offline-installer-$VER.tgz.asc https://github.com/goharbor/harbor/releases/download/$VER/harbor-offline-installer-$VER.tgz.asc 2>/dev/null || true
ls -la ~/airgap; docker --version; docker compose version
sha256sum ~/airgap/docker-debs/*.deb ~/airgap/harbor-offline-installer-*.tgz > ~/airgap/SHA256SUMS
