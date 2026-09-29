#!/bin/bash
# Redo step 2: with DNS air-gap active since T0, prove Supervisor + workload vks-addons pkgr keep reconciling (updatedAt > T0).
T0=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "T0=$T0 (DNS air-gap active)"
export KUBECTL_VSPHERE_PASSWORD="${LAB_PASSWORD:?export LAB_PASSWORD first}"; NS=vmware-system-vks-public; WK=~/vks-test01.kubeconfig
for i in $(seq 1 16); do
  kubectl vsphere login --server=supervisor01.alan.lab --vsphere-username administrator@vsphere.local >/dev/null 2>&1
  S=$(kubectl --context supervisor01.alan.lab get pkgr vks-addons-3.7.0-20260618 -n $NS -o jsonpath='{.status.fetch.updatedAt}|{.status.friendlyDescription}|{.spec.fetch.imgpkgBundle.image}')
  W=$(kubectl --kubeconfig $WK get pkgr vks-addons-3.7.0-20260618 -n vmware-system-tkg -o jsonpath='{.status.fetch.updatedAt}|{.status.friendlyDescription}|{.spec.fetch.imgpkgBundle.image}')
  bad=$(kubectl --kubeconfig $WK get pkgi -A --no-headers 2>/dev/null | grep -vc "Reconcile succeeded")
  echo "$(date -u +%H:%M:%S) SV[$S] WL[$W] wl-pkgi-not-succeeded=$bad"
  s_upd=${S%%|*}; w_upd=${W%%|*}
  if [[ "$s_upd" > "$T0" && "$w_upd" > "$T0" && "$S" == *"Reconcile succeeded"* && "$W" == *"Reconcile succeeded"* ]] && [ $i -ge 13 ]; then echo "STEP2 PASS: both re-fetched after T0 while air-gapped"; break; fi
  sleep 120
done
