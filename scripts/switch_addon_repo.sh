#!/bin/bash
# Run on admin (logged in to Supervisor): point VKS 3.7.0 add-on repository at the local Harbor instead of projects.packages.broadcom.com.
set -euo pipefail
export KUBECTL_VSPHERE_PASSWORD="${LAB_PASSWORD:?export LAB_PASSWORD first}"
kubectl vsphere login --server=supervisor01.alan.lab --vsphere-username administrator@vsphere.local >/dev/null 2>&1
kubectl config use-context supervisor01.alan.lab >/dev/null
NS=vmware-system-vks-public; NEW=harbor-addonrepository-3.7.0; ARI=default-addon-repo-install-3.7.0-20260618
IMG=harbor.alan.lab/vks/vks-addons:3.7.0-20260618
imgpkg tag list -i harbor.alan.lab/vks/vks-addons | grep -qE '^3.7.0-20260618[[:space:]]*$' || { echo "image not in harbor yet"; exit 1; }
mkdir -p ~/rollback && kubectl get ari $ARI -n $NS -o yaml > ~/rollback/ari-$ARI.orig.yaml && echo "backup: ~/rollback/ari-$ARI.orig.yaml"
# 1. new AddonRepository = copy of builtin, only name + imageURL changed
kubectl get addonrepository builtin-addonrepository-3.7.0 -n $NS -o json | jq --arg n "$NEW" --arg img "$IMG" '
  del(.status, .metadata.uid, .metadata.resourceVersion, .metadata.creationTimestamp, .metadata.generation, .metadata.managedFields, .metadata.ownerReferences, .metadata.finalizers)
  | .metadata.name = $n | .spec.fetch.imgpkgBundle.imageURL = $img
  | .metadata.labels = ((.metadata.labels // {}) | del(."kubernetes.vmware.com/managed-by"))' > ~/rollback/$NEW.json
kubectl apply -f ~/rollback/$NEW.json
kubectl get addonrepository -n $NS -o custom-columns=NAME:.metadata.name,IMAGE:.spec.fetch.imgpkgBundle.imageURL
# 2. repoint the install
kubectl patch ari $ARI -n $NS --type merge -p "{\"metadata\":{\"annotations\":{\"addons.kubernetes.vmware.com/preferred-repository\":\"$NEW\"}},\"spec\":{\"addonRepositoryRef\":{\"name\":\"$NEW\",\"namespace\":\"$NS\"}}}"
# 3. watch for 3 min (did VKS revert it? did it reconcile?)
for i in $(seq 1 9); do sleep 20
  echo "$(date +%T) $(kubectl get ari $ARI -n $NS -o json | jq -r '"ref=\(.spec.addonRepositoryRef.name) ready=\([.status.conditions[]? | select(.type=="Ready")][0].status) pkgr=\([.status.conditions[]? | select(.type=="PackageRepositoryReconciled")][0] | "\(.status) \(.reason) \(.message // "" | .[0:160])")"')"
done
echo "== Supervisor-side PackageRepository"; kubectl get packagerepository -n $NS -o custom-columns=NAME:.metadata.name,IMG:.spec.fetch.imgpkgBundle.image,DESC:.status.friendlyDescription
