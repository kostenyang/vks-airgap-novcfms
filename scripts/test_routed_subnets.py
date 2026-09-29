"""Empirically test which existing dcxd subnets are routable from a nested VLAN-0 portgroup (pg-vks-workload).
On esx01: temp netstack 'vkstest' + vmk on pg-vks-workload; for each candidate subnet set IP + default gw (dcxd .1),
then vmkping the gateway (L2), vcsa 120.3 and depot 110.85 (routed through pfSense). Cleans up afterwards."""
import os
import ssl, time, paramiko
from pyVim.connect import SmartConnect
from pyVmomi import vim
CANDIDATES = [("192.168.130.209", "192.168.130.1"), ("192.168.150.209", "192.168.150.1")]
TARGETS = ["192.168.120.3", "192.168.110.85", "192.168.120.1"]

ssh = paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.120.61", username="root", password=os.environ["LAB_PASSWORD"], timeout=15)
def sh(cmd):
    _, o, e = ssh.exec_command(cmd); return (o.read().decode() + e.read().decode()).strip()

si = SmartConnect(host="192.168.120.3", user="administrator@vsphere.local", pwd=os.environ["LAB_PASSWORD"], sslContext=ssl._create_unverified_context())
c = si.content
h = [x for x in c.viewManager.CreateContainerView(c.rootFolder, [vim.HostSystem], True).view if x.name == "esx01.alan.lab"][0]
dvs = [d for d in c.viewManager.CreateContainerView(c.rootFolder, [vim.DistributedVirtualSwitch], True).view if d.name == "vcf-m01-cl01-vds01"][0]
pg = [p for p in dvs.portgroup if p.name == "pg-vks-workload"][0]
ns = h.configManager.networkSystem

print(sh("esxcli network ip netstack add -N vkstest 2>&1; esxcli network ip netstack list | grep -A1 vkstest | head -2"))
dev = None
try:
    ip0, gw0 = CANDIDATES[0]
    spec = vim.host.VirtualNic.Specification(ip=vim.host.IpConfig(dhcp=False, ipAddress=ip0, subnetMask="255.255.255.0"),
        distributedVirtualPort=vim.dvs.PortConnection(switchUuid=dvs.uuid, portgroupKey=pg.key), netStackInstanceKey="vkstest", mtu=1500)
    dev = ns.AddVirtualNic(portgroup="", nic=spec); print("temp vmk:", dev)
    for ip, gw in CANDIDATES:
        ns.UpdateVirtualNic(dev, vim.host.VirtualNic.Specification(ip=vim.host.IpConfig(dhcp=False, ipAddress=ip, subnetMask="255.255.255.0")))
        sh("esxcli network ip route ipv4 remove -N vkstest -n default -g 192.168.130.1 2>/dev/null; esxcli network ip route ipv4 remove -N vkstest -n default -g 192.168.150.1 2>/dev/null")
        print(sh(f"esxcli network ip route ipv4 add -N vkstest -n default -g {gw} && echo route-ok"))
        time.sleep(3)
        print(f"===== {ip}  gw {gw}")
        for t in [gw] + TARGETS:
            r = sh(f"vmkping -S vkstest -c 3 -W 2 {t} 2>&1 | grep -E 'packets transmitted|Unknown|No route|sendto'")
            print(f"   -> {t:16} {r}")
finally:
    if dev:
        ns.RemoveVirtualNic(dev); print("removed", dev)
    time.sleep(2)
    print(sh("esxcli network ip netstack remove -N vkstest && echo netstack-removed"))
    ssh.close()
