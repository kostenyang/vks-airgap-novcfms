"""Create dvportgroup pg-vks-workload (VLAN 0) on vcf-m01-cl01-vds01, copying teaming/security from the management portgroup."""
import os
import ssl, time
from pyVim.connect import SmartConnect
from pyVmomi import vim
si = SmartConnect(host="192.168.120.3", user="administrator@vsphere.local", pwd=os.environ["LAB_PASSWORD"], sslContext=ssl._create_unverified_context())
c = si.content
dvs = [d for d in c.viewManager.CreateContainerView(c.rootFolder, [vim.DistributedVirtualSwitch], True).view if d.name == "vcf-m01-cl01-vds01"][0]
pgs = {p.name: p for p in dvs.portgroup}
print("dvs:", dvs.name, "mtu:", dvs.config.maxMtu, "| portgroups:", sorted(pgs))
if "pg-vks-workload" in pgs:
    print("pg-vks-workload already exists"); raise SystemExit
mgmt = pgs["vcf-m01-cl01-vds01-pg-management"].config.defaultPortConfig
port = vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy(
    vlan=vim.dvs.VmwareDistributedVirtualSwitch.VlanIdSpec(vlanId=0, inherited=False),
    uplinkTeamingPolicy=mgmt.uplinkTeamingPolicy,
    macManagementPolicy=getattr(mgmt, "macManagementPolicy", None))
spec = vim.dvs.DistributedVirtualPortgroup.ConfigSpec(name="pg-vks-workload", type="earlyBinding", numPorts=64,
                                               autoExpand=True, defaultPortConfig=port,
                                               description="VKS primary workload network 192.168.170.0/24 (gw 170.1 on pfSense IP alias)")
t = dvs.AddDVPortgroup_Task([spec])
while t.info.state in ("queued", "running"): time.sleep(1)
print("AddDVPortgroup:", t.info.state, t.info.error.msg if t.info.error else "")
pg = [p for p in dvs.portgroup if p.name == "pg-vks-workload"][0]
tp = pg.config.defaultPortConfig.uplinkTeamingPolicy
print(f"created {pg.name} key={pg.key} vlan={pg.config.defaultPortConfig.vlan.vlanId} "
      f"active={tp.uplinkPortOrder.activeUplinkPort} standby={tp.uplinkPortOrder.standbyUplinkPort}")
