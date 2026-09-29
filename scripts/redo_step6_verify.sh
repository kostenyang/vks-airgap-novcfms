#!/bin/bash
# Redo step 6: full verification while the DNS air-gap is still active (run on admin).
export KUBECTL_VSPHERE_PASSWORD="${LAB_PASSWORD:?export LAB_PASSWORD first}"
kubectl vsphere login --server=supervisor01.alan.lab --vsphere-username administrator@vsphere.local >/dev/null 2>&1
K="kubectl --context supervisor01.alan.lab"; NS=vmware-system-vks-public; ARI=default-addon-repo-install-3.7.0-20260618; AR=harbor-addonrepository-3.7.0; WK=~/vks-test01.kubeconfig
echo "== 0. air-gap still active?"; printf "  dig example.org @120.5 -> [%s]  curl broadcom -> %s  harbor -> %s\n" "$(dig +short +time=3 +tries=1 @192.168.120.5 example.org | head -1)" "$(curl -m 8 -s -o /dev/null -w %{http_code} https://projects.packages.broadcom.com/v2/)" "$(curl -m 8 -s -o /dev/null -w %{http_code} https://harbor.alan.lab/v2/)"
echo "== 1. ARI"; $K get ari $ARI -n $NS -o json | jq -r '"  ref=\(.spec.addonRepositoryRef.name) skip=\(.metadata.annotations["addons.kubernetes.vmware.com/skip-vks-managed-addon-repository-update"]) preferred=\(.metadata.annotations["addons.kubernetes.vmware.com/preferred-repository"])", (.status.conditions[] | "  \(.type)=\(.status) \(.reason)")'
echo "== 2. clean AR"; printf "  kapp.k14s.io refs: %s | packages.broadcom.com refs: %s | image: %s\n" "$($K get addonrepository $AR -n $NS -o json | grep -c kapp.k14s.io)" "$($K get addonrepository $AR -n $NS -o json | grep -c packages.broadcom.com)" "$($K get addonrepository $AR -n $NS -o jsonpath='{.spec.fetch.imgpkgBundle.imageURL}')"
echo "== 3. PackageRepositories"; $K get pkgr -n $NS -o custom-columns=NAME:.metadata.name,IMAGE:.spec.fetch.imgpkgBundle.image,DESC:.status.friendlyDescription,UPDATED:.status.fetch.updatedAt | sed 's/^/  SV /'
kubectl --kubeconfig $WK get pkgr -A -o custom-columns=NAME:.metadata.name,IMAGE:.spec.fetch.imgpkgBundle.image,DESC:.status.friendlyDescription,UPDATED:.status.fetch.updatedAt | sed 's/^/  WL /'
echo "== 4. workload PackageInstalls not succeeded:"; kubectl --kubeconfig $WK get pkgi -A --no-headers | grep -v "Reconcile succeeded" | sed 's/^/  /' || true; echo "  (count: $(kubectl --kubeconfig $WK get pkgi -A --no-headers | grep -vc 'Reconcile succeeded'))"
echo "== 5. controller log (last 30m)"; CM=$($K get deploy -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{"\n"}{end}' | grep tanzu-addons-controller-manager | head -1)
$K logs -n ${CM%/*} deploy/${CM#*/} --since=30m 2>/dev/null | grep -E "skipped updating AddonRepositoryRef|Selected regular AddonRepository|ARISkipAnnotation" | tail -3 | cut -c1-260 | sed 's/^/  /'
echo "== 6. internet references in objects"; printf "  Supervisor app,pkgr,addonrepository -> %s lines mention packages.broadcom.com (expect only builtin AR)\n" "$($K get app,pkgr,addonrepository -A -o json | grep -c packages.broadcom.com)"
$K get addonrepository -A -o json | jq -r '.items[] | select(tostring|test("packages.broadcom.com")) | "    from: \(.metadata.name)"'
printf "  Workload app,pkgr -> %s lines mention packages.broadcom.com (expect 0)\n" "$(kubectl --kubeconfig $WK get app,pkgr -A -o json | grep -c packages.broadcom.com)"
echo "== 7. image registry set (containers + initContainers)"
allow='^(localhost:5000/|docker-registry\.kube-system\.svc:5000/|vmware/|etcd:|harbor\.alan\.lab/)'
for c in SV WL; do if [ $c = SV ]; then KK="$K"; else KK="kubectl --kubeconfig $WK"; fi
  $KK get pods -A -o json | jq -r '.items[].spec | ((.containers // []) + (.initContainers // []))[].image' | sort -u > /tmp/img-$c.txt
  echo "  $c registries: $(sed -E 's#^([^/]+)/.*#\1#; s#^(etcd):.*#\1:*#' /tmp/img-$c.txt | sort -u | tr '\n' ' ')"
  echo "  $c images outside allow-list: $(grep -vE "$allow" /tmp/img-$c.txt | tr '\n' ' ' || true)"; done
