#!/bin/bash
# Bastion: fetch CLI tools (kept as files under ~/airgap/tools for the air-gapped side too) + list VKr / standard-package versions.
set -euo pipefail
mkdir -p ~/airgap/tools && cd ~/airgap/tools
gh_latest() { curl -fsSL https://api.github.com/repos/$1/releases/latest | jq -r .tag_name; }
V_IMG=$(gh_latest carvel-dev/imgpkg); V_YQ=$(gh_latest mikefarah/yq); V_GOVC=$(gh_latest vmware/govmomi)
[ -f imgpkg ] || curl -fsSL -o imgpkg https://github.com/carvel-dev/imgpkg/releases/download/$V_IMG/imgpkg-linux-amd64
[ -f yq ] || curl -fsSL -o yq https://github.com/mikefarah/yq/releases/download/$V_YQ/yq_linux_amd64
[ -f govc.tgz ] || curl -fsSL -o govc.tgz https://github.com/vmware/govmomi/releases/download/$V_GOVC/govc_Linux_x86_64.tar.gz
tar xzf govc.tgz govc; chmod +x imgpkg yq govc
sudo install imgpkg yq govc /usr/local/bin/
echo "tools: imgpkg $V_IMG | yq $V_YQ | govc $V_GOVC"; imgpkg version | head -1; yq --version; govc version
echo "===== VKr catalog (wp-content.broadcom.com/v2/latest)"
curl -fsSL https://wp-content.broadcom.com/v2/latest/items.json -o ~/airgap/vkr-items.json
jq -r '.items[].name' ~/airgap/vkr-items.json | sort -V | tail -25
echo "total items: $(jq '.items|length' ~/airgap/vkr-items.json)"
echo "===== vks-standard-packages versions"
curl -fsSL "https://projects.packages.broadcom.com/api/v2.0/projects/vsphere/repositories?q=name=~vks-standard-packages&page_size=50" | jq -r '.[].name' | sort -V | tail -10 || echo "harbor API listing not public"
