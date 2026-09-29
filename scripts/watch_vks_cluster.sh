#!/bin/bash
# Run on admin: poll vks-test01 until Available/all machines Running, or 45 min. Re-login every loop (token TTL).
export KUBECTL_VSPHERE_PASSWORD="${LAB_PASSWORD:?export LAB_PASSWORD first}"
last=""
for i in $(seq 1 90); do
  kubectl vsphere login --server=supervisor01.alan.lab --vsphere-username administrator@vsphere.local >/dev/null 2>&1
  kubectl config use-context vks-ns01 >/dev/null
  c=$(kubectl get cluster vks-test01 -n vks-ns01 -o json 2>/dev/null)
  phase=$(echo "$c" | jq -r .status.phase); avail=$(echo "$c" | jq -r '[.status.conditions[]? | select(.type=="Available")][0].status')
  m=$(kubectl get machines -n vks-ns01 -o json | jq -r '[.items[] | "\(.metadata.name|sub("vks-test01-";""))=\(.status.phase // "?")"] | join(" ")')
  vm=$(kubectl get vm -n vks-ns01 -o json 2>/dev/null | jq -r '[.items[] | "\(.metadata.name|sub("vks-test01-";""))=\(.status.powerState // "?")/\(.status.network.primaryIP4 // "-")"] | join(" ")')
  cur="phase=$phase available=$avail | machines: $m | vms: $vm"
  [ "$cur" != "$last" ] && echo "$(date +%T) $cur" && last="$cur"
  if [ "$avail" = "True" ] && ! echo "$m" | grep -qv "Running" ; then
    if echo "$m" | grep -q "Running" && [ "$(echo "$m" | tr ' ' '\n' | grep -vc '=Running')" = "0" ]; then echo "$(date +%T) CLUSTER AVAILABLE"; break; fi
  fi
  sleep 30
done
echo "== conditions"; kubectl get cluster vks-test01 -n vks-ns01 -o json | jq -r '.status.conditions[]? | select(.status!="True") | "\(.type)=\(.status) \(.reason // "") \(.message // "" | .[0:200])"' | head -15
