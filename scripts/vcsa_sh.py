"""Run a bash snippet on the VCSA as root. root's login shell is appliancesh, so: open a pty, type 'shell', then run
the base64-decoded script and read until an end marker."""
import os
import paramiko, base64, sys, time, re
def vcsa(cmd, host="192.168.120.3", pw=os.environ["LAB_PASSWORD"], timeout=300):
    c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy()); c.connect(host, username="root", password=pw, timeout=15)
    ch = c.invoke_shell(width=400, height=100); time.sleep(2); ch.recv(65536)
    ch.send("shell\n"); time.sleep(2); ch.recv(65536)
    b = base64.b64encode(cmd.encode()).decode()
    ch.send(f"echo {b} | base64 -d > /tmp/_c.sh; echo ===BEGIN===; bash /tmp/_c.sh 2>&1; echo ===END===\n")
    buf, t0 = "", time.time()
    while time.time() - t0 < timeout:
        if ch.recv_ready():
            buf += ch.recv(65536).decode(errors="replace")
            if buf.count("===END===") >= 2: break
        else: time.sleep(0.5)
    c.close()
    m = re.search(r"===BEGIN===\r?\n(.*)\r?\n===END===", buf.split("; echo ===END===", 1)[-1], re.S)
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", m.group(1) if m else buf).strip()
if __name__ == "__main__":
    print(vcsa(sys.argv[1]))
