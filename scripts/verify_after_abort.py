"""Post-abort verification: installer bring-up state, SDDC Manager tasks/domain, inner vCenter VMs/hosts/vSAN, NSX TNs."""
import os
import sys, json, ssl, base64, urllib.request
sys.path.insert(0, "vks-airgap/scripts")
from installer_api import Api, flatten_errors
from pyVim.connect import SmartConnect
from pyVmomi import vim
ctx = ssl._create_unverified_context()
sid = open("vks-airgap/logs/sddc-id.txt").read().strip()

print("== installer bring-up")
inst = Api()
s, d = inst.req(f"/v1/sddcs/{sid}")
print("  status:", d.get("status"))
for m in d.get("milestones", []): print(f"   {m['name']:50} {m.get('status')}")
bad = [x for x in d["sddcSubTasks"] if "FAIL" in (x.get("status") or "")]
for x in bad[:3]: print("   failed subtask:", x["name"], x["status"], flatten_errors(x.get("errorResponse") or {})[:2])

print("== SDDC Manager 120.4")
sm = Api("https://192.168.120.4", "administrator@vsphere.local", os.environ["LAB_PASSWORD"])
s, doms = sm.req("/v1/domains"); print("  domains:", [(x["name"], x["status"]) for x in doms.get("elements", [])] if s == 200 else (s, doms))
s, hs = sm.req("/v1/hosts"); print("  hosts:", [(x["fqdn"], x["status"]) for x in hs.get("elements", [])] if s == 200 else (s, hs))
s, tk = sm.req("/v1/tasks?pageSize=20")
if s == 200:
    for t in tk.get("elements", [])[:12]:
        print(f"   task {t.get('status'):28} {t.get('name','')[:80]}")
else: print("  tasks:", s, str(tk)[:200])

print("== inner vCenter 120.3")
si = SmartConnect(host="192.168.120.3", user="administrator@vsphere.local", pwd=os.environ["LAB_PASSWORD"], sslContext=ctx)
c = si.content
for vm in sorted(c.viewManager.CreateContainerView(c.rootFolder, [vim.VirtualMachine], True).view, key=lambda v: v.name):
    print(f"   VM {vm.name:40} {vm.runtime.powerState}")
for h in sorted(c.viewManager.CreateContainerView(c.rootFolder, [vim.HostSystem], True).view, key=lambda h: h.name):
    print(f"   host {h.name:18} {h.runtime.connectionState} mm={h.runtime.inMaintenanceMode} status={h.overallStatus}")
for ds in c.viewManager.CreateContainerView(c.rootFolder, [vim.Datastore], True).view:
    print(f"   ds {ds.name:30} {ds.summary.type} free={ds.summary.freeSpace//2**30}G/{ds.summary.capacity//2**30}G")
for cl in c.viewManager.CreateContainerView(c.rootFolder, [vim.ClusterComputeResource], True).view:
    print(f"   cluster {cl.name} status={cl.overallStatus} drs={cl.configurationEx.drsConfig.enabled} ha={cl.configurationEx.dasConfig.enabled}")

print("== NSX 120.11 transport nodes")
auth = "Basic " + base64.b64encode(("admin:" + os.environ["LAB_PASSWORD"]).encode()).decode()
def nsx(p):
    r = urllib.request.Request("https://192.168.120.11" + p, headers={"Authorization": auth})
    with urllib.request.urlopen(r, context=ctx, timeout=60) as x: return json.loads(x.read())
try:
    tns = nsx("/api/v1/transport-nodes")["results"]
    for tn in tns:
        st = nsx(f"/api/v1/transport-nodes/{tn['id']}/state")
        print(f"   TN {tn['display_name']:18} state={st.get('state')} deploy={st.get('node_deployment_state',{}).get('state')}")
    print("   cluster status:", nsx("/api/v1/cluster/status").get("mgmt_cluster_status", {}).get("status"))
except Exception as ex: print("   NSX query failed:", ex)
