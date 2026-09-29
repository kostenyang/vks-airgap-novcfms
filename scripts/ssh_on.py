"""Start TSM-SSH on esx01-03 (host-direct API) and report state."""
import os
import ssl, sys
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
ctx = ssl._create_unverified_context()
for n, ip in (("esx01","192.168.120.61"),("esx02","192.168.120.62"),("esx03","192.168.120.63")):
    si = SmartConnect(host=ip, user="root", pwd=os.environ["LAB_PASSWORD"], sslContext=ctx)
    h = si.content.viewManager.CreateContainerView(si.content.rootFolder, [vim.HostSystem], True).view[0]
    ss = h.configManager.serviceSystem
    if "--check" not in sys.argv and not [s for s in ss.serviceInfo.service if s.key == "TSM-SSH"][0].running:
        ss.StartService("TSM-SSH")
    ss.RefreshServices()
    print(f"{n}: TSM-SSH running={[s for s in ss.serviceInfo.service if s.key=='TSM-SSH'][0].running}")
    Disconnect(si)
