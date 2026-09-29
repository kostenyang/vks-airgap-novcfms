"""Deploy bastion / harbor / admin Ubuntu 24.04 VMs on the OUTER Xindian vCenter from the cloud-image OVA (cloud-init guestinfo).
harbor/admin: no package_update / packages (air-gap style — software is carried over from bastion)."""
import os
from urllib.parse import quote
import base64, subprocess, ssl, time, sys
from pyVim.connect import SmartConnect
from pyVmomi import vim
OVA = r"E:\iso\ubuntu-24.04-cloudimg.ova"
OVFTOOL = r"C:\Program Files\VMware\VMware OVF Tool\ovftool.exe"
TARGET = f"vi://administrator%40vsphere.local:{quote(os.environ["OUTER_VC_PASSWORD"], safe="")}@192.168.110.32/Xindian%20Datacenter/host/XinDian%20Cluster/192.168.110.16"
PUBKEY = os.environ.get("SSH_PUBKEY", "")
VMS = [  # name, net, ip, gw, dns, cpu, memGB, diskGB, online
    ("bastion", "VM Network",          "192.168.110.86", "192.168.110.254", "192.168.110.85", 2, 4, 200, True),
    ("harbor",  "VCF91-Nested-Trunk",  "192.168.120.80", "192.168.120.1",   "192.168.120.5",  4, 8, 300, False),
    ("admin",   "VCF91-Nested-Trunk",  "192.168.120.81", "192.168.120.1",   "192.168.120.5",  2, 4, 200, False),
]
only = sys.argv[1:]
si = SmartConnect(host="192.168.110.32", user="administrator@vsphere.local", pwd=os.environ["OUTER_VC_PASSWORD"], sslContext=ssl._create_unverified_context())
def vms(): return {v.name: v for v in si.content.viewManager.CreateContainerView(si.content.rootFolder, [vim.VirtualMachine], True).view}
def wait(t):
    while t.info.state in ("queued", "running"): time.sleep(2)
    if t.info.state != "success": raise SystemExit(f"task failed: {t.info.error.msg}")
for name, net, ip, gw, dns, cpu, mem, disk, online in VMS:
    if only and name not in only: continue
    if name in vms(): print(f"{name}: exists, skip deploy")
    else:
        meta = f"""instance-id: {name}-vks-001
local-hostname: {name}
network:
  version: 2
  ethernets:
    id0:
      match: {{name: "e*"}}
      dhcp4: false
      addresses: [{ip}/24]
      nameservers: {{addresses: [{dns}], search: [alan.lab]}}
      routes:
        - {{to: default, via: {gw}}}
"""
        pkgs = "package_update: true\npackages: [git, openssl, jq, curl, wget, python3, sshpass]\n" if online else "package_update: false\n"
        user = f"""#cloud-config
hostname: {name}
fqdn: {name}.alan.lab
ssh_pwauth: true
users:
  - name: ubuntu
    sudo: ALL=(ALL) NOPASSWD:ALL
    groups: [sudo]
    shell: /bin/bash
    lock_passwd: false
    ssh_authorized_keys: [{PUBKEY}]
chpasswd:
  expire: false
  users: [{{name: ubuntu, password: "{os.environ['LAB_PASSWORD']}", type: text}}]
{pkgs}runcmd:
  - [ bash, -lc, "echo network:{{config:disabled}} > /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg" ]
"""
        b = lambda s: base64.b64encode(s.encode()).decode()
        cmd = [OVFTOOL, "--acceptAllEulas", "--noSSLVerify", "--allowExtraConfig", "--diskMode=thin", f"--name={name}",
               "--datastore=Datastore2", f"--net:VM Network={net}",
               f"--extraConfig:guestinfo.metadata={b(meta)}", "--extraConfig:guestinfo.metadata.encoding=base64",
               f"--extraConfig:guestinfo.userdata={b(user)}", "--extraConfig:guestinfo.userdata.encoding=base64", OVA, TARGET]
        print(f"{name}: ovftool deploy -> {net} {ip}")
        r = subprocess.run(cmd, capture_output=True, text=True)
        print("   ", (r.stdout.strip().splitlines() or [""])[-1], r.stderr.strip()[-300:])
        if r.returncode != 0: raise SystemExit(f"{name}: ovftool failed rc={r.returncode}")
    vm = vms()[name]
    if vm.runtime.powerState == "poweredOff":
        d = [x for x in vm.config.hardware.device if isinstance(x, vim.vm.device.VirtualDisk)][0]
        changes = []
        if d.capacityInKB < disk * 1024 * 1024:
            d.capacityInKB = disk * 1024 * 1024
            changes.append(vim.vm.device.VirtualDeviceSpec(operation="edit", device=d))
        wait(vm.ReconfigVM_Task(vim.vm.ConfigSpec(numCPUs=cpu, memoryMB=mem * 1024, deviceChange=changes)))
        wait(vm.PowerOnVM_Task())
    print(f"{name}: {vm.config.hardware.numCPU} vCPU / {vm.config.hardware.memoryMB//1024}GB / disk "
          f"{[x.capacityInKB//2**20 for x in vm.config.hardware.device if isinstance(x, vim.vm.device.VirtualDisk)]}G / {vm.runtime.powerState}")
