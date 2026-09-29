"""Poll Supervisor enablement until RUNNING/READY, a stable ERROR, or timeout. Logs status changes, messages and new VMs."""
import os
import sys, time, json, ssl, datetime
sys.path.insert(0, "vks-airgap/scripts")
from vc_rest import VC
from pyVim.connect import SmartConnect
from pyVmomi import vim
LOG = open("vks-airgap/logs/09-supervisor-enable.log", "a", encoding="utf-8")
def log(*a):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} " + " ".join(str(x) for x in a); print(line, flush=True); LOG.write(line + "\n"); LOG.flush()
vc = VC(); si = SmartConnect(host="192.168.120.3", user="administrator@vsphere.local", pwd=os.environ["LAB_PASSWORD"], sslContext=ssl._create_unverified_context())
BASE_VMS = {"vcsa", "sddc", "nsx01"}
last = None; seen_vms = set(); t0 = time.time(); err_streak = 0
while time.time() - t0 < 7200:
    try:
        s, r = vc.req("/api/vcenter/namespace-management/supervisors/summaries")
        if s == 401: vc = VC(); continue
        it = r["items"][0]["info"]
        s2, cl = vc.req("/api/vcenter/namespace-management/clusters/domain-c9")
        msgs = [m.get("details", {}).get("default_message") or json.dumps(m)[:200] for m in (cl.get("messages") or [])] if s2 == 200 else []
        cur = (it["config_status"], it["kubernetes_status"], tuple(msgs))
        if cur != last:
            log(f"config={it['config_status']} k8s={it['kubernetes_status']} api_ep={cl.get('api_server_cluster_endpoint') if s2 == 200 else '?'}")
            for m in msgs: log("   msg:", m[:300])
            last = cur
        vms = {v.name: v.runtime.powerState for v in si.content.viewManager.CreateContainerView(si.content.rootFolder, [vim.VirtualMachine], True).view}
        new = {n: p for n, p in vms.items() if n not in BASE_VMS and n not in seen_vms}
        for n, p in new.items(): log("   new VM:", n, p); seen_vms.add(n)
        if it["config_status"] == "RUNNING" and it["kubernetes_status"] == "READY":
            log("SUPERVISOR RUNNING / READY"); break
        err_streak = err_streak + 1 if it["config_status"] == "ERROR" else 0
        if err_streak >= 15:
            log("config_status ERROR for 15 consecutive polls — stopping watcher (not touching anything)"); break
    except Exception as ex:
        log("poll error:", ex)
    time.sleep(60)
else:
    log("TIMEOUT after 2h")
