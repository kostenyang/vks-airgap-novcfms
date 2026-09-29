"""Minimal vCenter REST (/api) client with session auth."""
import os
import json, ssl, base64, urllib.request
CTX = ssl._create_unverified_context()
class VC:
    def __init__(self, host="192.168.120.3", user="administrator@vsphere.local", pw=os.environ["LAB_PASSWORD"]):
        self.base = f"https://{host}"
        r = urllib.request.Request(self.base + "/api/session", method="POST",
            headers={"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()})
        with urllib.request.urlopen(r, context=CTX, timeout=60) as x: self.sid = json.loads(x.read())
    def req(self, path, method="GET", body=None, timeout=120):
        r = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                   headers={"vmware-api-session-id": self.sid, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, context=CTX, timeout=timeout) as x:
                t = x.read().decode(); return x.status, (json.loads(t) if t else {})
        except urllib.error.HTTPError as e:
            t = e.read().decode()
            try: return e.code, json.loads(t)
            except Exception: return e.code, t[:1500]
