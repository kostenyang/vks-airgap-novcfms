#!/bin/bash
# Bastion: download VKr OVF items (latest Photon-5 per minor) + VKS Standard Packages bundle into ~/airgap for transfer.
set -euo pipefail
BASE=https://wp-content.broadcom.com/v2/latest
ITEMS="ob-25650988-photon-5-amd64-v1.36.2---vmware.2-vkr.3 ob-25653794-photon-5-amd64-v1.35.6---vmware.2-vkr.3 ob-25677161-photon-5-amd64-v1.34.9---vmware.2-vkr.4"
STDPKG=projects.packages.broadcom.com/vsphere/supervisor/vks-standard-packages/3.6.0-20260211/vks-standard-packages:3.6.0-20260211
mkdir -p ~/airgap/vkr && cd ~/airgap/vkr
for it in $ITEMS; do
  mkdir -p "$it"
  for href in $(jq -r --arg n "$it" '.items[] | select(.name==$n) | .files[].hrefs[0]' ~/airgap/vkr-items.json); do
    f="$it/$(basename "$href")"
    if [ -f "$f" ]; then echo "exists $f"; continue; fi
    echo "$(date +%T) get $f"; curl -fsSL --retry 3 -o "$f.part" "$BASE/$href" && mv "$f.part" "$f"
  done
done
echo "$(date +%T) VKr done:"; du -sh ~/airgap/vkr/*
cd ~/airgap
if [ ! -f vks-standard-packages-3.6.0-20260211.tar ]; then
  echo "$(date +%T) imgpkg copy standard packages -> tar"
  imgpkg copy -b "$STDPKG" --to-tar vks-standard-packages-3.6.0-20260211.tar --cosign-signatures 2>&1 | tail -3
fi
ls -la ~/airgap/*.tar
cd ~/airgap && find vkr -type f -name '*' ! -name '*.part' | sort | xargs sha256sum > SHA256SUMS.vks && sha256sum vks-standard-packages-*.tar >> SHA256SUMS.vks
echo "$(date +%T) ALL DONE"; du -sh ~/airgap
