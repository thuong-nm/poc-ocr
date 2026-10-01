"""Render the produced DOCX through LibreOffice and check the *visual* RTL layout."""
import pytest

from img2docx.config import DocxCfg
from img2docx.docx_builder import build_docx
from img2docx.render import docx_to_pdf, pdf_to_pngs

from test_docx_builder import _doc

pytestmark = pytest.mark.libreoffice


def _spans(pdf):
    import pymupdf

    out = []
    with pymupdf.open(str(pdf)) as d:
        page = d[0]
        W = page.rect.width
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    if s["text"].strip():
                        out.append((s["text"], s["bbox"], W))
    return out


def test_rtl_layout_renders_right_aligned(tmp_path, soffice):
    doc = _doc(tmp_path)
    docx = build_docx(doc, tmp_path / "r.docx", DocxCfg(), tmp_path)
    pdf = docx_to_pdf(docx, tmp_path, soffice)
    pngs = pdf_to_pngs(pdf)
    assert pngs and pngs[0].stat().st_size > 1000
    spans = _spans(pdf)
    W = spans[0][2]

    def find(sub):
        hits = [s for s in spans if sub in s[0]]
        assert hits, f"{sub!r} not rendered; got {[s[0] for s in spans]}"
        return hits[0][1]

    # Arabic body paragraph: flush right (right edge near the right margin)
    num = find("الرقم")
    assert num[2] > W * 0.8, num
    # English paragraph: flush left
    en = find("approved")
    assert en[0] < W * 0.2, en
    # Letterhead: Arabic on the right, English on the left
    ar_head = find("وزارة")
    en_head = find("Ministry")
    assert ar_head[0] > W * 0.6 and en_head[2] < W * 0.4
    # RTL table: the serial-number column header 'م' is the rightmost header cell
    mim = [s for s in spans if s[0].strip() == "م"]
    cost = find("التكلفة")
    assert mim and mim[0][1][0] > cost[0]
