#!/usr/bin/env python3
"""clone-slide.py — 從官方 pptx 範本複製整頁、只換文字。

為什麼要有這支：一張官方內容頁的 XML 約 290,000 字元，其中純文字只有約 950 字元。
「複製整頁再換字」讓你用 1/300 的成本拿到 100% 的官方美術（配色、對齊、圖形、陰影全在）。
反過來用 python-pptx 從空白頁「照規格畫」既貴又不像 —— 不要那樣做。

用法
----
  # 1. 看範本有哪些頁、每頁是什麼版型、有哪些欄位可填（便宜，先做這步）
  clone-slide.py list deck.pptx
  clone-slide.py list deck.pptx --slide 6

  # 2. 複製第 6 頁到最後，順便換掉文字
  clone-slide.py clone deck.pptx --slide 6 --out new.pptx \
      --title "Deploy vSAN without Purchasing New Servers" \
      --subtitle "Repurposing vSphere hosts for VMware vSAN" \
      --bullets "既有主機沿用|不必採購新伺服器|授權額度已含"

  # 3. 只改文字，不複製
  clone-slide.py settext deck.pptx --slide 12 --out new.pptx --title "..."

  # 4. 只留下要的頁（其餘刪掉），順序照給的順序
  clone-slide.py keep deck.pptx --slides 1,2,3,5,6,28 --out new.pptx

欄位怎麼指定
------------
  --title / --subtitle        對應 ph type="title" / "subTitle"
  --bullets "a|b|c"           填第一個 body placeholder，用 | 分行
                              行首加 "1:" / "2:" 可指定縮排層級，例如 "1:子項目"
  --set 'body:17=文字內容'     直接指定 placeholder（type 或 type:idx），可重複
                              多行同樣用 | 分隔

限制（誠實說明）
----------------
  * 只換 placeholder 裡的文字。頁面上的圖、示意圖裡的文字方塊不是 placeholder，不會被動到 ——
    那正是你要的：美術原封不動。**但也代表圖不會跟著你的新標題改**，所以要挑一張
    「圖已經對」的頁來複製，不要拿壓縮示意圖的頁去講授權。
  * **不支援 markdown**。寫 `**粗體**` 會原樣印出兩個星號。
    整段的字體/字級/顏色沿用原頁（本來就對），需要局部粗體請在 PowerPoint 裡手動處理。
  * 段落格式沿用原頁第一段的 pPr（bullet 樣式、縮排）；不會幫你重新設計排版。
  * 需要 lxml（macOS 內建 python3 通常已有；沒有就 pip3 install lxml）。

QA
--
  soffice --headless --convert-to pdf --outdir qa out.pptx
  pdftoppm -png -r 70 -f 4 -l 4 qa/out.pdf qa/slide      # 只渲染要看的那幾頁
"""

import argparse
import copy
import os
import re
import shutil
import sys
import zipfile

try:
    from lxml import etree
except ImportError:
    sys.exit("需要 lxml：pip3 install lxml")

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

SLIDE_CT = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
SLIDE_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"

q = lambda ns, tag: "{%s}%s" % (ns, tag)


class Deck:
    """把 pptx 當成一包 part（路徑 -> bytes）處理，改完再壓回去。"""

    def __init__(self, path):
        self.parts = {}
        with zipfile.ZipFile(path) as z:
            self.names = z.namelist()
            for n in self.names:
                self.parts[n] = z.read(n)

    # ---------- XML helpers ----------
    def xml(self, name):
        return etree.fromstring(self.parts[name])

    def put(self, name, tree):
        self.parts[name] = etree.tostring(
            tree, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    # ---------- slide order ----------
    def slide_order(self):
        """回傳 [(sldId, rId, part_name), ...] 依簡報實際順序。"""
        pres = self.xml("ppt/presentation.xml")
        rels = self.xml("ppt/_rels/presentation.xml.rels")
        rid2tgt = {
            r.get("Id"): r.get("Target")
            for r in rels
            if r.get("Type") == SLIDE_RT
        }
        out = []
        lst = pres.find(q(P, "sldIdLst"))
        for sid in lst:
            rid = sid.get(q(R, "id"))
            tgt = rid2tgt[rid]
            out.append((sid.get("id"), rid, "ppt/slides/" + tgt.split("/")[-1]))
        return out

    def layout_of(self, slide_part):
        rp = slide_part.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
        m = re.search(rb"slideLayouts/(slideLayout\d+\.xml)", self.parts[rp])
        if not m:
            return "?", "?"
        lf = m.group(1).decode()
        name = re.search(
            rb'<p:cSld[^>]*name="([^"]*)"', self.parts["ppt/slideLayouts/" + lf]
        )
        return lf, (name.group(1).decode() if name else "?")

    # ---------- placeholders ----------
    @staticmethod
    def placeholders(slide_xml):
        """回傳 [(key, sp_element, 目前文字)]，key 形如 'title' / 'body:17'。"""
        out = []
        for sp in slide_xml.iter(q(P, "sp")):
            ph = sp.find(".//" + q(P, "ph"))
            if ph is None:
                continue
            t = ph.get("type") or "body"
            idx = ph.get("idx")
            key = "%s:%s" % (t, idx) if idx else t
            tx = sp.find(q(P, "txBody"))
            txt = ""
            if tx is not None:
                txt = " ".join(e.text or "" for e in tx.iter(q(A, "t")))
            out.append((key, sp, txt))
        return out

    @staticmethod
    def set_text(sp, lines):
        """把一個 placeholder 的文字換成 lines（[(level, text), ...]）。

        沿用原本第一段的 pPr 與第一個 run 的 rPr，所以字體/字級/顏色/bullet 樣式不變。
        """
        tx = sp.find(q(P, "txBody"))
        if tx is None:
            return False
        paras = tx.findall(q(A, "p"))
        if not paras:
            return False
        proto_p = paras[0]
        proto_pPr = proto_p.find(q(A, "pPr"))
        proto_r = proto_p.find(q(A, "r"))
        proto_rPr = proto_r.find(q(A, "rPr")) if proto_r is not None else None
        endPara = tx.find(q(A, "endParaRPr"))

        for p_el in paras:
            tx.remove(p_el)

        anchor = endPara if endPara is not None else None
        for level, text in lines:
            p_el = etree.SubElement(tx, q(A, "p"))
            if proto_pPr is not None:
                pPr = copy.deepcopy(proto_pPr)
                p_el.append(pPr)
            elif level:
                pPr = etree.SubElement(p_el, q(A, "pPr"))
            else:
                pPr = None
            if level:
                if pPr is None:
                    pPr = etree.SubElement(p_el, q(A, "pPr"))
                    p_el.insert(0, pPr)
                pPr.set("lvl", str(level))
            r_el = etree.SubElement(p_el, q(A, "r"))
            if proto_rPr is not None:
                r_el.append(copy.deepcopy(proto_rPr))
            t_el = etree.SubElement(r_el, q(A, "t"))
            t_el.text = text
            if anchor is not None:
                tx.remove(p_el)
                anchor.addprevious(p_el)
        return True

    # ---------- mutations ----------
    def clone(self, src_part, at=None):
        """複製一張投影片到簡報裡，回傳新 part 名稱。"""
        used = [
            int(m.group(1))
            for n in self.parts
            for m in [re.fullmatch(r"ppt/slides/slide(\d+)\.xml", n)]
            if m
        ]
        new_n = max(used) + 1
        new_part = "ppt/slides/slide%d.xml" % new_n
        self.parts[new_part] = self.parts[src_part]

        src_rels = src_part.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
        if src_rels in self.parts:
            self.parts[
                new_part.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
            ] = self.parts[src_rels]

        ct = self.xml("[Content_Types].xml")
        ov = etree.SubElement(ct, q(CT, "Override"))
        ov.set("PartName", "/" + new_part)
        ov.set("ContentType", SLIDE_CT)
        self.put("[Content_Types].xml", ct)

        rels = self.xml("ppt/_rels/presentation.xml.rels")
        nums = [
            int(m.group(1))
            for r in rels
            for m in [re.fullmatch(r"rId(\d+)", r.get("Id") or "")]
            if m
        ]
        new_rid = "rId%d" % (max(nums) + 1)
        rel = etree.SubElement(rels, q(PKG_REL, "Relationship"))
        rel.set("Id", new_rid)
        rel.set("Type", SLIDE_RT)
        rel.set("Target", "slides/slide%d.xml" % new_n)
        self.put("ppt/_rels/presentation.xml.rels", rels)

        pres = self.xml("ppt/presentation.xml")
        lst = pres.find(q(P, "sldIdLst"))
        ids = [int(s.get("id")) for s in lst]
        sid = etree.SubElement(lst, q(P, "sldId"))
        sid.set("id", str(max(max(ids), 255) + 1))
        sid.set(q(R, "id"), new_rid)
        if at is not None:
            lst.remove(sid)
            lst.insert(at, sid)
        self.put("ppt/presentation.xml", pres)
        return new_part

    def keep(self, keep_parts):
        """只保留指定的投影片，順序照 keep_parts。"""
        order = self.slide_order()
        part2rid = {p: rid for _, rid, p in order}
        pres = self.xml("ppt/presentation.xml")
        lst = pres.find(q(P, "sldIdLst"))
        by_part = {}
        for sid in list(lst):
            rid = sid.get(q(R, "id"))
            for _, r2, p2 in order:
                if r2 == rid:
                    by_part[p2] = sid
            lst.remove(sid)
        for p in keep_parts:
            lst.append(by_part[p])
        self.put("ppt/presentation.xml", pres)

        drop = [p for p in part2rid if p not in keep_parts]
        rels = self.xml("ppt/_rels/presentation.xml.rels")
        drop_rids = {part2rid[p] for p in drop}
        for r in list(rels):
            if r.get("Id") in drop_rids:
                rels.remove(r)
        self.put("ppt/_rels/presentation.xml.rels", rels)

        ct = self.xml("[Content_Types].xml")
        drop_names = {"/" + p for p in drop}
        for o in list(ct):
            if o.get("PartName") in drop_names:
                ct.remove(o)
        self.put("[Content_Types].xml", ct)

        for p in drop:
            self.parts.pop(p, None)
            self.parts.pop(
                p.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels", None
            )

    def save(self, out):
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for n in self.names:
                if n in self.parts:
                    z.writestr(n, self.parts[n])
            for n in self.parts:
                if n not in self.names:
                    z.writestr(n, self.parts[n])


def parse_lines(spec):
    out = []
    for chunk in spec.split("|"):
        chunk = chunk.strip()
        m = re.match(r"^([0-9]):(.*)$", chunk)
        if m:
            out.append((int(m.group(1)), m.group(2).strip()))
        else:
            out.append((0, chunk))
    return out


def apply_text(deck, part, args):
    sx = deck.xml(part)
    phs = deck.placeholders(sx)
    todo = []
    if args.title:
        todo.append(("title", args.title))
    if args.subtitle:
        todo.append(("subTitle", args.subtitle))
    if args.bullets:
        body = next((k for k, _, _ in phs if k.startswith("body")), None)
        if body is None:
            sys.exit("這一頁沒有 body placeholder，改用 --set 指定")
        todo.append((body, args.bullets))
    for s in args.set or []:
        k, _, v = s.partition("=")
        todo.append((k.strip(), v))

    missing = []
    for key, val in todo:
        hit = [sp for k, sp, _ in phs if k == key or k.split(":")[0] == key]
        if not hit:
            missing.append(key)
            continue
        deck.set_text(hit[0], parse_lines(val))
    if missing:
        sys.stderr.write(
            "略過（這一頁沒有這些 placeholder）：%s\n  可用："
            % ", ".join(missing)
            + ", ".join(k for k, _, _ in phs)
            + "\n"
        )
    deck.put(part, sx)


def cmd_list(args):
    d = Deck(args.pptx)
    order = d.slide_order()
    if args.slide:
        idx = args.slide - 1
        if not 0 <= idx < len(order):
            sys.exit("沒有第 %d 頁（共 %d 頁）" % (args.slide, len(order)))
        part = order[idx][2]
        lf, ln = d.layout_of(part)
        print("slide %d  版型: %s  (%s)" % (args.slide, ln, lf))
        for k, _, txt in d.placeholders(d.xml(part)):
            print("  %-12s %s" % (k, (txt[:90] + "…") if len(txt) > 90 else txt))
        return
    for i, (_, _, part) in enumerate(order, 1):
        lf, ln = d.layout_of(part)
        phs = d.placeholders(d.xml(part))
        title = next((t for k, _, t in phs if k == "title"), "")
        print("%3d  %-34s %s" % (i, ln[:34], title[:48]))


def cmd_clone(args):
    d = Deck(args.pptx)
    order = d.slide_order()
    idx = args.slide - 1
    if not 0 <= idx < len(order):
        sys.exit("沒有第 %d 頁（共 %d 頁）" % (args.slide, len(order)))
    at = (args.at - 1) if args.at else None
    new_part = d.clone(order[idx][2], at=at)
    apply_text(d, new_part, args)
    d.save(args.out)
    print("已複製 slide %d → %s（新頁在第 %d 頁）"
          % (args.slide, args.out, (args.at or len(order) + 1)))


def cmd_settext(args):
    d = Deck(args.pptx)
    order = d.slide_order()
    idx = args.slide - 1
    if not 0 <= idx < len(order):
        sys.exit("沒有第 %d 頁（共 %d 頁）" % (args.slide, len(order)))
    apply_text(d, order[idx][2], args)
    d.save(args.out)
    print("已更新 slide %d → %s" % (args.slide, args.out))


def cmd_keep(args):
    d = Deck(args.pptx)
    order = d.slide_order()
    want = [int(x) for x in args.slides.split(",")]
    for n in want:
        if not 1 <= n <= len(order):
            sys.exit("沒有第 %d 頁（共 %d 頁）" % (n, len(order)))
    d.keep([order[n - 1][2] for n in want])
    d.save(args.out)
    print("保留 %d 頁 → %s" % (len(want), args.out))


def main():
    ap = argparse.ArgumentParser(
        description="從官方 pptx 範本複製整頁、只換文字",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法", 1)[1] if "用法" in __doc__ else None,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def text_args(p):
        p.add_argument("--title")
        p.add_argument("--subtitle")
        p.add_argument("--bullets", help='用 | 分行，行首 "1:" 指定縮排層級')
        p.add_argument("--set", action="append",
                       help="placeholder=文字，例如 'body:17=第一行|第二行'")

    p = sub.add_parser("list", help="列出投影片 / 單頁的可填欄位")
    p.add_argument("pptx")
    p.add_argument("--slide", type=int)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("clone", help="複製一頁並換文字")
    p.add_argument("pptx")
    p.add_argument("--slide", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--at", type=int, help="插到第幾頁（預設放最後）")
    text_args(p)
    p.set_defaults(func=cmd_clone)

    p = sub.add_parser("settext", help="只換某頁的文字")
    p.add_argument("pptx")
    p.add_argument("--slide", type=int, required=True)
    p.add_argument("--out", required=True)
    text_args(p)
    p.set_defaults(func=cmd_settext)

    p = sub.add_parser("keep", help="只保留指定頁，順序照給的順序")
    p.add_argument("pptx")
    p.add_argument("--slides", required=True, help="例如 1,2,3,5,28")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_keep)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
