#!/usr/bin/env bash
# 讓這台主機(含 docker 容器)只能連私有網段,模擬 air-gap
#   主機本身:OUTPUT;容器:DOCKER-USER(docker 的 FORWARD 會先跳這條鏈)
set -euo pipefail
for CH in OUTPUT DOCKER-USER; do
  iptables -N AIRGAP-$CH 2>/dev/null || iptables -F AIRGAP-$CH
  iptables -A AIRGAP-$CH -d 127.0.0.0/8    -j RETURN
  iptables -A AIRGAP-$CH -d 10.0.0.0/8     -j RETURN
  iptables -A AIRGAP-$CH -d 172.16.0.0/12  -j RETURN
  iptables -A AIRGAP-$CH -d 192.168.0.0/16 -j RETURN
  iptables -A AIRGAP-$CH -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  iptables -A AIRGAP-$CH -j REJECT
  iptables -C $CH -j AIRGAP-$CH 2>/dev/null || iptables -I $CH 1 -j AIRGAP-$CH
done
echo "air-gap egress block active"
