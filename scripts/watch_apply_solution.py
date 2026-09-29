"""After silencing nvmeonhcl: watch vLCM Apply Solution attempts, vSAN NOT_OK lines, and spherelet state on all hosts."""
import os
import ssl, time, datetime, sys, paramiko
sys.path.insert(0, "vks-airgap/scripts")
from vcsa_sh import vcsa
from pyVim.connect import SmartConnect
from pyVmomi import vim
si = SmartConnect(host="192.168.120.3", user="administrator@vsphere.local", pwd=os.environ["LAB_PASSWORD"], sslContext=ssl._create_unverified_context())
cl = si.content.viewManager.CreateContainerView(si.content.rootFolder, [vim.ClusterComputeResource], True).view[0]
H = {h.name: h for h in cl.host}
for h in H.values():
    ss = h.configManager.serviceSystem
    if not [s for s in ss.serviceInfo.service if s.key == "TSM-SSH"][0].running: ss.StartService("TSM-SSH")
def spher(ip):
    c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy()); c.connect(ip, username="root", password=os.environ["LAB_PASSWORD"], timeout=15)
    _, o, _ = c.exec_command("esxcli software vib list 2>/dev/null | grep -c spherelet; ls -la /etc/vmware/spherelet/spherelet.conf 2>/dev/null | awk '{print $5}'; ps -c | grep -c '[s]pherelet'", timeout=60)
    r = o.read().decode().split(); c.close()
    return f"vib={r[0] if r else '?'} conf_bytes={r[1] if len(r)>2 else '-'} procs={r[-1] if r else '?'}"
t0 = time.time()
while time.time() - t0 < 900:
    now = datetime.datetime.now().strftime("%H:%M:%S")
    col = si.content.taskManager.CreateCollectorForTasks(vim.TaskFilterSpec(entity=vim.TaskFilterSpec.ByEntity(entity=cl, recursion="self"),
          time=vim.TaskFilterSpec.ByTime(timeType="queuedTime", beginTime=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=3))))
    ts = col.ReadNextTasks(50); col.DestroyCollector()
    ap = [t for t in ts if "ApplySolution" in str(t.descriptionId)]
    last = max(ap, key=lambda t: t.queueTime) if ap else None
    st = f"{last.state}{(' ' + last.error.msg[:120]) if last and last.error else ''}" if last else "no recent apply task"
    hosts = {n.split('.')[0]: spher({'esx01.alan.lab':'192.168.120.61','esx02.alan.lab':'192.168.120.62','esx03.alan.lab':'192.168.120.63'}[n]) for n in sorted(H)}
    print(f"{now} apply={st} | " + " | ".join(f"{k}:{v}" for k, v in hosts.items()), flush=True)
    if last and last.state == "success": print("APPLY SOLUTION SUCCEEDED"); break
    time.sleep(60)
print(vcsa("grep -h 'returned status: NOT_OK' /var/log/vmware/vmware-updatemgr/vum-server/vmware-vum-server*.log | tail -3 | cut -c1-260; echo; grep -h 'errorMessage' /var/log/vmware/vmware-updatemgr/vum-server/vmware-vum-server*.log | tail -2 | grep -o '\"errorMessage\":\"[^\"]*\"'"))
