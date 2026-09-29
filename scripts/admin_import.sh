#!/bin/bash
# Admin host (air-gapped side): trust vCenter CA, import VKr OVF items into content library 'vks-kr-local' with govc,
# and push the VKS Standard Packages bundle into Harbor project 'vks' with imgpkg.
# Expects ~/vks/ copied from bastion:  vkr/<item>/{*.ovf,*.vmdk,*.mf,*.cert}, vks-standard-packages-*.tar, SHA256SUMS.vks
set -euo pipefail
PW="${LAB_PASSWORD:?export LAB_PASSWORD first}"
cd ~/vks && sha256sum -c SHA256SUMS.vks | tail -8
# 1. vCenter CA (from the vCenter itself — no internet)
if ! ls /usr/local/share/ca-certificates/vcsa-*.crt >/dev/null 2>&1; then
  curl -fsSk https://vcsa.alan.lab/certs/download.zip -o /tmp/vc-certs.zip
  rm -rf /tmp/vc-certs && mkdir /tmp/vc-certs && cd /tmp/vc-certs && python3 -c "import zipfile;zipfile.ZipFile('/tmp/vc-certs.zip').extractall('.')"
  i=0; for c in certs/lin/*.0; do sudo cp "$c" /usr/local/share/ca-certificates/vcsa-$i.crt; i=$((i+1)); done
  sudo update-ca-certificates >/dev/null; cd ~/vks
fi
curl -fsS -o /dev/null -w "vCenter TLS verified: HTTP %{http_code}\n" https://vcsa.alan.lab/ui/
# 2. VKr -> content library
export GOVC_URL=https://vcsa.alan.lab GOVC_USERNAME=administrator@vsphere.local GOVC_PASSWORD="$PW"
govc library.info vks-kr-local | grep -E 'Name|Type|Items' || true
for d in ~/vks/vkr/*/; do
  item=$(basename "$d"); ovf=$(ls "$d"*.ovf)
  if govc library.ls "vks-kr-local/$item" 2>/dev/null | grep -q .; then echo "exists: $item"; continue; fi
  echo "$(date +%T) import $item"; govc library.import -n "$item" vks-kr-local "$ovf"
done
govc library.ls "vks-kr-local/*"
# 3. standard packages -> Harbor
curl -fsS -u "admin:$PW" https://harbor.alan.lab/api/v2.0/projects?name=vks | grep -q '"name":"vks"' || \
  curl -fsS -u "admin:$PW" -H 'Content-Type: application/json' -X POST https://harbor.alan.lab/api/v2.0/projects \
       -d '{"project_name":"vks","metadata":{"public":"true"}}' && echo "harbor project vks ready"
echo "$PW" | docker login harbor.alan.lab -u admin --password-stdin >/dev/null
for t in ~/vks/vks-standard-packages-*.tar; do
  echo "$(date +%T) imgpkg push $(basename $t)"
  imgpkg copy --tar "$t" --to-repo harbor.alan.lab/vks/vks-standard-packages --cosign-signatures 2>&1 | tail -3
done
curl -fsS -u "admin:$PW" "https://harbor.alan.lab/api/v2.0/projects/vks/repositories?page_size=100" | jq -r '.[] | "\(.name) artifacts=\(.artifact_count)"' | head -40
echo "repo count: $(curl -fsS -u "admin:$PW" 'https://harbor.alan.lab/api/v2.0/projects/vks/summary' | jq .repo_count)"
