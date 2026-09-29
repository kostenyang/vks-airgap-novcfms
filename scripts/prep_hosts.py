"""Apply the 6 nested-vSAN advanced settings + verify vmk0 carries only the Management tag on esx01-03."""
import os
import paramiko
SETTINGS = {"/LSOM/VSANDeviceMonitoring": 0, "/LSOM/lsomSlowDeviceUnmount": 0, "/VSAN/SwapThickProvisionDisabled": 1,
            "/VSAN/Vsan2ZdomCompZstd": 0, "/VSAN/FakeSCSIReservations": 1, "/VSAN/GuestUnmap": 1}
HOSTS = {"esx01": "192.168.120.61", "esx02": "192.168.120.62", "esx03": "192.168.120.63"}
for n, ip in HOSTS.items():
    c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username="root", password=os.environ["LAB_PASSWORD"], timeout=15)
    cmd = "; ".join(f"esxcli system settings advanced set -o {k} -i {v}" for k, v in SETTINGS.items())
    cmd += "; " + "; ".join(f"echo -n '{k}='; esxcli system settings advanced list -o {k} | awk '/Int Value:/{{print $3; exit}}'" for k in SETTINGS)
    cmd += "; echo -n 'vmk0 tags: '; esxcli network ip interface tag get -i vmk0"
    _, o, e = c.exec_command(cmd)
    print(f"===== {n}\n{o.read().decode()}{e.read().decode()}"); c.close()
