"""Generate the 4 architecture diagrams (SVG -> PNG via headless Chrome) for the VKS air-gap docs.
Palette: Broadcom official (vcf-base). Lines #717074. Canvas 1680x1040 (= 8.4 x 5.2 in left diagram area)."""
import os, subprocess, html

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagrams")
os.makedirs(OUT, exist_ok=True)
W, H = 1680, 1040
FONT = "Arial, 'Microsoft JhengHei', sans-serif"
C = dict(plum="#6C4B94", teal="#007B8C", ocean="#005C8A", sky="#0098C7", green="#61A60E", bgreen="#78BE20",
         dteal="#316E60", tcyan="#0091A0", bblue="#0095D3", royal="#1D428A", navy="#002142", lav="#A68CC2",
         orange="#E68C28", crimson="#A6192E", red="#CC092F", line="#717074", pale="#E8F0F4", grey="#F2F2F2",
         dgrey="#4A4A4A", white="#FFFFFF", gold="#F3BA16")


class S:
    def __init__(self):
        self.p = []

    def rect(self, x, y, w, h, fill="#fff", stroke=None, sw=2, rx=10, dash=None, op=1):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" fill-opacity="{op}"{st}{d}/>')

    def text(self, x, y, s, size=18, color=C["dgrey"], weight="normal", anchor="start", italic=False, rot=None):
        st = ' font-style="italic"' if italic else ""
        if rot is not None:
            st += f' transform="rotate({rot} {x} {y})"'
        self.p.append(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{color}" font-weight="{weight}" '
                      f'text-anchor="{anchor}"{st}>{html.escape(s)}</text>')

    def box(self, x, y, w, h, title, lines=(), color=C["royal"], fill=None, tsize=19, lsize=15, title_color=None):
        """Component box: colored header strip + white body with lines."""
        self.rect(x, y, w, h, fill=fill or C["white"], stroke=color, sw=2.5, rx=8)
        self.p.append(f'<path d="M{x} {y+8} a8 8 0 0 1 8 -8 h{w-16} a8 8 0 0 1 8 8 v{26} h{-w} z" fill="{color}"/>')
        self.text(x + w / 2, y + 24, title, tsize, title_color or C["white"], "bold", "middle")
        for i, ln in enumerate(lines):
            self.text(x + 12, y + 56 + i * (lsize + 7), ln, lsize, C["dgrey"])

    def arrow(self, pts, color=C["line"], sw=3, dash=None, label=None, lpos=None, lsize=15, lcolor=None, head=True):
        d = "M" + " L".join(f"{a} {b}" for a, b in pts)
        mid = f' stroke-dasharray="{dash}"' if dash else ""
        mk = f' marker-end="url(#ah-{color[1:]})"' if head else ""
        self.p.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}"{mid}{mk}/>')
        if label:
            lx, ly = lpos or ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2 - 8)
            self.p.append(f'<text x="{lx}" y="{ly}" font-family="{FONT}" font-size="{lsize}" fill="{lcolor or color}" '
                          f'font-weight="bold" text-anchor="middle" paint-order="stroke" stroke="#fff" stroke-width="5">{html.escape(label)}</text>')

    def svg(self, title=None):
        cols = sorted({c for c in C.values()})
        markers = "".join(f'<marker id="ah-{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                          f'<path d="M0 0 L10 5 L0 10 z" fill="{c}"/></marker>' for c in cols)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
                f'<defs>{markers}</defs><rect width="{W}" height="{H}" fill="#fff"/>' + "".join(self.p) + "</svg>")


def render(name, s):
    svg = s.svg()
    sp = os.path.join(OUT, name + ".svg"); open(sp, "w", encoding="utf-8").write(svg)
    hp = os.path.join(OUT, name + ".html")
    open(hp, "w", encoding="utf-8").write(f'<html><body style="margin:0;background:#fff">{svg}</body></html>')
    png = os.path.join(OUT, name + ".png")
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={W},{H}",
                    "--force-device-scale-factor=2", f"--screenshot={png}", "file:///" + hp.replace("\\", "/")],
                   check=True, capture_output=True, timeout=120)
    print("rendered", png, os.path.getsize(png))


# ---------------------------------------------------------------- D1 architecture
def d1():
    s = S()
    s.text(20, 36, "VKS Air-Gap Lab Architecture — VCF 9.1.1 (no VCF Management Services)", 26, C["plum"], "bold")
    # internet + air-gap boundary
    s.rect(20, 56, 520, 118, C["grey"], C["line"], 2, 14, "8 6")
    s.text(34, 84, "Internet (Broadcom)", 19, C["dgrey"], "bold")
    for i, t in enumerate(["support.broadcom.com  (VCF CLI + plugin bundle)",
                           "projects.packages.broadcom.com  (vks-addons, packages)",
                           "wp-content.broadcom.com  (VKr OVF)  ·  github.com (Harbor, tools)"]):
        s.text(34, 110 + i * 22, t, 14.5)
    s.p.append(f'<line x1="20" y1="192" x2="1660" y2="192" stroke="{C["crimson"]}" stroke-width="3" stroke-dasharray="14 8"/>')
    s.text(1660, 186, "AIR-GAP BOUNDARY — lab DNS (dnsmasq) has no upstream; only bastion is internet-side", 16, C["crimson"], "bold", "end")
    # outer vSphere column
    s.rect(20, 208, 520, 812, C["pale"], C["line"], 2, 14)
    s.text(34, 236, "Outer vSphere  (Xindian vCenter 192.168.110.32)", 18, C["navy"], "bold")
    s.box(40, 252, 480, 96, "bastion  110.86  (internet side)", ["Docker · imgpkg · yq · govc · curl", "downloads + SHA256SUMS → ~/airgap"], C["orange"])
    s.box(40, 364, 480, 96, "vcf91-depot  110.85 / 120.5", ["dnsmasq (alan.lab DNS, air-gapped)", "VCF offline depot (bring-up binaries)"], C["dteal"])
    s.box(40, 476, 480, 74, "dcxd pfSense  110.254 / 120.1 / 130.1", ["routes 120.x ↔ 130.x (not modified)"], C["line"])
    s.box(40, 566, 480, 74, "vcf-installer  120.2", ["VCF Installer (bring-up stopped after NSX)"], C["royal"])
    s.box(40, 656, 480, 130, "harbor  120.80  (Harbor v2.15.2, offline)", ["vks/vks-addons : 3.7.0-20260618",
          "vks/vks-standard-packages : 3.6.0-20260211", "library/*   ·  self-signed CA (alan.lab Harbor Root CA)"], C["green"])
    s.box(40, 812, 480, 112, "admin  120.81  (air-gapped jump host)", ["kubectl / kubectl-vsphere (from Supervisor)",
          "VCF CLI 9.1.1 + 13 plugins · imgpkg", "govc import VKr → content library vks-kr-local"], C["plum"])
    s.text(40, 944, "Mgmt network 192.168.120.0/24  (VLAN 0, gw 120.1)", 15, C["royal"], "bold")
    s.text(40, 968, "Workload 192.168.130.0/24  (pg-vks-workload, gw 130.1)", 15, C["tcyan"], "bold")
    s.text(40, 992, "DNS 192.168.120.5 for all lab components", 15, C["dteal"], "bold")
    # nested cluster
    s.rect(570, 208, 1090, 812, "#FAFAFC", C["plum"], 3, 14)
    s.text(588, 236, "Nested VCF 9.1.1 management domain — cluster vcf-m01-cl01  (esx01–03 · vSAN FTT=0)", 18, C["plum"], "bold")
    s.box(590, 252, 330, 96, "vCenter  vcsa.alan.lab 120.3", ["Supervisor Management", "content library vks-kr-local"], C["royal"])
    s.box(935, 252, 330, 96, "SDDC Manager  120.4", ["domain m01 ACTIVE", "(from bring-up, not VCFMS)"], C["royal"])
    s.box(1280, 252, 360, 96, "NSX Manager  120.11", ["installed by bring-up", "NOT used by Supervisor (VDS)"], C["line"])
    # supervisor
    s.rect(590, 364, 1050, 300, C["white"], C["teal"], 2.5, 10)
    s.text(606, 390, "Supervisor  supervisor01  —  VDS networking + Foundation Load Balancer (one-arm)", 17, C["teal"], "bold")
    s.box(606, 404, 330, 118, "Control Plane × 3  (Small)", ["mgmt 120.90 (float) –.93", "workload 130.100 – .102", "K8s v1.34.9 · VKS svc 3.7.0"], C["teal"])
    s.box(950, 404, 330, 118, "Foundation LB × 2  (Medium)", ["active / passive", "mgmt 120.95 – .97", "VS/transit 130.103 / .104"], C["sky"])
    s.box(1294, 404, 330, 118, "API VIP  130.200", ["supervisor01.alan.lab", "VIP pool 130.200 – .250", "(one-arm on primary-wl)"], C["bblue"])
    s.box(606, 536, 1018, 112, "ESXi esx01–03  =  Spherelet agent nodes  (vSphere Pods enabled)", [
        "Supervisor Services: tkg.vsphere.vmware.com 3.7.0 · velero 1.9.0 · cci-ns 9.1.2  (all CONFIGURED)",
        "Container registry trust: harbor.alan.lab (CA registered)  ·  add-on repo → harbor-addonrepository-3.7.0"], C["tcyan"])
    # namespace / vks
    s.rect(590, 680, 1050, 324, C["white"], C["green"], 2.5, 10)
    s.text(606, 706, "vSphere Namespace  vks-ns01   (VM classes best-effort-small … xlarge · vSAN policy · primary-wl)", 17, C["green"], "bold")
    s.box(606, 720, 500, 150, "VKS cluster  vks-test01", ["ClusterClass builtin-generic-v3.7.0 (CAPI v1beta2)",
          "v1.34.9+vmware.2-vkr.4 · CP 130.108 · worker 130.109", "API VIP 130.202 (FLB) · pods 10.244/16 · svc 10.97/16",
          "trust: Harbor CA (osConfiguration.trust)"], C["green"])
    s.box(1124, 720, 500, 150, "Content library  vks-kr-local", ["VKr v1.34.9 · v1.35.6 · v1.36.2  (Photon 5)",
          "READY + COMPATIBLE", "imported offline with govc", "(no subscribed library, no internet)"], C["dteal"])
    s.box(606, 884, 1018, 104, "Workload images come only from:", ["localhost:5000 (VKr-embedded)  ·  harbor.alan.lab  —  0 images from public registries",
          "Pod Security default: restricted:latest"], C["bgreen"])
    # flows
    s.arrow([(520, 300), (548, 300), (548, 868), (522, 868)], C["orange"], 3, "8 6")
    s.text(560, 470, "media transfer (scp + SHA256)", 14, C["orange"], "bold", "middle", rot=90)
    s.arrow([(280, 812), (280, 790)], C["plum"], 3)
    s.text(292, 806, "imgpkg push", 13, C["plum"], "bold")
    s.arrow([(520, 740), (604, 800)], C["green"], 3, None, "pull", (575, 760), 14)
    s.arrow([(520, 700), (604, 610)], C["green"], 3, "6 4")
    s.text(612, 676, "add-on repo fetch (Harbor)", 13, C["green"], "bold")
    return s


# ---------------------------------------------------------------- D2 supply chain
def d2():
    s = S()
    s.text(20, 38, "Air-Gap Supply Chain — what is carried in, from where, to where", 26, C["plum"], "bold")
    cols = [("SOURCE (internet)", 20, C["line"]), ("BASTION 110.86", 440, C["orange"]), ("ADMIN 120.81 (air-gapped)", 860, C["plum"]), ("TARGET", 1270, C["green"])]
    for t, x, c in cols:
        s.rect(x, 60, 390, 44, c, None, 0, 8); s.text(x + 195, 90, t, 19, C["white"], "bold", "middle")
    rows = [
        ("Broadcom Support Portal", "VCF Consumption CLI 9.1.1\n+ PluginBundle (13 plugins)", "vcf plugin install all\n--local-source", "VCF CLI on admin\n(vcf context / cluster / addon)", C["plum"]),
        ("wp-content.broadcom.com", "VKr OVF ×3 (curl)\nv1.34.9 · v1.35.6 · v1.36.2", "govc library.import\n(item name = original)", "Content library\nvks-kr-local → Supervisor", C["dteal"]),
        ("projects.packages.broadcom.com", "imgpkg copy --to-tar\nvks-addons:3.7.0-20260618", "imgpkg copy --tar\n--to-repo harbor.../vks", "Harbor vks/vks-addons\n→ AddonRepository", C["green"]),
        ("github.com", "Harbor offline installer\nDocker debs · imgpkg/yq/govc", "dpkg -i · install.sh\n(no apt, no internet)", "harbor 120.80 / admin\n(Docker, tools)", C["sky"]),
        ("Supervisor itself", "—", "/wcp/plugin/.../vsphere-plugin.zip", "kubectl + kubectl-vsphere\n(no internet needed)", C["teal"]),
    ]
    y = 124
    for src, bas, adm, tgt, c in rows:
        for i, (x, txt) in enumerate([(20, src), (440, bas), (860, adm), (1270, tgt)]):
            s.rect(x, y, 390, 150, C["white"], c, 2.5, 10)
            for j, ln in enumerate(txt.split("\n")):
                s.text(x + 195, y + 62 + j * 30, ln, 18 if i else 19, C["dgrey"] if i else c, "bold" if i == 0 else "normal", "middle")
        for x in (410, 830, 1240):
            s.arrow([(x, y + 75), (x + 28, y + 75)], c, 3.5)
        y += 172
    s.text(440, 1010, "Every hop is checked with SHA256SUMS  ·  bastion → admin via scp  ·  harbor/admin never use apt or the internet", 16, C["crimson"], "bold")
    return s


# ---------------------------------------------------------------- D3 bring-up stop point
def d3():
    s = S()
    s.text(20, 38, "VCF 9.1.1 Bring-up — run to NSX, abort before VCF Management Platform", 26, C["plum"], "bold")
    ms = [("M1", "Deploy vCenter", "done"), ("M2", "Deploy SDDC Manager", "done"), ("M3", "Configure vSphere cluster", "done"),
          ("M4", "Deploy and configure NSX", "done"), ("M5", "VCF Management Platform (VSP)", "abort"),
          ("M6", "Operations appliance", "skip"), ("M7", "VCF Management Services", "skip")]
    x0, y0, w, gap = 30, 110, 220, 13
    for i, (m, t, st) in enumerate(ms):
        x = x0 + i * (w + gap)
        col = {"done": C["green"], "abort": C["crimson"], "skip": "#B8B8B8"}[st]
        s.rect(x, y0, w, 170, col, None, 0, 12)
        s.text(x + w / 2, y0 + 50, m, 34, C["white"], "bold", "middle")
        parts, cur = [], ""
        for word in t.split():
            if len(cur) + len(word) + 1 > 17 and cur:
                parts.append(cur); cur = word
            else:
                cur = (cur + " " + word).strip()
        parts.append(cur)
        for j, part in enumerate(parts):
            s.text(x + w / 2, y0 + 88 + j * 24, part, 16, C["white"], "bold", "middle")
        s.text(x + w / 2, y0 + 150, {"done": "SUCCESS", "abort": "ABORTED (by design)", "skip": "NOT STARTED"}[st], 15, C["white"], "bold", "middle")
    s.text(30, 330, "Why abort instead of omitting? — validation rejects a spec without vspClusterSpec:", 20, C["dgrey"], "bold")
    s.text(30, 360, "\"VCF service runtime specification must be present in the SDDC specification\" → keep the full spec, stop the run.", 18, C["crimson"])
    s.rect(30, 392, 1620, 300, C["pale"], None, 0, 12)
    s.text(50, 426, "Abort watcher (vks-airgap/scripts/abort_watcher.py) — trigger and actions", 20, C["royal"], "bold")
    lines = ["Trigger: subtask #272 'Deploy VCF Management Services via SDDC Manager' leaves INITIALIZED (M4 already done, domain m01 ACTIVE)",
             "1.  VCF Installer 120.2 :   systemctl stop domainmanager      → no M6 / M7",
             "2.  SDDC Manager 120.4 :    systemctl restart domainmanager   → in-flight VSP task ends ORCH_TASK_INTERRUPTED",
             "3.  destroy any vsp01-* / vcf-services-runtime-template VMs  (none existed — aborted in time)",
             "4.  VCF Installer :         systemctl start domainmanager     (installer stays reusable)",
             "Gotcha: not-yet-started subtasks report status INITIALIZED — treat as idle or the watcher fires immediately"]
    for i, ln in enumerate(lines):
        s.text(60, 466 + i * 36, ln, 17, C["crimson"] if ln.startswith("Gotcha") else C["dgrey"], "bold" if i == 0 else "normal")
    s.rect(30, 712, 790, 300, C["white"], C["green"], 2.5, 12)
    s.text(50, 746, "Result (1 h 45 min)", 20, C["green"], "bold")
    for i, ln in enumerate(["vCenter 120.3 · SDDC Manager 120.4 · NSX 120.11", "vSAN vcf-m01-cl01-ds-vsan01 (FTT=0)",
                            "vDS vcf-m01-cl01-vds01 (MTU 9000) + NSX TEP", "Only 3 VMs: vcsa, sddc, nsx01 — no VSP / VCFMS"]):
        s.text(60, 790 + i * 40, "•  " + ln, 18)
    s.rect(860, 712, 790, 300, C["white"], C["orange"], 2.5, 12)
    s.text(880, 746, "Unavoidable / side effects", 20, C["orange"], "bold")
    for i, ln in enumerate(["SDDC Manager is deployed (M2, before NSX)", "Bring-up record: COMPLETED_WITH_FAILURE (M5)",
                            "SDDC Manager task 'Creating VCF services runtime' = Failed", "NSX VPC external IP block = 192.168.120.0/24 — do not create VPCs"]):
        s.text(890, 790 + i * 40, "•  " + ln, 18)
    return s


# ---------------------------------------------------------------- D4 add-on repository override
def d4():
    s = S()
    s.text(20, 38, "VKS 3.7 Add-on Repository — default (public) vs. internal override", 26, C["plum"], "bold")
    s.rect(20, 60, 1640, 560, C["pale"], None, 0, 12)
    s.text(40, 90, "Supervisor  ·  namespace vmware-system-vks-public", 19, C["navy"], "bold")
    s.box(40, 108, 520, 150, "builtin-addonrepository-3.7.0", ["projects.packages.broadcom.com/.../vks-addons:3.7.0-20260618",
          "kapp-owned · URL hard-coded in VKS bundle", "left in place, UNUSED after override"], C["crimson"])
    s.box(40, 290, 520, 150, "harbor-addonrepository-3.7.0  (user)", ["harbor.alan.lab/vks/vks-addons:3.7.0-20260618",
          "copy of builtin: only name + imageURL change", "keep package-offerings; drop kapp.k14s.io/*"], C["green"])
    s.box(620, 190, 520, 190, "AddonRepositoryInstall", ["default-addon-repo-install-3.7.0-20260618",
          "annotation skip-vks-managed-addon-repository-update=true", "spec.addonRepositoryRef → harbor-addonrepository-3.7.0",
          "preferred-repository = builtin (webhook: addon-manager only)", "controller log: 'skipped updating AddonRepositoryRef'"], C["royal"])
    s.box(1200, 190, 440, 150, "PackageRepository (Supervisor)", ["vks-addons-3.7.0-20260618", "image = harbor.alan.lab/vks/vks-addons",
          "Reconcile succeeded (air-gapped)"], C["teal"])
    s.arrow([(560, 365), (590, 365), (590, 300), (618, 300)], C["green"], 4, None, "ref", (600, 290))
    s.arrow([(560, 183), (590, 183), (590, 250), (618, 250)], C["crimson"], 3, "8 6", "default ref", (612, 170))
    s.arrow([(1140, 265), (1198, 265)], C["teal"], 4)
    s.box(40, 470, 1600, 128, "carvel-repo AddonConfig  (per cluster, vks-ns01/vks-test01-carvel-repo)", [
        "input: Supervisor PackageRepositories labelled addons.kubernetes.vmware.com/carvel-pkgr=true  →  output: same image into the workload cluster",
        "→ workload side follows the Supervisor automatically (≈ 2 min); nothing to edit in each cluster"], C["tcyan"])
    s.arrow([(1420, 340), (1420, 468)], C["tcyan"], 4)
    s.rect(20, 640, 1640, 170, C["white"], C["green"], 2.5, 12)
    s.text(40, 672, "Workload cluster vks-test01  ·  namespace vmware-system-tkg", 19, C["green"], "bold")
    s.text(40, 708, "PackageRepository vks-addons-3.7.0-20260618 → harbor.alan.lab/vks/vks-addons  ·  Reconcile succeeded  ·  29 packages available", 17)
    s.text(40, 742, "PackageInstall helm-controller 1.5.4 (from the repo) + VKr-embedded add-ons: antrea · CSI · CPI · pinniped · metrics-server · secretgen · gateway-api", 17)
    s.text(40, 776, "Node trust: Harbor CA via Cluster variable osConfiguration.trust.additionalTrustedCAs", 17)
    s.arrow([(840, 598), (840, 638)], C["green"], 4)
    s.rect(20, 830, 1640, 190, "#FFF", C["crimson"], 2.5, 12)
    s.text(40, 862, "Proof under DNS air-gap (2026-09-28)", 19, C["crimson"], "bold")
    for i, ln in enumerate(["Negative control: remove skip annotation → ARI reverts to builtin in ~30 s → Supervisor pkgr fails at once, workload fails on next sync:",
                            "   Get \"https://projects.packages.broadcom.com/v2/\": dial tcp: lookup projects.packages.broadcom.com ...   (running add-ons unaffected)",
                            "Re-apply override → both sides Reconcile succeeded from Harbor within ~30 s; next scheduled fetch 15:53Z also succeeded",
                            "Future VKS upgrade (e.g. add-on 3.7.0+20260723): a new VKS-managed ARI with the public URL appears → repeat the override"]):
        s.text(40, 900 + i * 30, ln, 16, C["dgrey"])
    return s


if __name__ == "__main__":
    for n, f in (("d1-architecture", d1), ("d2-supply-chain", d2), ("d3-bringup-stop", d3), ("d4-addon-repo-override", d4)):
        render(n, f())
