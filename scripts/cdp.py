"""Persistent headless-Chrome CDP driver for the vSphere Client.
  python cdp.py start                 # launch chrome (if not running) + SSO login to vcsa
  python cdp.py nav <url> [settle]    # navigate
  python cdp.py eval "<js>"           # evaluate JS, print JSON result
  python cdp.py evalf <file.js>       # evaluate JS file
  python cdp.py shot <path.png>       # screenshot
  python cdp.py dump                  # dump visible form controls / buttons / headings (wizard inspection)
"""
import json, sys, time, base64, socket, subprocess, os, urllib.request
import websocket
PORT = 9222
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = os.path.join(os.environ["TEMP"], "cdp-vks-9222")
RULES = "MAP vcsa.alan.lab 192.168.120.3, MAP sddc.alan.lab 192.168.120.4, MAP nsx01.alan.lab 192.168.120.11"
SHOTS = r"C:\Users\mjalan\Documents\vspher8to9\vks-airgap\shots"

def running():
    s = socket.socket(); s.settimeout(1)
    try: s.connect(("127.0.0.1", PORT)); return True
    except Exception: return False
    finally: s.close()

def start_chrome():
    if running(): return
    args = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--no-sandbox",
            "--ignore-certificate-errors", "--hide-scrollbars", "--window-size=1600,1100", f"--remote-debugging-port={PORT}",
            f"--user-data-dir={PROFILE}", f"--host-resolver-rules={RULES}", "about:blank"]
    subprocess.Popen(args, creationflags=0x00000008 | 0x00000200, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        if running(): time.sleep(2); return
        time.sleep(1)
    raise SystemExit("chrome did not start")

class Cdp:
    def __init__(self):
        pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
        pg = [p for p in pages if p["type"] == "page"][0]
        self.ws = websocket.create_connection(pg["webSocketDebuggerUrl"], timeout=120, suppress_origin=True); self.i = 0
    def call(self, method, params=None):
        self.i += 1; self.ws.send(json.dumps({"id": self.i, "method": method, "params": params or {}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.i: return m
    def eval(self, js):
        r = self.call("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True})
        res = r.get("result", {})
        if "exceptionDetails" in res: return {"__exception__": res["exceptionDetails"].get("exception", {}).get("description", str(res["exceptionDetails"]))[:500]}
        return res.get("result", {}).get("value")
    def nav(self, url, settle=6):
        self.call("Page.navigate", {"url": url})
        for _ in range(60):
            if self.eval("document.readyState") == "complete": break
            time.sleep(1)
        time.sleep(settle); return self.eval("location.href")
    def shot(self, path):
        if not os.path.isabs(path): path = os.path.join(SHOTS, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        d = self.call("Page.captureScreenshot", {"format": "png"})["result"]["data"]
        open(path, "wb").write(base64.b64decode(d)); return path

DUMP_JS = r"""
(() => {
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const lab = e => { if (e.id) { const l = document.querySelector(`label[for="${e.id}"]`); if (l) return l.innerText.trim(); }
    const w = e.closest('clr-input-container,clr-select-container,clr-radio-wrapper,clr-checkbox-wrapper,clr-password-container,.clr-form-control,clr-textarea-container,label');
    return w ? w.innerText.trim().split('\n')[0].slice(0, 80) : (e.getAttribute('aria-label') || e.name || ''); };
  const root = document.querySelector('.modal-dialog, clr-wizard, .wizard, [role=dialog]') || document.body;
  const out = {title: (root.querySelector('h1,h2,h3,.modal-title,.clr-wizard-title,.wizard-page-title')||{}).innerText, steps: [], fields: [], buttons: [], errors: []};
  root.querySelectorAll('.clr-wizard-stepnav-item, .wizard-stepnav-item, clr-wizard-stepnav-item').forEach(s => out.steps.push((s.className.includes('active')?'>':' ')+s.innerText.trim().replace(/\s+/g,' ').slice(0,60)));
  root.querySelectorAll('input,select,textarea').forEach(e => { if (!vis(e) && e.type!=='radio' && e.type!=='checkbox') return;
    out.fields.push({tag:e.tagName, type:e.type, id:e.id, name:e.name, label:lab(e), value: e.type==='password'?'***':(e.type==='checkbox'||e.type==='radio'?e.checked:e.value),
      options: e.tagName==='SELECT' ? [...e.options].map(o=>o.text.trim()).slice(0,15) : undefined, disabled:e.disabled}); });
  root.querySelectorAll('button').forEach(b => { if (vis(b) && b.innerText.trim()) out.buttons.push(b.innerText.trim().slice(0,40) + (b.disabled?' [disabled]':'')); });
  root.querySelectorAll('.clr-subtext.clr-error, .alert-text, .clr-error .clr-subtext, .error, [class*=error-message]').forEach(e => { if (vis(e) && e.innerText.trim()) out.errors.push(e.innerText.trim().slice(0,200)); });
  return out;
})()
"""

def sso_login(c):
    c.nav("https://vcsa.alan.lab/ui/", 8)
    for _ in range(30):
        if c.eval("!!document.querySelector('#username')"): break
        time.sleep(1)
    else:
        return "no-login-form (already logged in?)"
    c.eval("""(() => { const set=(s,v)=>{const e=document.querySelector(s); const d=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
      d.call(e,v); e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true}));};
      set('#username','administrator@vsphere.local'); set('#password','""" + os.environ["LAB_PASSWORD"] + """'); document.querySelector('#submit').click(); })()""")
    time.sleep(25); return c.eval("location.href")

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "start":
        start_chrome(); print("login ->", sso_login(Cdp())); sys.exit()
    c = Cdp()
    if cmd == "nav": print(c.nav(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 6))
    elif cmd == "eval": print(json.dumps(c.eval(sys.argv[2]), ensure_ascii=False, indent=1))
    elif cmd == "evalf": print(json.dumps(c.eval(open(sys.argv[2], encoding="utf-8").read()), ensure_ascii=False, indent=1))
    elif cmd == "shot": print(c.shot(sys.argv[2]))
    elif cmd == "dump": print(json.dumps(c.eval(DUMP_JS), ensure_ascii=False, indent=1))
