"""Watch the VCF bring-up and abort it the moment M5 (VCF Management Platform / VSP) starts real work.
Trigger: subtask 'Deploy VCF Management Services via SDDC Manager' (or the Monitor task after it) leaves NOT_STARTED.
Abort: installer `systemctl stop domainmanager` -> SDDC Manager `systemctl restart domainmanager` (kills the VSP task)
       -> destroy any VSP/VCFMS VMs on the inner vCenter -> installer `systemctl start domainmanager`.
If the bring-up FAILS before the trigger, only report — never run abort actions.
Usage: python abort_watcher.py <sddc-id> [--dry-run]
"""
import os
import sys, time, json, datetime, ssl
sys.path.insert(0, "vks-airgap/scripts")
from installer_api import Api, flatten_errors
from installer_root import run_root

SID = sys.argv[1]; DRY = "--dry-run" in sys.argv
TRIGGERS = ("Deploy VCF Management Services via SDDC Manager", "Monitor VCF Management Services Deployment Task")
IDLE = {None, "", "NOT_STARTED", "PENDING", "SCHEDULED", "INITIALIZED"}
VM_PATTERNS = ("vsp01", "vcf-services-runtime-template", "vcfms", "vcfops", "proxy", "license", "identity-broker")
LOG = open("vks-airgap/logs/04-abort-watcher.log", "a", encoding="utf-8")
def log(*a):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} " + " ".join(str(x) for x in a)
    print(line, flush=True); LOG.write(line + "\n"); LOG.flush()

def destroy_vsp_vms():
    from pyVim.connect import SmartConnect
    from pyVmomi import vim
    si = SmartConnect(host="192.168.120.3", user="administrator@vsphere.local", pwd=os.environ["LAB_PASSWORD"], sslContext=ssl._create_unverified_context())
    c = si.content
    vms = [v for v in c.viewManager.CreateContainerView(c.rootFolder, [vim.VirtualMachine], True).view
           if any(v.name.startswith(p) for p in VM_PATTERNS)]
    log("VSP/VCFMS-looking VMs found:", [v.name for v in vms] or "none")
    for v in vms:
        if DRY: log("  [dry-run] would destroy", v.name); continue
        try:
            if v.runtime.powerState == "poweredOn":
                t = v.PowerOffVM_Task()
                while t.info.state in ("queued", "running"): time.sleep(2)
            t = v.Destroy_Task()
            while t.info.state in ("queued", "running"): time.sleep(2)
            log("  destroyed", v.name, t.info.state)
        except Exception as ex:
            log("  destroy failed", v.name, ex)

api = Api()
last = {}; last_run = None
log(f"watching sddc {SID} dry_run={DRY}")
while True:
    s, d = api.req(f"/v1/sddcs/{SID}")
    if s != 200:
        log("GET failed", s, str(d)[:200]); time.sleep(20); continue
    ms = {m["name"]: m.get("status") for m in d.get("milestones", [])}
    if ms != last:
        log("milestones:", json.dumps(ms, ensure_ascii=False)); last = ms
    subs = d.get("sddcSubTasks", [])
    running = [x["name"] for x in subs if x.get("status") == "IN_PROGRESS"]
    if running and running != last_run: log("  running:", running[:3]); last_run = running
    hit = [x for x in subs if x["name"] in TRIGGERS and x.get("status") not in IDLE]
    if hit:
        log(">>> TRIGGER:", [(x["name"], x["status"]) for x in hit]); break
    failed = [x for x in subs if "FAIL" in (x.get("status") or "")]
    if d.get("status") in ("COMPLETED_WITH_FAILURE", "FAILED") or failed:
        log("!!! bring-up FAILED before trigger — NOT aborting. status:", d.get("status"))
        for x in failed[:5]:
            log("   failed subtask:", x["name"], x.get("status"), flatten_errors(x.get("errorResponse") or {})[:3])
        sys.exit(2)
    time.sleep(10)

# ---- abort sequence
log("step 1: stop domainmanager on installer 120.2")
if not DRY: log(run_root("192.168.120.2", "systemctl stop domainmanager; systemctl is-active domainmanager"))
log("step 2: restart domainmanager on SDDC Manager 120.4 (kills in-flight VSP task)")
if not DRY: log(run_root("192.168.120.4", "systemctl restart domainmanager; sleep 5; systemctl is-active domainmanager"))
log("step 3: wait 60s, then destroy any VSP/VCFMS VMs on inner vCenter")
time.sleep(60); destroy_vsp_vms()
log("step 4: start domainmanager on installer again")
if not DRY: log(run_root("192.168.120.2", "systemctl start domainmanager; sleep 5; systemctl is-active domainmanager"))
log("ABORT COMPLETE")
