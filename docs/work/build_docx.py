"""VKS air-gap Installation & Configuration Procedures (docx).
Structure follows the PSO kit '*_InstallationAndConfigurationProcedures.docx' pattern
(Version History -> Overview -> Prerequisites -> Procedures (goal / where / steps / verification) -> Verification -> Troubleshooting).
Usage:  python build_docx.py [KIT.docx]   # with KIT: kit styles/header/footer are reused, its body is replaced."""
import os, sys, re
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

HERE = os.path.dirname(os.path.abspath(__file__))
DIA = os.path.join(HERE, "diagrams")
OUT = os.path.join(os.path.dirname(HERE), "VKS-AirGap-VCF911-Installation-Procedures.docx")
ROOT = os.path.dirname(os.path.dirname(HERE))  # vks-airgap
KIT = sys.argv[1] if len(sys.argv) > 1 else None
PLUM, TEAL, NAVY, GREY = "6C4B94", "007B8C", "1B1D36", "717074"
PW = "<ADMIN_PASSWORD>"

doc = Document(KIT) if KIT else Document()
if KIT:  # keep cover Title + Subtitle(with cover art) and sectPr (page setup / header / footer); drop the rest of the kit body
    body = doc.element.body
    kids = list(body)
    for el in kids[2:]:
        if el.tag != qn("w:sectPr"):
            body.remove(el)
    # cover + running header are TITLE / SUBJECT / AUTHOR fields -> set document properties and the fields' cached text
    TITLE_TXT = "VKS Air-Gapped Installation on VCF 9.1.1"
    SUBJ_TXT = "Installation and Configuration Procedures — 安裝與組態程序"
    cp = doc.core_properties; cp.title, cp.subject, cp.author = TITLE_TXT, SUBJ_TXT, "VMware by Broadcom"
    cache = {"TITLE": TITLE_TXT, "SUBJECT": SUBJ_TXT, "AUTHOR": "VMware by Broadcom"}
    parts = [doc.element] + [getattr(doc.sections[0], h)._element for h in ("header", "footer")]
    for root in parts:
        for f in root.iter(qn("w:fldSimple")):
            key = f.get(qn("w:instr")).split()[0]
            if key in cache:
                ts = list(f.iter(qn("w:t")))
                for k, t in enumerate(ts): t.text = cache[key] if k == 0 else ""
                for br in list(f.iter(qn("w:br"))): br.getparent().remove(br)
else:
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21.0), Cm(29.7)
    s.left_margin = s.right_margin = Cm(2.2); s.top_margin = s.bottom_margin = Cm(2.2)


def set_fonts(style, latin="Arial", ea="Microsoft JhengHei", size=None, color=None, bold=None):
    f = style.font; f.name = latin
    if size: f.size = Pt(size)
    if color: f.color.rgb = RGBColor.from_string(color)
    if bold is not None: f.bold = bold
    rpr = style.element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None: rf = OxmlElement("w:rFonts"); rpr.insert(0, rf)
    for k in ("w:ascii", "w:hAnsi", "w:cs"): rf.set(qn(k), latin)
    rf.set(qn("w:eastAsia"), ea)


st = doc.styles
if not KIT:
    set_fonts(st["Normal"], size=10.5)
    st["Normal"].paragraph_format.space_after = Pt(4); st["Normal"].paragraph_format.line_spacing = 1.15
    for n, sz, col in (("Heading 1", 18, PLUM), ("Heading 2", 14, TEAL), ("Heading 3", 12, NAVY), ("Title", 26, PLUM)):
        set_fonts(st[n], size=sz, color=col, bold=True)
        st[n].paragraph_format.space_before = Pt(14 if n == "Heading 1" else 10); st[n].paragraph_format.space_after = Pt(6)
    st["Heading 1"].paragraph_format.page_break_before = True
else:
    for n in ("Normal", "Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3", "Section Heading 1", "Body Text", "List Bullet",
              "Table Body Text", "Table Header Text", "Figure Title", "Code Block", "toc 1", "toc 2", "toc 3"):
        try:
            rpr = st[n].element.get_or_add_rPr(); rf = rpr.find(qn("w:rFonts"))
            if rf is None: rf = OxmlElement("w:rFonts"); rpr.insert(0, rf)
            if rf.get(qn("w:eastAsiaTheme")) is not None: del rf.attrib[qn("w:eastAsiaTheme")]
            rf.set(qn("w:eastAsia"), "Microsoft JhengHei")
        except KeyError:
            pass
CODE_STYLE = "Code Block" if KIT else "Code"
BODY = "Body Text" if KIT else None
TH_FILL = "E1E1E1" if KIT else None
from docx.enum.style import WD_STYLE_TYPE
if "Code" not in [s.name for s in st]:
    cs = st.add_style("Code", WD_STYLE_TYPE.PARAGRAPH); cs.base_style = st["Normal"]
    set_fonts(cs, latin="Consolas", size=8.5, color="1B1D36")
    cs.paragraph_format.space_after = Pt(0); cs.paragraph_format.line_spacing = 1.0


def shade(el, hexcolor):
    pPr = el.get_or_add_pPr() if hasattr(el, "get_or_add_pPr") else el
    shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hexcolor)
    pPr.append(shd)


def cell_shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hexcolor)
    tcPr.append(shd)


def H(level, text):
    if KIT and level == 1:
        if text.startswith("附錄"):
            return doc.add_paragraph(text, style="Section Heading 1")
        text = re.sub("^[0-9]+　", "", text)   # Heading 1 is auto-numbered in the kit
    return doc.add_heading(text, level)


def P(text, bold_prefix=None, italic=False, color=None, size=None):
    p = doc.add_paragraph(style=BODY)
    if bold_prefix:
        r = p.add_run(bold_prefix); r.bold = True
    _inline(p, text, italic=italic, color=color, size=size)
    return p


def _inline(p, text, italic=False, color=None, size=None):
    # `code` spans -> Consolas, **bold**
    for i, part in enumerate(re.split(r"(`[^`]+`|\*\*[^*]+\*\*)", text)):
        if not part: continue
        code = part.startswith("`"); bold = part.startswith("**")
        r = p.add_run(part.strip("`") if code else part.strip("*") if bold else part)
        if bold: r.bold = True
        if code:
            r.font.name = "Consolas"; r.font.size = Pt(9); r.font.color.rgb = RGBColor.from_string("A6192E")
        else:
            if italic: r.italic = True
            if color: r.font.color.rgb = RGBColor.from_string(color)
            if size: r.font.size = Pt(size)


def BL(items, style="List Bullet"):
    for it in items:
        p = doc.add_paragraph(style=style); _inline(p, it)


def STEPS(items):
    for i, it in enumerate(items, 1):
        p = doc.add_paragraph(style=BODY)
        p.paragraph_format.left_indent = Cm(0.8); p.paragraph_format.first_line_indent = Cm(-0.8)
        r = p.add_run(f"{i}.\t"); r.bold = True; r.font.color.rgb = RGBColor.from_string(TEAL)
        p.paragraph_format.tab_stops.add_tab_stop(Cm(0.8))
        _inline(p, it)


def CODE(text):
    lines = text.strip("\n").splitlines()
    for i, ln in enumerate(lines):
        p = doc.add_paragraph(style=CODE_STYLE)
        p.add_run(ln if ln else " ")
        shade(p._p, "F2F2F2")
        if i == len(lines) - 1: p.paragraph_format.space_after = Pt(8)


def NOTE(text, kind="注意"):
    col = {"注意": "E68C28", "重要": "A6192E", "提示": "61A60E", "說明": "0098C7"}[kind]
    t = doc.add_table(rows=1, cols=1); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.cell(0, 0); cell_shade(c, "F7F7F7")
    tcPr = c._tc.get_or_add_tcPr(); b = OxmlElement("w:tcBorders")
    for side in ("top", "bottom", "right"):
        e = OxmlElement(f"w:{side}"); e.set(qn("w:val"), "nil"); b.append(e)
    e = OxmlElement("w:left"); e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "24"); e.set(qn("w:color"), col); b.append(e)
    tcPr.append(b)
    p = c.paragraphs[0]; r = p.add_run(kind + "："); r.bold = True; r.font.color.rgb = RGBColor.from_string(col)
    _inline(p, text)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def TABLE(rows, widths=None, header=PLUM, font=9):
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = st["Table Grid"] if "Table Grid" in [s.name for s in st] else None
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = t.cell(r, c); cell.text = ""
            p = cell.paragraphs[0]
            if KIT: p.style = st["Table Header Text" if r == 0 else "Table Body Text"]
            p.paragraph_format.space_after = Pt(0)
            _inline(p, val, size=font)
            if r == 0:
                cell_shade(cell, TH_FILL or header)
                for run in p.runs:
                    run.bold = True
                    if not KIT: run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            elif r % 2 == 0:
                cell_shade(cell, "F2F2F2")
            if widths: cell.width = Cm(widths[c])
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    return t


fig_no = [0]


def FIG(png, caption, width=16.5):
    doc.add_picture(os.path.join(DIA, png), width=Cm(width))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    fig_no[0] += 1
    p = doc.add_paragraph(style="Figure Title" if KIT else None); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"圖 {fig_no[0]}　{caption}"); r.italic = True; r.font.size = Pt(9); r.font.color.rgb = RGBColor.from_string(GREY)


def PROC(title, goal, where, pre=None):
    H(2, title)
    TABLE([["項目", "內容"], ["目的", goal], ["執行位置", where]] + ([["前置條件", pre]] if pre else []),
          widths=[3, 13.5], header=TEAL)


def TOC():
    p = doc.add_paragraph()
    r = p.add_run(); f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin"); r._r.append(f1)
    r = p.add_run(); it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = 'TOC \\o "1-2" \\h \\z \\u \\t "Section Heading 1,1"'; r._r.append(it)
    r = p.add_run(); f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "separate"); r._r.append(f2)
    r = p.add_run("（在 Word 中按右鍵 →「更新功能變數」產生目錄）"); r.italic = True
    r = p.add_run(); f3 = OxmlElement("w:fldChar"); f3.set(qn("w:fldCharType"), "end"); r._r.append(f3)


# =====================================================================  COVER
if not KIT:
    for _ in range(5): doc.add_paragraph()
    p = doc.add_paragraph(); r = p.add_run("VMware Cloud Foundation 9.1.1"); r.font.size = Pt(14); r.font.color.rgb = RGBColor.from_string(TEAL); r.bold = True
    p = doc.add_paragraph(style="Title"); p.add_run("vSphere Kubernetes Service（VKS）\nAir-Gapped 安裝與組態程序")
if not KIT:
  p = doc.add_paragraph(style=BODY); _inline(p, "不部署 VCF Management Services｜Supervisor（VDS + Foundation Load Balancer）｜外部 Harbor Registry", size=13, color=NAVY)
def DOCINFO():
  TABLE([["項目", "內容"], ["文件類型", "Installation and Configuration Procedures"], ["環境", "alan.lab 實驗環境（nested VCF 9.1.1 管理網域）"],
       ["版本", "1.0"], ["日期", "2026-09-29"], ["狀態", "已於 DNS 層級 air-gap 下驗證"]], widths=[4, 12.5])
if not KIT:
    for _ in range(8): doc.add_paragraph()
    DOCINFO()
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

# =====================================================================  FRONT MATTER
def FM(text):
    if KIT: return doc.add_paragraph(text, style="Section Heading 1")
    p = doc.add_paragraph(); r = p.add_run(text); r.bold = True; r.font.size = Pt(16); r.font.color.rgb = RGBColor.from_string(PLUM); return p
FM("目錄")
TOC()
FM("版本歷程")
if KIT:
    P("不部署 VCF Management Services｜Supervisor（VDS + Foundation Load Balancer）｜外部 Harbor Registry", bold_prefix="範圍：")
    DOCINFO()
TABLE([["版本", "日期", "說明"],
       ["0.1", "2026-09-24", "初版實作：bring-up 至 NSX、Supervisor（VDS + FLB）、Harbor、VKS cluster、addon 套件庫改指"],
       ["0.2", "2026-09-28", "DNS air-gap 下重做 addon 套件庫改指（含反向對照）；VCF CLI 9.1.1 + plugins 離線安裝"],
       ["1.0", "2026-09-29", "整理為安裝組態程序文件"]], widths=[2, 3, 11.5])

# =====================================================================  1 OVERVIEW
H(1, "1　文件概述")
H(2, "1.1　目的")
P("本文件記錄在 VMware Cloud Foundation（VCF）9.1.1 管理網域上，於不部署 VCF Management Services（VCFMS）的前提下，"
  "建置可在隔離網路（air-gap）運作之 vSphere Kubernetes Service（VKS）的完整安裝與組態程序，並附上每個階段的驗證方式。")
H(2, "1.2　範圍")
TABLE([["範圍內", "範圍外"],
       ["VCF bring-up 至 NSX 後中止（不部署 VSP / VCFMS / VCF Operations）", "VCF Operations、VCF Automation、VCF Software Depot"],
       ["Supervisor：VDS 網路 + Foundation Load Balancer（one-arm）", "NSX 網路的 Supervisor（T0/T1、VPC）、Avi"],
       ["外部 Harbor（單台 Linux，離線安裝）", "Harbor Supervisor Service、Bootstrap Registry Appliance"],
       ["VKr 本地 content library、vSphere Namespace、VKS cluster", "生產環境容量規劃、備份與 DR"],
       ["VKS addon 套件庫改指內部 Harbor 與 air-gap 驗證", "封包層級防火牆阻擋（本 lab 以 DNS 層級切斷驗證）"],
       ["VCF CLI 9.1.1 + plugins 離線安裝", "VKS 版本升級（見 §7 後續工作）"]], widths=[8.25, 8.25])
H(2, "1.3　讀者")
P("負責 VCF / vSphere Supervisor 建置的工程師。讀者應熟悉 vCenter、Linux 指令列、kubectl 與容器 registry 基本操作。")
H(2, "1.4　參考文件")
BL(["vmware/vsphere-supervisor（GitHub）：`airgapped/air-gapped-vcf91.md`、`air-gapped-vcf90.md`、`air-gapped-harbor.md`",
    "Broadcom TechDocs：vSphere Supervisor 9.1 — Supervisor networking requirements（管理網與 workload 網須不同 subnet）",
    "Broadcom TechDocs：VKS — Update an Add-on Repository Install（skip-vks-managed-addon-repository-update）",
    "Broadcom KB 449965：Supervisor 下載 VCF CLI 回 503（需 VCF Management Services / Software Depot）",
    "本案腳本與 log：`vks-airgap/scripts/`、`vks-airgap/logs/`"])
H(2, "1.5　文件慣例")
BL(["`等寬字` 為指令、檔名、Kubernetes 物件或 UI 欄位值；UI 路徑以「→」表示。",
    f"密碼一律以 `{PW}` 表示，請替換為實際值；本文件不含任何實際帳密。",
    "IP 位址以「120.80」簡寫代表 192.168.120.80，以此類推。",
    "每個程序以「目的／執行位置／前置條件」表開頭，最後附「驗證」。"])

# =====================================================================  2 ARCHITECTURE
H(1, "2　架構概述")
H(2, "2.1　邏輯架構")
FIG("d1-architecture.png", "整體架構：外層支援 VM 與 nested VCF 9.1.1 管理網域")
P("外層 vSphere 上有 bastion（唯一可存取網際網路的機器）、Harbor、admin 與 DNS/depot 等支援 VM；nested 管理網域由 VCF bring-up 建立 "
  "vCenter、SDDC Manager 與 NSX，但在 VCF Management Platform 階段前中止。Supervisor 採 VDS 網路 + Foundation Load Balancer，"
  "資料路徑不經 NSX。air-gap 邊界以 lab DNS（dnsmasq）不轉送公開名稱實現。")
H(2, "2.2　元件清單")
TABLE([["元件", "版本 / 規格", "位置 / 位址"],
       ["VCF Installer", "9.1.1（保留重用，勿刪除）", "120.2"],
       ["ESXi × 3", "9.1.1 build 25714478，24 vCPU / 96 GB，vSAN ESA（FTT=0）", "esx01–03：120.61–.63"],
       ["vCenter / SDDC Manager / NSX Manager", "9.1.1（bring-up 部署）", "120.3 / 120.4 / 120.11"],
       ["Supervisor", "K8s v1.34.9，CP × 3（Small），VDS + FLB", "CP 120.90–.94；API VIP 130.200"],
       ["Foundation Load Balancer", "Medium × 2（active/passive），one-arm", "管理 120.95–.97；VIP 130.200–.250"],
       ["VKS（內建 Supervisor Service）", "tkg.vsphere.vmware.com 3.7.0-embedded", "—"],
       ["Harbor", "v2.15.2 offline installer，Ubuntu 24.04，4 vCPU / 8 GB / 300 GB", "harbor.alan.lab 120.80"],
       ["admin（air-gap 側工具機）", "Ubuntu 24.04：docker、kubectl、kubectl-vsphere、govc、imgpkg、yq、vcf", "admin.alan.lab 120.81"],
       ["bastion（internet 側）", "Ubuntu 24.04，2 vCPU / 4 GB / 200 GB", "bastion.alan.lab 110.86"],
       ["DNS（dnsmasq）", "depot VM 雙介面", "110.85 / 120.5"],
       ["VKS cluster vks-test01", "v1.34.9+vmware.2-vkr.4，CP 1 + worker 1", "API VIP 130.202"]], widths=[4.5, 7.5, 4.5])
H(2, "2.3　設計決策")
TABLE([["編號", "決策", "理由"],
       ["D01", "bring-up 保留完整 spec，於 subtask #272 開始時中止", "spec 缺 `vspClusterSpec` 會被 validation 拒絕：`VCF service runtime specification must be present`"],
       ["D02", "Supervisor 採 VDS + Foundation LB（one-arm）", "NSX VPC 只支援 Avi；NSX segment 需 Edge + T0；FLB 內建於 vCenter，air-gap 不需額外下載"],
       ["D03", "外部 Harbor（單台 Linux）作為唯一 registry", "無 VCF Software Depot；不在 Supervisor 內放 Harbor Supervisor Service"],
       ["D04", "Workload 網 192.168.130.0/24（VLAN 0，同一 L2）", "管理網與 workload 網必須不同 subnet；沿用 pfSense 既有 130.1 介面，不改 pfSense"],
       ["D05", "addon 套件庫以文件化 override 改指 Harbor", "builtin AddonRepository URL 寫死；外部 registry 只能在安裝後改指"],
       ["D06", "air-gap 以 DNS 層級切斷驗證", "pfSense 不可異動；VKS 抓套件與 image 皆使用主機名稱"],
       ["D07", "nested lab silence vSAN 測試 `nvmeonhcl`", "HCL 黃燈會擋 vLCM 套用 Spherelet（僅限 nested lab）"],
       ["D08", "VKS cluster 明確指定 pod / service CIDR", "預設 pod CIDR 192.168.0.0/16 與 lab 網段重疊"]], widths=[1.5, 6.5, 8.5])
H(2, "2.4　網路與 IP 規劃")
TABLE([["用途", "portgroup / 網段", "位址"],
       ["管理網（ESXi、vCenter、SDDC Manager、NSX、Harbor、admin）", "SDDC-DPortGroup-VM-Mgmt，192.168.120.0/24，gw 120.1", "見 §2.2"],
       ["Supervisor CP（5 個連續 IP）", "同上", "120.90–.94"],
       ["FLB 管理 IP", "同上（flb-mgmt）", "120.95–.96，後加 .97"],
       ["Primary workload 網（primary-wl）", "pg-vks-workload（VLAN 0），192.168.130.0/24，gw 130.1", "130.100–.179"],
       ["FLB VIP pool", "primary-wl（one-arm）", "130.200–.250"],
       ["Supervisor service CIDR", "內部", "10.96.0.0/23"],
       ["VKS pods / services", "內部", "10.244.0.0/16 / 10.97.0.0/16"],
       ["DNS / NTP", "—", "120.5（110.85）/ 110.1"]], widths=[6, 6.5, 4])
NOTE("NSX bring-up 建立的 VPC external IP block 為整個 192.168.120.0/24。本案不使用 VPC；若日後要使用，請先縮小該範圍，以免與 Supervisor / FLB / Harbor 位址衝突。", "注意")

# =====================================================================  3 PREREQUISITES
H(1, "3　前置需求")
H(2, "3.1　硬體與資源")
TABLE([["項目", "需求", "本案"],
       ["ESXi 主機", "3 台（Supervisor CP HA）", "nested 3 × 24 vCPU / 96 GB，disk 32 / 40 / 250 GB"],
       ["vSAN 容量", "Supervisor CP、FLB、VKS 節點、content library", "749 GB（FTT=0）"],
       ["支援 VM", "bastion、Harbor、admin", "2/4/200、4/8/300、2/4/200（vCPU/GB/GB）"]], widths=[3.5, 6.5, 6.5])
H(2, "3.2　DNS 記錄")
TABLE([["FQDN", "IP", "用途"],
       ["esx01–03.alan.lab", "120.61–.63", "ESXi"], ["vcsa.alan.lab / sddc.alan.lab / nsx01.alan.lab", "120.3 / 120.4 / 120.11", "管理元件"],
       ["harbor.alan.lab", "120.80", "Harbor（憑證 SAN 必須包含）"], ["admin.alan.lab / bastion.alan.lab", "120.81 / 110.86", "工具機"],
       ["supervisor01.alan.lab", "130.200", "Supervisor API（啟用後才知道 VIP，之後補記錄）"]], widths=[6.5, 4, 6])
NOTE("DNS 伺服器必須回應 workload 網段（130.x）的查詢。Ubuntu dnsmasq 預設帶 `--local-service` 只回應直接連接的網段，"
     "請在 `/etc/dnsmasq.d/05-listen.conf` 加入 `listen-address=127.0.0.1,192.168.110.85,192.168.120.5`（參見 §6.2）。"
     "另外，備份檔不可放在 `/etc/dnsmasq.d/` 內，否則會被當成設定載入。", "重要")
H(2, "3.3　需攜入 air-gap 區的素材")
TABLE([["素材", "來源", "大小", "用途"],
       ["Docker .deb × 5（containerd.io、docker-ce、docker-ce-cli、buildx、compose）", "download.docker.com（bastion `apt-get download`）", "~100 MB", "Harbor / admin 執行環境"],
       ["harbor-offline-installer-v2.15.2.tgz", "github.com/goharbor/harbor", "~700 MB", "Harbor 離線安裝"],
       ["imgpkg / yq / govc", "GitHub releases", "~100 MB", "搬運與匯入工具"],
       ["VKr × 3（v1.36.2 / v1.35.6 / v1.34.9，Photon 5）", "wp-content.broadcom.com/v2/latest", "~11.5 GB", "VKS 節點映像"],
       ["vks-addons:3.7.0-20260618 bundle", "projects.packages.broadcom.com（imgpkg）", "5.2 GB", "VKS addon 套件庫"],
       ["VCF-Consumption-CLI-Linux_AMD64-9.1.1.0.25662425.tar.gz", "Broadcom Support Portal", "38 MB", "VCF CLI"],
       ["VCF-Consumption-CLI-PluginBundle-Linux_AMD64-9.1.1.0.25665404.tar.gz", "Broadcom Support Portal", "265 MB", "VCF CLI plugins"]],
      widths=[6, 4.5, 2, 4])
NOTE("VKS 3.7.0 實際使用的是 `vks-addons:3.7.0-20260618`，而不是官方 9.1 air-gap 指南中的 `vks-standard-packages:3.6.0-20260211`。"
     "請以 Supervisor 上 `builtin-addonrepository-<版本>` 的 imageURL 為準決定要鏡像的版本。", "重要")
H(2, "3.4　帳號與權限")
BL(["vCenter：administrator@vsphere.local（啟用 Supervisor、建立 content library / Namespace、登錄 registry）。",
    "Harbor：admin（建立專案 `vks`、推送 bundle）。",
    "SDDC Manager / VCF Installer：root（中止 bring-up 時停止 / 重啟 `domainmanager`）。",
    "Broadcom Support Portal 帳號（下載 VCF CLI 與 plugin bundle）。"])

# =====================================================================  4 PROCEDURES
H(1, "4　安裝與組態程序")
P("程序依執行順序編排，總覽如下。")
FIG("d3-bringup-stop.png", "VCF bring-up 里程碑與中止點（M1–M4 完成、M5 開始時中止）")
TABLE([["#", "程序", "執行位置", "預估時間"],
       ["4.1", "VCF bring-up 至 NSX 並中止", "VCF Installer、SDDC Manager", "~2 小時"],
       ["4.2", "解除 nested vSAN HCL 對 vLCM 的阻擋（lab 限定）", "vCenter（pyVmomi）", "10 分鐘"],
       ["4.3", "建立 workload portgroup", "vCenter", "5 分鐘"],
       ["4.4", "啟用 Supervisor（VDS + FLB）", "vCenter UI", "~40 分鐘"],
       ["4.5", "部署支援 VM", "外層 vCenter", "20 分鐘"],
       ["4.6", "bastion 下載素材", "bastion", "依頻寬"],
       ["4.7", "Harbor 離線安裝", "harbor", "15 分鐘"],
       ["4.8", "admin 工具機與信任設定", "admin", "15 分鐘"],
       ["4.9", "Supervisor 登錄 Harbor 與 VKr content library", "admin / vCenter API", "30 分鐘"],
       ["4.10", "建立 vSphere Namespace", "vCenter", "5 分鐘"],
       ["4.11", "建立 VKS cluster", "admin", "~15 分鐘"],
       ["4.12", "addon 套件庫改指 Harbor", "admin / bastion", "30 分鐘"],
       ["4.13", "VCF CLI 與 plugins 離線安裝", "admin", "10 分鐘"]], widths=[1.2, 7.5, 5, 2.8])

# ---- 4.1
PROC("4.1　VCF bring-up 至 NSX 並中止",
     "透過 VCF Installer 取得 vCenter、vSAN、SDDC Manager 與 NSX，但不部署 VCF Management Platform（VSP）、VCF Operations 與 VCFMS。",
     "VCF Installer 120.2（API + root shell）、SDDC Manager 120.4（root shell）",
     "3 台 ESXi 已完成前置（NTP、DNS、vSAN 進階設定，vmk0 只保留 Management tag）；VCF Installer 已連上 offline depot")
H(3, "步驟")
STEPS(["準備完整的 bring-up spec（含 `vspClusterSpec` 等 fleet 區塊）。**不要**刪除 fleet 區塊：validation 會回 "
       "`VCF service runtime specification must be present in the SDDC specification`。",
       "`POST /v1/sddcs/validations` 執行驗證；可接受的 WARNING：儲存容量低於 VSP / Ops 需求（不會部署）、NTP 微小偏差。",
       "驗證後確認 3 台 ESXi 的 SSH 仍為 running（本案發現 validation 後被停用，需要重新啟用）。",
       "`POST /v1/sddcs` 送出 bring-up，同時啟動中止監看程式（`abort_watcher.py`），每 30 秒輪詢 `/v1/sddcs/{id}` 的 subtask。",
       "監看條件：subtask **#272 `Deploy VCF Management Services via SDDC Manager`** 由閒置變為執行中即觸發中止。"
       "未開始的 subtask 狀態為 `INITIALIZED`，必須視為閒置，否則一啟動就會誤觸發。",
       "觸發時依序執行：VCF Installer `systemctl stop domainmanager` → SDDC Manager `systemctl restart domainmanager`"
       "（中斷進行中的 VSP 部署，狀態 `ORCH_TASK_INTERRUPTED`）→ 若已產生 `vsp01-*`、`vcf-services-runtime-template-*` VM 則刪除 → "
       "VCF Installer `systemctl start domainmanager`。"])
CODE("""# VCF Installer (120.2) / SDDC Manager (120.4) — run as root at the moment #272 starts
systemctl stop domainmanager        # on VCF Installer: never proceed to M6/M7
systemctl restart domainmanager     # on SDDC Manager: interrupts the in-flight VSP deployment
systemctl start domainmanager       # on VCF Installer: keep the installer usable""")
H(3, "驗證")
BL(["VCF Installer：bring-up = `COMPLETED_WITH_FAILURE`；M1–M4 SUCCESS、M5 FAILURE、M6/M7 NOT_STARTED。",
    "SDDC Manager：domain `m01` = ACTIVE，esx01–03 = ASSIGNED；task「Creating VCF services runtime」= Failed（不會自動重試）。",
    "nested vCenter 只有 `vcsa`、`sddc`、`nsx01` 三台 VM；NSX 3 個 transport node state = success。"])
NOTE("M1–M4 約 1 小時 45 分。SDDC Manager 的 `domainmanager` 重啟後，`/v1/sddcs` 約需 1–2 分鐘才會從 502 恢復。VCF Installer 請保留，之後重建可重用。", "說明")

# ---- 4.2
PROC("4.2　解除 nested vSAN HCL 對 vLCM 的阻擋（僅限 nested lab）",
     "避免 vSAN 健康檢查「NVMe device is VMware certified」黃燈讓 vLCM FINALIZE 失敗，導致 Supervisor 無法在 ESXi 安裝 Spherelet。",
     "任一可連 vCenter 的機器（pyVmomi 9.1.1 內建 vSAN bindings）",
     "nested ESXi 使用虛擬 NVMe（不在 VCG）")
STEPS(["以 vSAN Health 端點（`/vsanHealth`）建立 `VsanVcClusterHealthSystem` stub，沿用 vCenter session cookie。",
       "查出測試名稱為「NVMe device is VMware certified」的 test id，取最後一段短 id `nvmeonhcl`。",
       "呼叫 `SetVsanClusterSilentChecks(cluster, addSilentChecks=['nvmeonhcl'])`。"])
CODE("""hs = vim.cluster.VsanVcClusterHealthSystem('vsan-cluster-health-system', vsan_stub)
hs.SetVsanClusterSilentChecks(cluster=cl, addSilentChecks=['nvmeonhcl'])   # short id only
print(hs.GetVsanClusterSilentChecks(cluster=cl))""")
NOTE("必須用短 id `nvmeonhcl`；完整 id `com.vmware.vsan.health.test.nvmeonhcl` 會被拒絕（`silent.testid.invalid`）。"
     "只 silence 這一項即可，其他黃燈（maximum component size、performance service）不會阻擋 vLCM。生產環境請使用 VCG 認證硬體，不要套用此步驟。", "重要")
H(3, "驗證")
BL(["`kubectl get nodes`（Supervisor）：esx01–03 為 `Ready / agent`。",
    "若已啟用 Supervisor 且卡住，除錯入口為 VCSA `/var/log/vmware/vmware-updatemgr/vum-server/`，搜尋 `returned status: NOT_OK`。"])

# ---- 4.3
PROC("4.3　建立 workload portgroup",
     "提供 Supervisor primary workload 網（與管理網不同 subnet）。",
     "vCenter（nested）", "外部 gateway 130.1 位於同一個未打 tag 的 L2")
STEPS(["在 `vcf-m01-cl01-vds01` 建立 distributed portgroup `pg-vks-workload`，VLAN type = None（VLAN 0），MTU 繼承 VDS（≥ 1600）。",
       "（建議）暫時建立測試 vmk 驗證 130.x 可到達 gateway 130.1、vCenter 120.3 與 DNS，測完刪除。"])
NOTE("官方需求：「The Management Network and the Workload Network must be on different subnets」。同一 subnet 不受支援。", "重要")

# ---- 4.4
PROC("4.4　啟用 Supervisor（VDS + Foundation LB）",
     "以 VDS 網路與 Foundation Load Balancer 啟用 Supervisor。",
     "vCenter UI：Supervisor Management（9.1 起 Workload Management 更名）→ Get Started",
     "§4.2、§4.3 完成；vSAN storage policy 可用")
P("預檢（REST）：`GET /api/vcenter/namespace-management/cluster-compatibility?network_provider=VSPHERE_NETWORK` 應為 compatible；"
  "`distributed-switch-compatibility` 應列出 `pg-vks-workload`。")
TABLE([["精靈步驟", "設定值"],
       ["1 Networking", "vSphere Distributed Switch (VDS)；Load Balancer Type = Foundation Load Balancer"],
       ["2 Location", "Cluster deployment；名稱 `supervisor01`；Control Plane HA（3 台）；vSphere Zone `zone-m01`"],
       ["3 Storage", "Control Plane / Ephemeral Disks / Image Cache 皆為 `vcf-m01-cl01 vSAN Storage Policy`"],
       ["4 Management Network", "Static；`SDDC-DPortGroup-VM-Mgmt`；起始 IP 120.90（5 個連續）；/24；gw 120.1；DNS 120.5；search `alan.lab`；NTP 110.1"],
       ["5 Workload Network", "Static；portgroup `pg-vks-workload` → 網路名 `primary-wl`；130.100–130.179；/24；gw 130.1；service CIDR 10.96.0.0/23"],
       ["6 Load Balancer", "名稱 `flb-supervisor01`；One Arm；Size Medium；HA 2 台；管理網按 ASSIGN 建立 `flb-mgmt`（120.95–.96，剛好 2 個 IP）；VIP 130.200–130.250"],
       ["7 Advanced", "Control Plane Size = Small（4 vCPU / 16 GB）；API Server DNS Name = `supervisor01.alan.lab`"]], widths=[3.5, 13])
H(3, "注意事項")
BL(["one-arm 的 Virtual Server 網路預設即為 primary workload 網，FLB 介面 IP 從 workload range 取得，不需另留位址。",
    "摘要頁不顯示 VIP、CP 大小、API DNS name，但值已帶入。",
    "「Supervisor 映像 content library」提示為選配（非同步升級用），air-gap 下使用 vCenter 內建映像即可。",
    "啟用期間可能出現 `no deployments found in any zone`、`Need 2 net devices`、`Timed out waiting for LB service update` 等暫時性訊息，會自行恢復。",
    "啟用完成後若出現 flb-mgmt IP pool 使用率 > 95% 警告：使用中的 workload network 只能新增範圍，請另加 `{120.97, count 1}`，不要修改既有範圍。"])
H(3, "驗證")
BL(["Supervisor = RUNNING，k8s = READY 且無訊息；API endpoint = 130.200（FLB 第一個 VIP）。",
    "於 DNS 新增 `supervisor01.alan.lab → 192.168.130.200`；`https://supervisor01.alan.lab/` 回 200。",
    "`kubectl get nodes`：3 台 CP Ready + 3 台 ESXi agent；內建服務 tkg 3.7.0 / velero / cci-ns = CONFIGURED。"])

# ---- 4.5
PROC("4.5　部署支援 VM",
     "建立 internet 側 bastion 與 air-gap 側 Harbor、admin。", "外層 vCenter（ovftool + cloud-init，Ubuntu 24.04 cloud image）")
TABLE([["VM", "網路", "IP / gw / DNS", "規格", "備註"],
       ["bastion", "VM Network", "110.86 / 110.254 / 110.85", "2 / 4 GB / 200 GB", "唯一可上網；cloud-init 安裝 git、jq、curl、sshpass"],
       ["harbor", "Nested Trunk（VLAN 0）", "120.80 / 120.1 / 120.5", "4 / 8 GB / 300 GB", "不執行 package_update"],
       ["admin", "Nested Trunk（VLAN 0）", "120.81 / 120.1 / 120.5", "2 / 4 GB / 200 GB", "不執行 package_update"]], widths=[2, 3, 4, 3, 4.5])
NOTE("harbor 與 admin 一律依 air-gap 方式安裝軟體（由 bastion 帶入），即使路由上可以上網也不在這兩台執行 apt 或 curl 外網，確保程序可直接用於真正的隔離環境。", "說明")

# ---- 4.6
PROC("4.6　bastion 下載素材", "下載所有需攜入的素材並產生 SHA256 清單。", "bastion（internet 側）",
     "若 lab DNS 已切斷（§6.1），先暫時還原 upstream，下載完再切回")
FIG("d2-supply-chain.png", "素材供應鏈：來源 → bastion → admin → 目標（每一跳以 SHA256 驗證）")
H(3, "4.6.1　Docker 與 Harbor（`bastion_prep.sh`）")
CODE("""PKGS="containerd.io docker-ce docker-ce-cli docker-buildx-plugin docker-compose-plugin"
mkdir -p ~/airgap/docker-debs && cd ~/airgap/docker-debs && apt-get download $PKGS
VER=v2.15.2
curl -fsSLo ~/airgap/harbor-offline-installer-$VER.tgz \\
  https://github.com/goharbor/harbor/releases/download/$VER/harbor-offline-installer-$VER.tgz
sha256sum ~/airgap/docker-debs/*.deb ~/airgap/harbor-offline-installer-*.tgz > ~/airgap/SHA256SUMS""")
H(3, "4.6.2　工具（`bastion_tools.sh`）")
CODE("""mkdir -p ~/airgap/tools && cd ~/airgap/tools
curl -fsSLo imgpkg https://github.com/carvel-dev/imgpkg/releases/download/<ver>/imgpkg-linux-amd64
curl -fsSLo yq     https://github.com/mikefarah/yq/releases/download/<ver>/yq_linux_amd64
curl -fsSLo govc.tgz https://github.com/vmware/govmomi/releases/download/<ver>/govc_Linux_x86_64.tar.gz
curl -fsSL https://wp-content.broadcom.com/v2/latest/items.json -o ~/airgap/vkr-items.json   # VKr catalog""")
H(3, "4.6.3　VKr 與 addon bundle（`bastion_download_vks.sh`）")
P("每個 Kubernetes minor 取最新的 Photon 5 item，每個 item 包含 vmdk、ovf、mf、cert：")
CODE("""BASE=https://wp-content.broadcom.com/v2/latest
ITEMS="ob-25650988-photon-5-amd64-v1.36.2---vmware.2-vkr.3
       ob-25653794-photon-5-amd64-v1.35.6---vmware.2-vkr.3
       ob-25677161-photon-5-amd64-v1.34.9---vmware.2-vkr.4"
for it in $ITEMS; do mkdir -p ~/airgap/vkr/$it
  for href in $(jq -r --arg n "$it" '.items[]|select(.name==$n)|.files[].hrefs[0]' ~/airgap/vkr-items.json); do
    curl -fsSL --retry 3 -o ~/airgap/vkr/$it/$(basename $href) "$BASE/$href"; done; done

# VKS 3.7.0 add-on repository bundle (version = builtin AddonRepository imageURL on the Supervisor)
imgpkg copy -b projects.packages.broadcom.com/vsphere/supervisor/vks-standard-packages/3.7.0-20260618/vks-addons:3.7.0-20260618 \\
  --to-tar ~/airgap/vks-addons-3.7.0-20260618.tar
cd ~/airgap && find vkr -type f | sort | xargs sha256sum > SHA256SUMS.vks && sha256sum *.tar >> SHA256SUMS.vks""")
H(3, "4.6.4　VCF CLI 與 plugins（Broadcom Support Portal）")
P("路徑：My Downloads → VMware Cloud Foundation → 9.1.x → **VCF Consumption CLI**（plugin 在同一版本下的 **VCF Consumption CLI Plugins**）。")
TABLE([["檔案", "SHA256"],
       ["VCF-Consumption-CLI-Linux_AMD64-9.1.1.0.25662425.tar.gz", "74cf9b7e95b9460613bf7899d292ee6b53c95a3a77659ac9ccfdc450784bba99"],
       ["VCF-Consumption-CLI-PluginBundle-Linux_AMD64-9.1.1.0.25665404.tar.gz", "5bf25a18368da57ba690e7efc35068143a9ef08f817e790e22a95a94505e9d70"]], widths=[7.5, 9])
NOTE("公開 artifactory（packages.broadcom.com/artifactory/vcf-distro/vcf-cli）只到 v9.0.2。Supervisor 的 `/wcp/vcf-cli/` 在沒有 VCF Software Depot 時固定回 503（KB 449965），因此 9.1 CLI 只能從 Support Portal 取得。"
     "瀏覽器下載時檔名可能被截成 `.gz`，請改回 `.tar.gz`。", "注意")

# ---- 4.7
PROC("4.7　Harbor 離線安裝", "以自簽 CA 建立 HTTPS Harbor，作為唯一 registry。", "harbor（120.80）",
     "`~/airgap/`（docker-debs、harbor installer、SHA256SUMS）已由 bastion 複製過來")
STEPS(["驗證素材：`cd ~/airgap && sha256sum -c SHA256SUMS`。",
       "離線安裝 Docker：`sudo dpkg -i docker-debs/*.deb && sudo systemctl enable --now docker`。",
       "建立 CA 與伺服器憑證（SAN 必須包含 FQDN、短名與 IP）。",
       "讓 Docker 與系統信任 CA。",
       "設定 `harbor.yml`（hostname、certificate、private_key、admin 密碼）並執行 `install.sh`（不加 Trivy：弱點資料庫需要外網）。"])
CODE("""sudo mkdir -p /data/cert && cd /data/cert
sudo openssl genrsa -out ca.key 4096
sudo openssl req -x509 -new -nodes -sha512 -days 3650 -subj "/C=TW/O=alan.lab/CN=alan.lab Harbor Root CA" -key ca.key -out ca.crt
sudo openssl genrsa -out harbor.alan.lab.key 4096
sudo openssl req -sha512 -new -subj "/C=TW/O=alan.lab/CN=harbor.alan.lab" -key harbor.alan.lab.key -out harbor.alan.lab.csr
printf "authorityKeyIdentifier=keyid,issuer\\nbasicConstraints=CA:FALSE\\nkeyUsage=digitalSignature,nonRepudiation,keyEncipherment,dataEncipherment\\nextendedKeyUsage=serverAuth\\nsubjectAltName=DNS:harbor.alan.lab,DNS:harbor,IP:192.168.120.80\\n" | sudo tee v3.ext
sudo openssl x509 -req -sha512 -days 825 -extfile v3.ext -CA ca.crt -CAkey ca.key -CAcreateserial \\
  -in harbor.alan.lab.csr -out harbor.alan.lab.crt

sudo mkdir -p /etc/docker/certs.d/harbor.alan.lab && sudo cp ca.crt /etc/docker/certs.d/harbor.alan.lab/
sudo cp ca.crt /usr/local/share/ca-certificates/alan-lab-harbor-ca.crt && sudo update-ca-certificates

cd ~ && tar xzf ~/airgap/harbor-offline-installer-*.tgz && cd ~/harbor && cp harbor.yml.tmpl harbor.yml
sed -i 's/^hostname: .*/hostname: harbor.alan.lab/' harbor.yml
sed -i 's#^  certificate: .*#  certificate: /data/cert/harbor.alan.lab.crt#' harbor.yml
sed -i 's#^  private_key: .*#  private_key: /data/cert/harbor.alan.lab.key#' harbor.yml
sed -i 's/^harbor_admin_password: .*/harbor_admin_password: <ADMIN_PASSWORD>/' harbor.yml
sudo ./install.sh""")
H(3, "驗證")
BL(["`curl https://harbor.alan.lab/api/v2.0/health` → 所有元件 healthy（剛啟動 10 秒內 jobservice 可能短暫 unhealthy）。",
    "push 測試 image（例如 installer 內建的 `goharbor/harbor-log`，不需外網）至 `library/airgap-test`，並從 admin 以 TLS 驗證 pull 成功。",
    "CA 憑證：`CN=alan.lab Harbor Root CA`，到期 2036-09-21；CA 私鑰僅保存在 harbor `/data/cert/ca.key`。"])

# ---- 4.8
PROC("4.8　admin 工具機與信任設定", "安裝 air-gap 側操作工具，並信任 vCenter 與 Harbor CA。", "admin（120.81）")
STEPS(["同 §4.7 以 `dpkg -i` 離線安裝 Docker；將 Harbor `ca.crt` 放入 `/etc/docker/certs.d/harbor.alan.lab/` 與系統 trust store。",
       "安裝 imgpkg、yq、govc 至 `/usr/local/bin`（先比對 SHA256）。",
       "從 vCenter 本身取得 CA（不需外網）並加入 trust store。",
       "從 Supervisor 下載 kubectl 與 kubectl-vsphere（不需外網）並登入。"])
CODE("""curl -fsSk https://vcsa.alan.lab/certs/download.zip -o /tmp/vc-certs.zip
cd /tmp && python3 -c "import zipfile;zipfile.ZipFile('/tmp/vc-certs.zip').extractall('vc-certs')"
i=0; for c in vc-certs/certs/lin/*.0; do sudo cp $c /usr/local/share/ca-certificates/vcsa-$i.crt; i=$((i+1)); done
sudo update-ca-certificates

curl -fsSLO https://supervisor01.alan.lab/wcp/plugin/linux-amd64/vsphere-plugin.zip
unzip vsphere-plugin.zip -d vsphere-plugin && sudo install vsphere-plugin/bin/* /usr/local/bin/
export KUBECTL_VSPHERE_PASSWORD='<ADMIN_PASSWORD>'
kubectl vsphere login --server=supervisor01.alan.lab --vsphere-username administrator@vsphere.local""")
NOTE("Supervisor 提供的 kubectl 為 v1.32，而 Supervisor 為 v1.34（相差 2 個 minor，超出官方 ±1 支援範圍）。查詢正常；如遇異常先懷疑版本差。", "注意")

# ---- 4.9
PROC("4.9　Supervisor 登錄 Harbor 與 VKr content library",
     "讓 Supervisor 信任 Harbor，並提供本地 Kubernetes Release（VKr）。", "admin（govc、curl）/ vCenter REST API")
H(3, "4.9.1　登錄 Harbor 至 Supervisor")
CODE("""POST /api/vcenter/namespace-management/supervisors/{supervisor}/container-image-registries
{
  "name": "harbor-alan-lab",
  "image_registry": {"hostname": "harbor.alan.lab", "port": 443,
                     "certificate_chain": "<Harbor CA PEM>",
                     "username": "admin", "password": "<ADMIN_PASSWORD>"},
  "default_registry": false
}""")
H(3, "4.9.2　建立 content library 並匯入 VKr")
STEPS(["建立 LOCAL content library `vks-kr-local`（vSAN datastore）。",
       "以 govc 匯入每個 VKr item，**item 名稱必須等於原始名稱**（例如 `ob-25677161-photon-5-amd64-v1.34.9---vmware.2-vkr.4`）。",
       "設為 Supervisor 預設 VKr content library：`PATCH /api/vcenter/namespace-management/clusters/{cluster}`，"
       "body `{\"default_kubernetes_service_content_library\": \"<library id>\"}`。此操作為非同步，約 20 秒後生效。"])
CODE("""export GOVC_URL=https://vcsa.alan.lab GOVC_USERNAME=administrator@vsphere.local GOVC_PASSWORD='<ADMIN_PASSWORD>'
cd ~/vks && sha256sum -c SHA256SUMS.vks
for d in ~/vks/vkr/*/; do item=$(basename $d)
  govc library.import -n "$item" vks-kr-local "$(ls $d*.ovf)"; done
govc library.ls 'vks-kr-local/*'""")
H(3, "驗證")
BL(["`kubectl get kr`：v1.34.9 / v1.35.6 / v1.36.2 皆為 READY 且 COMPATIBLE。"])

# ---- 4.10
PROC("4.10　建立 vSphere Namespace", "提供 VKS cluster 所在的 Namespace。", "vCenter UI 或 REST API")
TABLE([["設定", "值"], ["名稱", "vks-ns01"], ["Storage policy", "vcf-m01-cl01 vSAN Storage Policy"],
       ["VM class", "best-effort-small / medium / large / xlarge"], ["Content library", "vks-kr-local"],
       ["網路", "primary-wl（自動帶入）"], ["權限", "administrator@vsphere.local = Owner"]], widths=[4, 12.5])
P("驗證：Namespace `config_status` = RUNNING。")

# ---- 4.11
PROC("4.11　建立 VKS cluster", "以 kubectl 建立 VKS cluster，節點信任 Harbor CA。", "admin（Supervisor context `vks-ns01`）",
     "§4.9、§4.10 完成")
P("ClusterClass `builtin-generic-v3.7.0` 使用 Cluster API v1beta2，重點欄位如下（完整 manifest 見附錄 B）：")
TABLE([["欄位", "值 / 說明"],
       ["`spec.topology.classRef`", "`{name: builtin-generic-v3.7.0, namespace: vmware-system-vks-public}`（取代 v1beta1 的 `topology.class`）"],
       ["`spec.topology.version`", "`v1.34.9+vmware.2-vkr.4`"],
       ["`spec.clusterNetwork`", "pods `10.244.0.0/16`、services `10.97.0.0/16`（預設 192.168.0.0/16 會與 lab 網段重疊）"],
       ["variables `vmClass` / `storageClass`", "`best-effort-medium` / `vcf-m01-cl01-vsan-storage-policy`（皆為必填）"],
       ["variable `osConfiguration.trust`", "`additionalTrustedCAs[].caCert.content` = Harbor CA PEM"]], widths=[5, 11.5])
CODE("""kubectl config use-context vks-ns01
kubectl apply --dry-run=server -f vks-test01.yaml     # webhook validates variables first
kubectl apply -f vks-test01.yaml
kubectl get cluster vks-test01 -n vks-ns01 -w
kubectl get secret vks-test01-kubeconfig -n vks-ns01 -o jsonpath='{.data.value}' | base64 -d > ~/vks-test01.kubeconfig""")
NOTE("variable 定義請查 ClusterClass 的 `status.variables[].definitions[]`，而不是 `spec.variables`。", "提示")
H(3, "驗證")
BL(["約 11 分鐘後 Cluster = Available；FLB 分配 API VIP 130.202；CP 與 worker 皆 Ready。",
    "節點 `curl https://harbor.alan.lab` 回 200（CA 已注入）。",
    "VKS 3.7 預設 Pod Security = `restricted:latest`：測試 pod 需設定 `runAsNonRoot`、`seccompProfile: RuntimeDefault`、"
    "`allowPrivilegeEscalation: false`、`capabilities.drop: [ALL]`，否則 `kubectl run` 會被拒絕。"])
NOTE("此時 workload 端 `helm-controller` addon 可能失敗（`Expected to find at least one version`），原因是 addon 套件庫仍指向公開網址，於 §4.12 修正。", "說明")

# ---- 4.12
PROC("4.12　addon 套件庫改指 Harbor",
     "讓 Supervisor 與 workload cluster 的 VKS addon 套件庫只從內部 Harbor 取得。",
     "bastion（imgpkg 下載）→ admin（imgpkg 推送、kubectl）",
     "§4.6.3 的 `vks-addons-3.7.0-20260618.tar` 已帶到 admin")
FIG("d4-addon-repo-override.png", "VKS 3.7 addon 套件庫：預設公開網址 → 改指 Harbor")
P("背景：VKS 3.7.0 的 `AddonRepository vmware-system-vks-public/builtin-addonrepository-3.7.0` 指向 "
  "`projects.packages.broadcom.com/.../vks-addons:3.7.0-20260618`，URL 寫死在 tanzu-addons-manager 的 kapp bundle，沒有設定可以修改；"
  "重新啟用 Supervisor 也只會產生相同的物件。自動使用內部 registry 的 `-regional-harbor` AddonRepository 只會在「VCF Software Depot + Harbor Supervisor Service」時產生。"
  "因此外部 registry 的官方做法為安裝後改指（TechDocs「Update an Add-on Repository Install」）。")
NOTE("路由或 DNS 可以上網時，Supervisor 端會顯示「Reconcile succeeded」，看起來正常，實際上正在使用外網。請以 image 來源盤點與切網驗證為準（§5）。", "重要")
H(3, "步驟")
STEPS(["推送 bundle 到 Harbor：`imgpkg copy --tar vks-addons-3.7.0-20260618.tar --to-repo harbor.alan.lab/vks/vks-addons`（專案 `vks` 設為 public）。",
       "備份：`kubectl get addonrepository,addonrepositoryinstall,pkgr -n vmware-system-vks-public -o yaml > ~/rollback/sv-addon-objs.yaml`。",
       "由 builtin 複製出**乾淨**的 AddonRepository：只改 name 與 imageURL；移除 `kapp.k14s.io/*`、`kubernetes.vmware.com/managed-by`、"
       "`last-applied-configuration`；保留 `package-offerings` annotation 與 `pkgr-type` label。",
       "每個修改先執行 `--dry-run=server`，通過後再正式執行。",
       "AddonRepositoryInstall 加上 skip annotation，再修改 `spec.addonRepositoryRef`。**不要**修改 `preferred-repository` annotation（webhook 只允許 addon manager SA）。"])
CODE("""K=kubectl; NS=vmware-system-vks-public
ARI=default-addon-repo-install-3.7.0-20260618; AR=harbor-addonrepository-3.7.0
IMG=harbor.alan.lab/vks/vks-addons:3.7.0-20260618
SKIP=addons.kubernetes.vmware.com/skip-vks-managed-addon-repository-update

# clean copy of the builtin AddonRepository (only name + imageURL change)
$K get addonrepository builtin-addonrepository-3.7.0 -n $NS -o json | jq --arg n $AR --arg img $IMG '
  {apiVersion, kind,
   metadata: {name: $n, namespace: .metadata.namespace,
     labels: ((.metadata.labels // {}) | with_entries(select((.key|startswith("kapp.k14s.io"))|not))
              | del(."kubernetes.vmware.com/managed-by")),
     annotations: ((.metadata.annotations // {}) | with_entries(select((.key|startswith("kapp.k14s.io"))
              or .key=="kubectl.kubernetes.io/last-applied-configuration" | not)))},
   spec: (.spec | .fetch.imgpkgBundle.imageURL = $img)}' > $AR.json
$K create -f $AR.json --dry-run=server && $K create -f $AR.json

# repoint the install
$K annotate ari $ARI -n $NS $SKIP=true --overwrite --dry-run=server && $K annotate ari $ARI -n $NS $SKIP=true --overwrite
P="{\\"spec\\":{\\"addonRepositoryRef\\":{\\"name\\":\\"$AR\\",\\"namespace\\":\\"$NS\\"}}}"
$K patch ari $ARI -n $NS --type merge -p "$P" --dry-run=server && $K patch ari $ARI -n $NS --type merge -p "$P\"""")
H(3, "驗證")
BL(["約 30 秒內 Supervisor 端 PackageRepository `vks-addons-3.7.0-20260618` 的 image = `harbor.alan.lab/...`，且 Reconcile succeeded。",
    "workload 端由 `carvel-repo` AddonConfig 自動重新渲染（來源為 Supervisor 上帶 `addons.kubernetes.vmware.com/carvel-pkgr=true` label 的 PackageRepository），約 2 分鐘內跟上。",
    "controller log 出現 `Set preferred repository annotation but skipped updating AddonRepositoryRef due to skip update annotation`。",
    "`preferred-repository` annotation 仍為 builtin（屬正常，不要修改）。"])
NOTE("VKS 升級（例如 add-on 3.7.0+20260723）會產生新的、指向公開網址的 AddonRepositoryInstall。升級後請對新版本重複本程序。", "重要")

# ---- 4.13
PROC("4.13　VCF CLI 與 plugins 離線安裝", "提供 `vcf` 指令操作 VKS cluster 與 addon。", "admin", "§4.6.4 的兩個檔案已帶到 admin")
CODE("""sha256sum -c <<< "74cf9b7e95b9460613bf7899d292ee6b53c95a3a77659ac9ccfdc450784bba99  VCF-Consumption-CLI-Linux_AMD64-9.1.1.0.25662425.tar.gz"
tar xzf VCF-Consumption-CLI-Linux_AMD64-9.1.1.0.25662425.tar.gz && sudo install vcf-cli-linux_amd64 /usr/local/bin/vcf
vcf version                                  # v9.1.1.0.25662425

mkdir -p ~/vcf-cli/plugin-bundle && tar xzf VCF-Consumption-CLI-PluginBundle-Linux_AMD64-9.1.1.0.25665404.tar.gz -C ~/vcf-cli/plugin-bundle
vcf plugin install all --local-source ~/vcf-cli/plugin-bundle     # 13 plugins

# reuse the kubectl-vsphere kubeconfig; create does not switch context
vcf context create sv01 --kubeconfig ~/.kube/config --kubecontext vks-ns01 --type k8s
vcf context use sv01
vcf cluster list
vcf addon repository list
vcf addon repository-install list""")
H(3, "驗證")
BL(["`vcf plugin list`：addon、cluster、kubernetes-release、package、registry-secret（v3.7.1）、argocd、imgpkg、namespaces、secret、telemetry、vm、objectstore、pais 共 13 個。",
    "`vcf cluster list` 顯示 vks-test01 running；`vcf addon repository-install list` 的 ARI 指向 `harbor-addonrepository-3.7.0` 且 READY。",
    "注意：`vcf kubernetes-release` 沒有 `list` 子指令，請使用 `get`。"])

# =====================================================================  5 VERIFICATION
H(1, "5　Air-Gap 驗證程序")
P("驗證目標：證明 VKS 在無法解析公開名稱的情況下仍可正常同步套件，而且所有 image 都來自邊界內部。本案於 2026-09-28 15:10–15:57Z 執行，DNS air-gap 全程開啟。")
H(2, "5.1　切斷外網（DNS 層級）")
CODE("""# depot / DNS VM
sudo sed -i 's/^server=/#AIRGAP-TEST# server=/' /etc/dnsmasq.d/alan-lab.conf     # no-resolv stays
sudo systemctl restart dnsmasq
dig +short @192.168.120.5 projects.packages.broadcom.com     # -> empty
dig +short @192.168.120.5 harbor.alan.lab                    # -> 192.168.120.80""")
NOTE("DNS 層級切斷不等於封包阻擋，直接用 IP 仍可出網；但 VKS 抓套件與 image 都使用主機名稱，因此足以證明套件同步不依賴公開 registry。正式環境請搭配防火牆規則。", "注意")
H(2, "5.2　驗證步驟與結果")
TABLE([["步驟", "動作", "預期結果", "實際結果"],
       ["1 現狀驗證", "切斷後觀察 30 分鐘（kapp pkgr 預設每 10 分同步）", "Supervisor 與 workload pkgr `updatedAt` > T0 且成功", "SV 15:20:48 / 15:30:59、WL 15:20:21 / 15:30:28 皆 Reconcile succeeded（Harbor）"],
       ["2 反向對照", "`--dry-run=server` 後移除 skip annotation", "ARI 退回 builtin，兩端因無法解析公開網址而失敗", "約 30 秒退回；錯誤 `lookup projects.packages.broadcom.com`；既有 addon 維持 succeeded"],
       ["3 清理重建", "刪除舊 AR，由 builtin 重建乾淨 AR", "kapp 引用 0、公開網址 0", "符合"],
       ["4 改指", "skip=true + addonRepositoryRef → Harbor", "兩端恢復", "約 30 秒恢復；15:53:50Z / 15:53:51Z 下一輪同步成功"],
       ["5 最終驗收", "`redo_step6_verify.sh`", "0 個外部 image", "符合（見 §5.3）"]], widths=[2.3, 4.5, 4.7, 5])
H(2, "5.3　驗收標準")
TABLE([["項目", "結果"],
       ["Supervisor", "k8s READY、無訊息；3 CP + 3 ESXi agent；tkg 3.7.0 / velero / cci-ns = CONFIGURED"],
       ["VKS cluster", "vks-test01 CP + worker Ready；`AddonsReconciled=True`；PackageInstall 全部 Reconcile succeeded"],
       ["addon 套件庫", "Supervisor 與 workload PackageRepository 皆來自 `harbor.alan.lab/vks/vks-addons`"],
       ["Supervisor image registry 集合", "`localhost:5000`、`docker-registry.kube-system.svc:5000`、`vmware/*`、`etcd`"],
       ["Workload image registry 集合", "`localhost:5000`（VKr 內建）、`harbor.alan.lab` → 0 個在允許清單外"],
       ["物件中的公開網址", "Supervisor 只剩未被引用的 `builtin-addonrepository-3.7.0`（kapp 管理）；workload 0"]], widths=[4.5, 12])
CODE("""allow='^(localhost:5000/|docker-registry\\.kube-system\\.svc:5000/|vmware/|etcd:|harbor\\.alan\\.lab/)'
kubectl get pods -A -o json | jq -r '.items[].spec | ((.containers//[]) + (.initContainers//[]))[].image' \\
  | sort -u | grep -vE "$allow"          # expect no output (compare sets, include initContainers)""")
H(2, "5.4　還原外網（需要時）")
CODE("""sudo sed -i 's/^#AIRGAP-TEST# server=/server=/' /etc/dnsmasq.d/alan-lab.conf && sudo systemctl restart dnsmasq
# bastion downloads done -> switch back to #AIRGAP-TEST#""")

# =====================================================================  6 TROUBLESHOOTING
H(1, "6　疑難排解與已知問題")
H(2, "6.1　問題對照表")
TABLE([["症狀", "原因", "處理方式"],
       ["bring-up validation：`VCF service runtime specification must be present`", "`vspClusterSpec` 為必填", "保留完整 spec，於 #272 中止（§4.1）"],
       ["中止監看程式一啟動就觸發", "未開始的 subtask 為 `INITIALIZED`", "閒置狀態集合加入 `INITIALIZED`"],
       ["Supervisor RUNNING 但出現「No node is accepting vSphere Pods」，cci-ns Pending", "vLCM FINALIZE 健康檢查被 vSAN NVMe HCL 擋住，Spherelet 未安裝", "silence `nvmeonhcl`（§4.2）；不是 VDS 的限制"],
       ["flb-mgmt IP pool 使用率 > 95% 警告", "FLB 管理網只給 2 個 IP", "新增範圍 `{97,1}`；使用中的網路不可修改既有範圍"],
       ["workload 節點解析不到 harbor.alan.lab", "dnsmasq `--local-service` 不回應 routed subnet", "`listen-address` 設定（§3.2）"],
       ["切斷 upstream 後仍可解析公開名稱", "`/etc/dnsmasq.d/` 內的 `.bak` 備份檔被載入", "備份檔移到設定目錄外"],
       ["workload `helm-controller` addon 失敗", "addon 套件庫指向公開網址", "§4.12"],
       ["ARI 修改被 webhook 拒絕", "未加 skip annotation，或修改了 `preferred-repository`", "先加 skip annotation；不要修改 `preferred-repository`"],
       ["`kubectl run` 建不出 pod", "Pod Security `restricted:latest`", "補齊 securityContext"],
       ["Supervisor 下載 VCF CLI 回 503", "沒有 VCF Software Depot / FDS 時 nginx 固定回 503", "Support Portal 下載（§4.6.4）"],
       ["Cluster 與 lab 網段衝突", "預設 pod CIDR 192.168.0.0/16", "明確指定 CIDR"]], widths=[5.5, 5.5, 5.5])
H(2, "6.2　DNS 設定（dnsmasq）")
CODE("""# /etc/dnsmasq.d/05-listen.conf  — answers routed subnets (130.x) despite Ubuntu's --local-service
listen-address=127.0.0.1,192.168.110.85,192.168.120.5
# verify from a workload node:  getent hosts harbor.alan.lab  -> 192.168.120.80""")
H(2, "6.3　除錯入口")
BL(["Supervisor CP root：在 vCenter root shell 執行 `/usr/lib/vmware-wcp/decryptK8Pwd.py` 取得 IP 與密碼（密碼不要落檔）。",
    "vLCM / Spherelet：VCSA `/var/log/vmware/vmware-updatemgr/vum-server/`。",
    "addon：`kubectl logs -n <ns> deploy/tanzu-addons-controller-manager`；ARI `status.conditions`；pkgr `status.usefulErrorMessage`。",
    "SSO Administrator 無權叢集層級 list kapp App / PackageRepository（Forbidden），請逐 namespace 查詢。"])

# =====================================================================  7 LIMITS
H(1, "7　限制與後續工作")
BL(["builtin AddonRepository（公開網址）由 kapp 管理，會一直存在，但不會被引用。",
    "VKS 升級後需對新版本的 AddonRepositoryInstall 重複 §4.12；在升級前預先建立屬於實驗性做法。",
    "本案 air-gap 為 DNS 層級；正式環境請以防火牆阻擋非 RFC1918 目的地並檢查 log。",
    "9.1 的 air-gap 參考架構假設有 VCF Software Depot；外部 registry 流程出自 9.0 指南。本案屬文件化的 override，不是 9.1 藍圖。",
    "後續驗證：以 `vcf addon` 安裝 cert-manager / contour；在 air-gap 下將 cluster 升級至 v1.35.6。"])

# =====================================================================  APPENDIX
H(1, "附錄 A　腳本與 log 對照")
TABLE([["腳本（vks-airgap/scripts）", "用途", "log（vks-airgap/logs）"],
       ["prep_hosts.py / validate.py / installer_api.py", "ESXi 前置、bring-up 驗證與送出", "02、03"],
       ["abort_watcher.py / verify_after_abort.py", "#272 觸發中止、中止後驗證", "04、05"],
       ["create_workload_pg.py / test_routed_subnets.py", "workload portgroup 與 130.x 路由測試", "06、07"],
       ["watch_supervisor.py / cdp.py", "Supervisor 啟用（精靈 CDP 自動化）與監看", "08–10"],
       ["vsan_silence_nvme_hcl.py / watch_apply_solution.py", "silence nvmeonhcl、監看 vLCM", "25–31"],
       ["deploy_helper_vms.py", "bastion / harbor / admin", "12、13"],
       ["bastion_prep.sh / harbor_install.sh", "Docker + Harbor 離線安裝", "14–16"],
       ["bastion_tools.sh / bastion_download_vks.sh / admin_import.sh", "工具、VKr、匯入", "17–22"],
       ["watch_vks_cluster.sh", "vks-test01 建立監看", "35–37"],
       ["switch_addon_repo.sh / redo_steps3to5.sh / redo_step6_verify.sh / watch_step2.sh", "addon 套件庫改指與 air-gap 驗證", "39–45、51–55"]], widths=[6.5, 6, 4])
H(1, "附錄 B　vks-test01 Cluster manifest")
yml = open(os.path.join(ROOT, "manifests", "vks-test01.yaml"), encoding="utf-8").read()
yml = re.sub(r"(-----BEGIN CERTIFICATE-----\n)(?:.*\n)*?(\s*-----END CERTIFICATE-----)", r"\1                <Harbor CA PEM — vks-airgap/certs/harbor-ca.crt>\n\2", yml)
CODE(yml)

doc.save(OUT)
print("saved", OUT)
