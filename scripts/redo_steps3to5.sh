#!/bin/bash
# Redo steps 3-5 (run on admin, DNS air-gap active). Every mutation is preceded by --dry-run=server; abort on dry-run failure.
set -uo pipefail
export KUBECTL_VSPHERE_PASSWORD="${LAB_PASSWORD:?export LAB_PASSWORD first}"
kubectl vsphere login --server=supervisor01.alan.lab --vsphere-username administrator@vsphere.local >/dev/null 2>&1
K="kubectl --context supervisor01.alan.lab"; NS=vmware-system-vks-public; ARI=default-addon-repo-install-3.7.0-20260618
AR=harbor-addonrepository-3.7.0; IMG=harbor.alan.lab/vks/vks-addons:3.7.0-20260618; WK=~/vks-test01.kubeconfig
SKIP=addons.kubernetes.vmware.com/skip-vks-managed-addon-repository-update
dry() { echo "  dry-run: $*"; if ! "$@" --dry-run=server >/tmp/dry.out 2>&1; then echo "  DRY-RUN FAILED: $(cat /tmp/dry.out)"; exit 1; fi; echo "  dry-run ok: $(tail -1 /tmp/dry.out)"; }
state() { echo "$(date -u +%H:%M:%S) ARI.ref=$($K get ari $ARI -n $NS -o jsonpath='{.spec.addonRepositoryRef.name}') | SV.pkgr=[$($K get pkgr vks-addons-3.7.0-20260618 -n $NS -o jsonpath='{.spec.fetch.imgpkgBundle.image} | {.status.friendlyDescription}')] | WL.pkgr=[$(kubectl --kubeconfig $WK get pkgr vks-addons-3.7.0-20260618 -n vmware-system-tkg -o jsonpath='{.spec.fetch.imgpkgBundle.image} | {.status.friendlyDescription}')]"; }

echo "===== STEP 3: negative control — remove skip annotation (product default)"; state
dry $K annotate ari $ARI -n $NS ${SKIP}-
$K annotate ari $ARI -n $NS ${SKIP}-
for i in $(seq 1 24); do sleep 30; s=$(state); echo "$s"
  if [[ "$s" == *"ARI.ref=builtin-addonrepository-3.7.0"* && "$s" == *"SV.pkgr=[projects.packages.broadcom.com"*"failed"* && "$s" == *"WL.pkgr=[projects.packages.broadcom.com"*"failed"* ]]; then echo "  NEGATIVE CONTROL CONFIRMED (both sides fail on the public URL)"; break; fi
done
echo "  SV error: $($K get pkgr vks-addons-3.7.0-20260618 -n $NS -o jsonpath='{.status.usefulErrorMessage}' | tr '\n' ' ' | cut -c1-400)"
echo "  WL error: $(kubectl --kubeconfig $WK get pkgr vks-addons-3.7.0-20260618 -n vmware-system-tkg -o jsonpath='{.status.usefulErrorMessage}' | tr '\n' ' ' | cut -c1-400)"
echo "  workload pkgi (running add-ons during failure window):"; kubectl --kubeconfig $WK get pkgi -A --no-headers | awk '{print "   ",$2,$NF=="" ? "" : ""}' >/dev/null; kubectl --kubeconfig $WK get pkgi -A -o custom-columns=NAME:.metadata.name,DESC:.status.friendlyDescription --no-headers | sed 's/^/    /'

echo "===== STEP 4: delete contaminated AR, recreate clean"
[ "$($K get ari $ARI -n $NS -o jsonpath='{.spec.addonRepositoryRef.name}')" = "$AR" ] && { echo "  ARI still references $AR — abort"; exit 1; }
dry $K delete addonrepository $AR -n $NS
$K delete addonrepository $AR -n $NS
$K get addonrepository builtin-addonrepository-3.7.0 -n $NS -o json | jq --arg n "$AR" --arg img "$IMG" '
  {apiVersion, kind,
   metadata: {name: $n, namespace: .metadata.namespace,
     labels: ((.metadata.labels // {}) | with_entries(select((.key | startswith("kapp.k14s.io")) | not)) | del(."kubernetes.vmware.com/managed-by")),
     annotations: ((.metadata.annotations // {}) | with_entries(select((.key | startswith("kapp.k14s.io")) or .key == "kubectl.kubernetes.io/last-applied-configuration" | not)))},
   spec: (.spec | .fetch.imgpkgBundle.imageURL = $img)}' > ~/rollback/$AR.clean.json
echo "  clean AR: kapp refs=$(grep -c kapp.k14s.io ~/rollback/$AR.clean.json) broadcom refs=$(grep -c packages.broadcom.com ~/rollback/$AR.clean.json) labels=$(jq -c .metadata.labels ~/rollback/$AR.clean.json) annotations=$(jq -c '.metadata.annotations | keys' ~/rollback/$AR.clean.json)"
dry $K create -f ~/rollback/$AR.clean.json
$K create -f ~/rollback/$AR.clean.json

echo "===== STEP 5: skip annotation + repoint ARI; clean my extra AddonConfig annotation"
dry $K annotate ari $ARI -n $NS ${SKIP}=true --overwrite
$K annotate ari $ARI -n $NS ${SKIP}=true --overwrite
dry $K patch ari $ARI -n $NS --type merge -p "{\"spec\":{\"addonRepositoryRef\":{\"name\":\"$AR\",\"namespace\":\"$NS\"}}}"
$K patch ari $ARI -n $NS --type merge -p "{\"spec\":{\"addonRepositoryRef\":{\"name\":\"$AR\",\"namespace\":\"$NS\"}}}"
if $K get addonconfig vks-test01-carvel-repo -n vks-ns01 -o jsonpath='{.metadata.annotations}' | grep -q airgap.alan.lab/reconcile-at; then
  dry $K annotate addonconfig vks-test01-carvel-repo -n vks-ns01 airgap.alan.lab/reconcile-at-
  $K annotate addonconfig vks-test01-carvel-repo -n vks-ns01 airgap.alan.lab/reconcile-at-
fi
for i in $(seq 1 30); do sleep 30; s=$(state); echo "$s"
  if [[ "$s" == *"ARI.ref=$AR"* && "$s" == *"SV.pkgr=[harbor.alan.lab"*"Reconcile succeeded"* && "$s" == *"WL.pkgr=[harbor.alan.lab"*"Reconcile succeeded"* ]]; then echo "  RESTORED ON HARBOR (both sides succeed, DNS air-gap still active)"; break; fi
done
