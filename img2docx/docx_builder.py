"""IR (schema.Document) -> .docx with correct RTL/bidi structure.

python-docx for the skeleton, raw OOXML for what it lacks: w:bidi (paragraph + section), w:rtl,
w:rFonts/@w:cs, w:szCs, w:bCs, w:bidiVisual, floating (anchored) stamp images.
"""
from __future__ import annotations

import copy
import logging
from pathlib import Path

from docx import Document as new_docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Mm, Pt

from .config import DocxCfg
from .postprocess import split_bidi_runs, text_direction
from .schema import Block, Document
from .tables import parse_html_table

log = logging.getLogger(__name__)
EMU_PER_MM = 36000


# --------------------------------------------------------------------------- low-level OOXML helpers
def _get_or_add(parent, tag: str, first: bool = False):
    el = parent.find(qn(tag))
    if el is None:
        el = OxmlElement(tag)
        if first:
            parent.insert(0, el)
        else:
            parent.append(el)
    return el


def _set_rfonts(rpr, latin: str, cs: str):
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.insert(0, rf)
    rf.set(qn("w:ascii"), latin)
    rf.set(qn("w:hAnsi"), latin)
    rf.set(qn("w:eastAsia"), latin)
    rf.set(qn("w:cs"), cs)


def _set_size(rpr, size_pt: float):
    half = str(int(round(size_pt * 2)))
    for tag in ("w:sz", "w:szCs"):
        el = _get_or_add(rpr, tag)
        el.set(qn("w:val"), half)


def _set_lang(rpr, bidi="ar-SA", val="en-US"):
    el = _get_or_add(rpr, "w:lang")
    el.set(qn("w:val"), val)
    el.set(qn("w:bidi"), bidi)


# CT_RPr child order matters for strict validators (Word is tolerant, LibreOffice too) – keep canonical order.
_RPR_ORDER = ["w:rStyle", "w:rFonts", "w:b", "w:bCs", "w:i", "w:iCs", "w:caps", "w:smallCaps", "w:strike", "w:dstrike",
              "w:outline", "w:shadow", "w:emboss", "w:imprint", "w:noProof", "w:snapToGrid", "w:vanish", "w:webHidden",
              "w:color", "w:spacing", "w:w", "w:kern", "w:position", "w:sz", "w:szCs", "w:highlight", "w:u",
              "w:effect", "w:bdr", "w:shd", "w:fitText", "w:vertAlign", "w:rtl", "w:cs", "w:em", "w:lang",
              "w:eastAsianLayout", "w:specVanish", "w:oMath"]


def _sort_children(el, order):
    rank = {qn(t): i for i, t in enumerate(order)}
    kids = list(el)
    kids.sort(key=lambda k: rank.get(k.tag, 999))
    for k in kids:
        el.remove(k)
    for k in kids:
        el.append(k)


_PPR_ORDER = ["w:pStyle", "w:keepNext", "w:keepLines", "w:pageBreakBefore", "w:framePr", "w:widowControl", "w:numPr",
              "w:suppressLineNumbers", "w:pBdr", "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
              "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd",
              "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap",
              "w:jc", "w:textDirection", "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId",
              "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange"]


def set_paragraph_bidi(p, rtl: bool):
    """Always explicit: on RTL pages the Normal style is bidi, so LTR paragraphs need w:val="0"."""
    ppr = p._p.get_or_add_pPr()
    el = ppr.find(qn("w:bidi"))
    if el is None:
        el = OxmlElement("w:bidi")
        ppr.append(el)
    if rtl:
        el.attrib.pop(qn("w:val"), None)
    else:
        el.set(qn("w:val"), "0")
    _sort_children(ppr, _PPR_ORDER)


def set_alignment(p, align: str | None, rtl: bool):
    """Alignment in *visual* terms (left/right/center/justify).

    For bidi paragraphs, Word and LibreOffice interpret w:jc left/right logically (left=start=right
    edge), so visual 'right' on an RTL paragraph is written as 'left' (= start). Verified by rendering
    through LibreOffice (see tests/test_docx_render.py).
    """
    ppr = p._p.get_or_add_pPr()
    jc = ppr.find(qn("w:jc"))
    if jc is not None:
        ppr.remove(jc)
    if align is None:
        return
    val = {"center": "center", "justify": "both"}.get(align)
    if val is None:
        if rtl:
            val = "left" if align == "right" else "right"
        else:
            val = align
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), val)
    ppr.append(jc)
    _sort_children(ppr, _PPR_ORDER)


def set_spacing(p, before_pt: float = 0, after_pt: float = 4, line: float | None = None):
    ppr = p._p.get_or_add_pPr()
    sp = _get_or_add(ppr, "w:spacing")
    sp.set(qn("w:before"), str(int(before_pt * 20)))
    sp.set(qn("w:after"), str(int(after_pt * 20)))
    if line:
        sp.set(qn("w:line"), str(int(240 * line)))
        sp.set(qn("w:lineRule"), "auto")
    _sort_children(ppr, _PPR_ORDER)


# --------------------------------------------------------------------------- builder
class DocxBuilder:
    def __init__(self, cfg: DocxCfg):
        self.cfg = cfg
        self._doc = None

    # -- run / paragraph
    def add_runs(self, p, text: str, base: str, size_pt: float, bold: bool = False, highlight: bool = False):
        runs = []
        lines = text.split("\n")
        for li, line in enumerate(lines):
            for seg, d in split_bidi_runs(line, base):
                r = p.add_run(seg)
                rpr = r._r.get_or_add_rPr()
                _set_rfonts(rpr, self.cfg.font_latin, self.cfg.font_cs)
                if bold:
                    _get_or_add(rpr, "w:b"); _get_or_add(rpr, "w:bCs")
                _set_size(rpr, size_pt)
                if highlight:
                    _get_or_add(rpr, "w:highlight").set(qn("w:val"), "yellow")
                if d == "rtl":
                    _get_or_add(rpr, "w:rtl")
                _set_lang(rpr)
                _sort_children(rpr, _RPR_ORDER)
                runs.append(r)
            if li < len(lines) - 1:
                br = p.add_run()
                br.add_break(WD_BREAK.LINE)
                if base == "rtl":
                    _get_or_add(br._r.get_or_add_rPr(), "w:rtl")
                runs.append(br)
        return runs

    def text_paragraph(self, container, b: Block, size_pt: float, align: str | None, before_pt: float, keep_breaks: bool):
        direction = b.direction or text_direction(b.text)
        rtl = direction == "rtl"
        p = container.add_paragraph()
        set_paragraph_bidi(p, rtl)
        set_alignment(p, align, rtl)
        set_spacing(p, before_pt, 3, 1.15)
        text = b.text or ""
        if not keep_breaks:
            text = " ".join(t.strip() for t in text.split("\n") if t.strip())
        low = self._low(b)
        runs = self.add_runs(p, text, direction, size_pt, bold=bool(b.style.bold), highlight=low and self.cfg.highlight_low_confidence)
        if low and self.cfg.comment_low_confidence and runs and self._doc is not None:
            msg = f"confidence {b.confidence:.2f}" + (": " + "; ".join(b.review_reasons[:4]) if b.review_reasons else "")
            try:
                self._doc.add_comment(runs, text=msg, author="img2docx", initials="OCR")
            except Exception as e:  # pragma: no cover
                log.warning("could not add comment: %s", e)
        return p

    def _low(self, b: Block) -> bool:
        return b.confidence is not None and b.confidence < self.cfg.low_confidence_threshold

    def size_for(self, b: Block) -> float:
        s = b.style.size_pt or self.cfg.default_size_pt
        return float(min(self.cfg.max_size_pt, max(self.cfg.min_size_pt, round(s * 2) / 2)))

    # -- tables
    def table(self, container, b: Block, size_pt: float, rtl: bool):
        cells, nrows, ncols = parse_html_table(b.html or "")
        if not cells:
            return None
        t = container.add_table(rows=nrows, cols=ncols)
        try:
            t.style = "Table Grid"
        except Exception:
            pass
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        tblpr = t._tbl.tblPr
        if rtl:
            tblpr.append(OxmlElement("w:bidiVisual"))
            _sort_children(tblpr, ["w:tblStyle", "w:tblpPr", "w:tblOverlap", "w:bidiVisual", "w:tblStyleRowBandSize",
                                   "w:tblStyleColBandSize", "w:tblW", "w:jc", "w:tblCellSpacing", "w:tblInd",
                                   "w:tblBorders", "w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook"])
        low = self._low(b) and self.cfg.highlight_low_confidence
        for c in cells:
            r1, c1 = min(nrows - 1, c.row + c.rowspan - 1), min(ncols - 1, c.col + c.colspan - 1)
            cell = t.cell(c.row, c.col)
            if (r1, c1) != (c.row, c.col):
                cell = cell.merge(t.cell(r1, c1))
            p = cell.paragraphs[0]
            d = text_direction(c.text, "rtl" if rtl else "ltr")
            set_paragraph_bidi(p, d == "rtl")
            set_alignment(p, "center", d == "rtl")
            set_spacing(p, 0, 0, 1.0)
            self.add_runs(p, c.text, d, size_pt, bold=c.header, highlight=low)
            if c.header:
                tcpr = cell._tc.get_or_add_tcPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), "E7E6E6")
                tcpr.append(shd)
        return t

    # -- images
    def picture_paragraph(self, container, b: Block, page_w_mm: float, px_per_mm: float, assets_root: Path,
                          align: str, rtl: bool, before_pt: float):
        path = assets_root / b.image_path if b.image_path else None
        if not path or not path.exists():
            return None
        p = container.add_paragraph()
        set_paragraph_bidi(p, rtl)
        set_alignment(p, align, rtl)
        set_spacing(p, before_pt, 2, 1.0)
        width_mm = max(8.0, min(page_w_mm * 0.9, b.bbox.w / px_per_mm))
        p.add_run().add_picture(str(path), width=Mm(width_mm))
        return p

    def floating_picture(self, container, b: Block, px_per_mm: float, assets_root: Path, rtl: bool):
        """Stamp image anchored to the page at its original position, behind text."""
        path = assets_root / b.image_path if b.image_path else None
        if not path or not path.exists():
            return None
        p = container.add_paragraph()
        set_paragraph_bidi(p, rtl)
        set_spacing(p, 0, 0, 1.0)
        run = p.add_run()
        run.add_picture(str(path), width=Mm(max(8.0, b.bbox.w / px_per_mm)))
        inline = run._r.find(".//" + qn("wp:inline"))
        if inline is None:
            return p
        anchor = OxmlElement("wp:anchor")
        for k, v in dict(distT="0", distB="0", distL="0", distR="0", simplePos="0", relativeHeight="251659264",
                         behindDoc="1", locked="0", layoutInCell="1", allowOverlap="1").items():
            anchor.set(k, v)
        sp = OxmlElement("wp:simplePos"); sp.set("x", "0"); sp.set("y", "0"); anchor.append(sp)
        for axis, val in (("H", b.bbox.x0), ("V", b.bbox.y0)):
            pos = OxmlElement(f"wp:position{axis}")
            pos.set("relativeFrom", "page")
            off = OxmlElement("wp:posOffset")
            off.text = str(int(val / px_per_mm * EMU_PER_MM))
            pos.append(off)
            anchor.append(pos)
        anchor.append(copy.deepcopy(inline.find(qn("wp:extent"))))
        ee = OxmlElement("wp:effectExtent")
        for k in "ltrb":
            ee.set(k, "0")
        anchor.append(ee)
        anchor.append(OxmlElement("wp:wrapNone"))
        for tag in ("wp:docPr", "wp:cNvGraphicFramePr"):
            el = inline.find(qn(tag))
            if el is not None:
                anchor.append(copy.deepcopy(el))
        anchor.append(copy.deepcopy(inline.find(qn("a:graphic"))))
        inline.getparent().replace(inline, anchor)
        return p

    # -- header / footer
    def band(self, part, blocks: list[Block], page: "Page", px_per_mm: float, assets_root: Path, rtl: bool, content_w_mm: float):
        """Header/footer band: blocks placed in a borderless 3-column table by visual x position."""
        if not blocks:
            return
        W = page.width_px
        cols: dict[int, list[Block]] = {0: [], 1: [], 2: []}
        for b in blocks:
            cx = b.bbox.cx / W
            cols[0 if cx < 0.36 else (2 if cx > 0.64 else 1)].append(b)
        used = [k for k in cols if cols[k]]
        if len(used) == 1 and len(blocks) == 1:
            b = blocks[0]
            align = ["left", "center", "right"][used[0]]
            self._band_block(part, b, align, px_per_mm, assets_root, page)
            return
        t = part.add_table(rows=1, cols=3, width=Mm(content_w_mm))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        # Make the table direction explicit: LibreOffice otherwise inherits RTL from the section
        # while Word does not. With bidiVisual, cell 0 is the *right* cell in both.
        visual = ("left", "center", "right")
        if rtl:
            t._tbl.tblPr.append(OxmlElement("w:bidiVisual"))
            _sort_children(t._tbl.tblPr, ["w:tblStyle", "w:tblpPr", "w:tblOverlap", "w:bidiVisual", "w:tblW", "w:jc",
                                          "w:tblInd", "w:tblBorders", "w:tblLayout", "w:tblCellMar", "w:tblLook"])
            visual = ("right", "center", "left")
        slot = {"left": 0, "center": 1, "right": 2}
        for k, align in enumerate(visual):
            cell = t.cell(0, k)
            cell.width = Mm(content_w_mm / 3)
            first = True
            for b in sorted(cols[slot[align]], key=lambda b: b.bbox.y0):
                if first:
                    cell._tc.remove(cell.paragraphs[0]._p)
                    first = False
                self._band_block(cell, b, align, px_per_mm, assets_root, page)

    def _band_block(self, container, b: Block, align: str, px_per_mm: float, assets_root: Path, page):
        if b.type in ("logo", "figure", "stamp", "signature"):
            if self.cfg.insert_images and b.image_path:
                path = assets_root / b.image_path
                if path.exists():
                    p = container.add_paragraph()
                    set_alignment(p, align, False)
                    p.add_run().add_picture(str(path), width=Mm(max(8.0, min(60.0, b.bbox.w / px_per_mm))))
            return
        rtl = (b.direction or text_direction(b.text)) == "rtl"
        p = self.text_paragraph(container, b, self.size_for(b), align, 0, keep_breaks=True)
        set_alignment(p, align, rtl)

    # -- document
    def build(self, doc: Document, out_path: str | Path, assets_root: str | Path) -> Path:
        out_path = Path(out_path)
        assets_root = Path(assets_root)
        d = new_docx()
        self._doc = d
        page = doc.page
        rtl_page = page.direction == "rtl"
        px_per_mm = page.width_px / page.width_mm
        sec = d.sections[0]
        sec.page_width, sec.page_height = Mm(page.width_mm), Mm(page.height_mm)
        blocks = doc.ordered_blocks()
        body_blocks = [b for b in blocks if b.type not in ("header", "footer") and not (b.type == "logo" and b.bbox.cy < page.height_px * 0.2)]
        header_blocks = [b for b in blocks if b.type == "header" or (b.type == "logo" and b.bbox.cy < page.height_px * 0.2)]
        footer_blocks = [b for b in blocks if b.type == "footer"]
        # margins from content extent
        xs0 = [b.bbox.x0 for b in body_blocks] or [page.width_px * 0.1]
        xs1 = [b.bbox.x1 for b in body_blocks] or [page.width_px * 0.9]
        ml = min(30.0, max(12.0, min(xs0) / px_per_mm))
        mr = min(30.0, max(12.0, (page.width_px - max(xs1)) / px_per_mm))
        sec.left_margin, sec.right_margin = Mm(ml), Mm(mr)
        top_body = min((b.bbox.y0 for b in body_blocks), default=page.height_px * 0.1) / px_per_mm
        hdr_bottom = max((b.bbox.y1 for b in header_blocks), default=0) / px_per_mm
        sec.top_margin = Mm(min(60.0, max(15.0, top_body - 4))) if header_blocks else Mm(20)
        sec.header_distance = Mm(max(5.0, min(header_blocks and min(b.bbox.y0 for b in header_blocks) / px_per_mm or 10, 20)))
        sec.bottom_margin = Mm(20)
        sec.footer_distance = Mm(8)
        content_w = page.width_mm - ml - mr
        if rtl_page:
            sec._sectPr.append(OxmlElement("w:bidi"))
            _sort_children(sec._sectPr, ["w:headerReference", "w:footerReference", "w:footnotePr", "w:endnotePr", "w:type",
                                         "w:pgSz", "w:pgMar", "w:paperSrc", "w:pgBorders", "w:lnNumType", "w:pgNumType",
                                         "w:cols", "w:formProt", "w:vAlign", "w:noEndnote", "w:titlePg", "w:textDirection",
                                         "w:bidi", "w:rtlGutter", "w:docGrid", "w:printerSettings", "w:sectPrChange"])
        self._defaults(d, rtl_page)
        # header / footer
        if header_blocks:
            sec.header.is_linked_to_previous = False
            hp = sec.header.paragraphs[0]
            hp._p.getparent().remove(hp._p)
            self.band(sec.header, header_blocks, page, px_per_mm, assets_root, rtl_page, content_w)
            sec.header.add_paragraph()  # a table can't be last in a header part
        if footer_blocks:
            sec.footer.is_linked_to_previous = False
            fp = sec.footer.paragraphs[0]
            fp._p.getparent().remove(fp._p)
            self.band(sec.footer, footer_blocks, page, px_per_mm, assets_root, rtl_page, content_w)
        # body
        body = d
        first_para = d.paragraphs[0] if d.paragraphs else None
        prev_bottom = None
        for b in body_blocks:
            gap_pt = 0.0
            if prev_bottom is not None:
                gap_mm = (b.bbox.y0 - prev_bottom) / px_per_mm
                gap_pt = max(0.0, min(30.0, gap_mm * 2.83465 * 0.6))
            if b.type in ("stamp",) and self.cfg.stamp_floating:
                if self.cfg.insert_images:
                    self.floating_picture(body, b, px_per_mm, assets_root, rtl_page)
                continue
            align = self._visual_align(b, page)
            if b.type in ("logo", "figure", "signature", "stamp"):
                if self.cfg.insert_images:
                    self.picture_paragraph(body, b, content_w, px_per_mm, assets_root, align, rtl_page, gap_pt)
            elif b.type == "table" and b.html:
                tbl_rtl = (b.direction or ("rtl" if rtl_page else "ltr")) == "rtl"
                self.table(body, b, max(self.cfg.min_size_pt, self.size_for(b) - 1), tbl_rtl)
                after = body.add_paragraph(); set_paragraph_bidi(after, rtl_page); set_spacing(after, 0, 0, 1.0)
            elif b.text is not None:
                keep = b.type not in ("paragraph", "list") or self._keeps_breaks(b)
                if b.type == "list":
                    for item in [t for t in b.text.split("\n") if t.strip()]:
                        bb = b.model_copy(update={"text": item})
                        self.text_paragraph(body, bb, self.size_for(b), align, 0, keep_breaks=False)
                else:
                    self.text_paragraph(body, b, self.size_for(b), align, gap_pt, keep_breaks=keep)
            prev_bottom = b.bbox.y1
        if first_para is not None and not first_para.text and len(d.paragraphs) > 1:
            first_para._p.getparent().remove(first_para._p)
        self._doc = None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        d.save(str(out_path))
        return out_path

    @staticmethod
    def _keeps_breaks(b: Block) -> bool:
        return bool(b.style.align == "center" and b.text and b.text.count("\n") >= 1)

    @staticmethod
    def _visual_align(b: Block, page) -> str | None:
        if b.style.align:
            return b.style.align
        return None

    def _defaults(self, d, rtl: bool):
        st = d.styles["Normal"]
        rpr = st.element.get_or_add_rPr()
        _set_rfonts(rpr, self.cfg.font_latin, self.cfg.font_cs)
        _set_size(rpr, self.cfg.default_size_pt)
        _set_lang(rpr)
        _sort_children(rpr, _RPR_ORDER)
        if rtl:
            ppr = st.element.get_or_add_pPr()
            ppr.append(OxmlElement("w:bidi"))
            _sort_children(ppr, _PPR_ORDER)
        # docDefaults too, so tables/headers inherit Arabic font + size
        styles = d.styles.element
        dd = styles.find(qn("w:docDefaults"))
        if dd is not None:
            rpd = dd.find(qn("w:rPrDefault"))
            if rpd is not None:
                r = _get_or_add(rpd, "w:rPr")
                _set_rfonts(r, self.cfg.font_latin, self.cfg.font_cs)
                _set_lang(r)
                _sort_children(r, _RPR_ORDER)


def build_docx(doc: Document, out_path: str | Path, cfg: DocxCfg, assets_root: str | Path) -> Path:
    return DocxBuilder(cfg).build(doc, out_path, assets_root)
