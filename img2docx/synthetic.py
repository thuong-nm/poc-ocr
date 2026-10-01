"""Synthetic official-letter generator (Arabic / English / mixed) with ground truth.

Renders with Pillow + libraqm (HarfBuzz shaping, FriBiDi reordering), so Arabic is
shaped and ordered correctly. Ground-truth text is stored in *logical* order.
Then photo-like augmentations are applied (perspective, curvature, shadow, blur,
noise, JPEG).
"""
from __future__ import annotations

import io
import json
import math
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, features

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
DPI = 200
A4_PX = (int(210 / 25.4 * DPI), int(297 / 25.4 * DPI))  # (1653, 2338)

AR_FONTS = ["Amiri-Regular.ttf", "NotoNaskhArabic.ttf", "NotoSansArabic.ttf"]
AR_BOLD = {"Amiri-Regular.ttf": "Amiri-Bold.ttf"}
EN_FONTS = ["NotoSerif.ttf", "NotoSans.ttf"]
HW_AR = "ArefRuqaa-Regular.ttf"
HW_EN = "Caveat.ttf"

AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

# --------------------------------------------------------------------------- corpus
AR_PARAS = [
    "تهديكم وزارة الثقافة أطيب التحيات، وتود أن تحيطكم علماً بأنه تقرر عقد الاجتماع السنوي للجنة الوطنية للتراث في مقر الوزارة.",
    "نرجو التكرم بالاطلاع واتخاذ ما يلزم نحو تزويدنا بقائمة أسماء المشاركين قبل نهاية الشهر الجاري.",
    "وقد تمت الموافقة على خطة ترميم المباني التاريخية في المدينة القديمة وفقاً للميزانية المعتمدة لهذا العام.",
    "يرجى العلم بأن آخر موعد لتقديم الطلبات هو يوم الخميس، ولن يتم النظر في الطلبات الواردة بعد هذا التاريخ.",
    "تعمل الوزارة على دعم المكتبات العامة وتطوير برامج القراءة للأطفال والشباب في جميع المحافظات.",
    "كما نود الإشارة إلى ضرورة التنسيق مع إدارة المتاحف والآثار قبل البدء في أعمال الصيانة.",
    "وبناءً على توجيهات معالي الوزير، يتم تشكيل لجنة فنية لدراسة المقترحات المقدمة ورفع التوصيات خلال أسبوعين.",
    "ونأمل منكم تعميم هذا القرار على جميع الإدارات التابعة لكم والعمل بموجبه اعتباراً من تاريخه.",
]
AR_PARAS_NUM = [
    "بالإشارة إلى كتابكم رقم {n1} بتاريخ {d1} بشأن تنظيم معرض الكتاب الدولي، نفيدكم بالموافقة على المشاركة.",
    "تم تخصيص مبلغ {n2} ديناراً لصيانة المسرح الوطني، على أن تنتهي الأعمال خلال {n3} يوماً.",
]
MIXED_PARAS = [
    "سيتم عرض التقرير عبر نظام ECM الجديد، ويمكن التواصل عبر البريد info@culture.example.",
    "تم إرسال الملف بصيغة PDF إلى قسم IT لمراجعته قبل يوم {d2}.",
    "يعقد مؤتمر Digital Heritage في قاعة المؤتمرات الرئيسية بمشاركة منظمة UNESCO.",
]
EN_PARAS = [
    "With reference to your letter regarding the national heritage week, we are pleased to confirm the participation of the Ministry.",
    "Please submit the list of participants and the proposed exhibition plan no later than the end of the current month.",
    "The restoration plan for the historical buildings in the old city has been approved according to the annual budget.",
    "All departments are kindly requested to coordinate with the Museums and Antiquities Directorate before starting any maintenance work.",
    "The committee will review the submitted proposals and report its recommendations within two weeks.",
    "We would like to thank you for your continuous cooperation and support.",
]
AR_TITLES = ["تعميم إداري", "الموضوع: تنظيم معرض الكتاب", "قرار وزاري", "الموضوع: ترميم المباني التاريخية"]
EN_TITLES = ["Administrative Circular", "Subject: National Book Fair", "Subject: Restoration Programme"]
AR_CLOSING = "وتفضلوا بقبول فائق الاحترام والتقدير،"
EN_CLOSING = "Yours sincerely,"
BISMILLAH = "بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ"
HW_NOTES_AR = ["يعتمد", "للمتابعة مع الإدارة", "تمت المراجعة", "يحفظ"]
HW_NOTES_EN = ["Approved", "Please follow up", "Reviewed"]
HIJRI_MONTHS = ["محرم", "صفر", "رجب", "شعبان", "رمضان", "شوال"]


@dataclass
class GTBlock:
    id: str
    type: str
    lang: str | None
    bbox: list[float]
    text: str | None = None
    html: str | None = None
    align: str | None = None
    size_pt: float | None = None
    bold: bool = False


@dataclass
class GTPage:
    id: str
    direction: str  # rtl | ltr
    lang: str  # ar | en | mixed
    width_px: int
    height_px: int
    dpi: int
    blocks: list[GTBlock] = field(default_factory=list)  # in reading order
    augment: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- rendering helpers
class Renderer:
    def __init__(self, rng: random.Random):
        if not features.check("raqm"):
            raise RuntimeError("Pillow is built without libraqm; Arabic shaping would be wrong.")
        self.rng = rng
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def font(self, name: str, size_pt: float) -> ImageFont.FreeTypeFont:
        px = max(8, int(round(size_pt * DPI / 72)))
        key = (name, px)
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(str(FONT_DIR / name), px, layout_engine=ImageFont.Layout.RAQM)
        return self._cache[key]

    @staticmethod
    def _dir(text: str) -> str:
        return "rtl" if any("؀" <= c <= "ۿ" for c in text) else "ltr"

    def measure(self, text: str, font) -> float:
        d = self._dir(text)
        return font.getlength(text, direction=d, language="ar" if d == "rtl" else "en")

    def wrap(self, text: str, font, width: float) -> list[str]:
        words, lines, cur = text.split(), [], ""
        for w in words:
            cand = f"{cur} {w}".strip()
            if self.measure(cand, font) <= width or not cur:
                cur = cand
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def draw_line(self, draw: ImageDraw.ImageDraw, x: float, y: float, text: str, font, fill, anchor_x="l"):
        d = self._dir(text)
        lang = "ar" if d == "rtl" else "en"
        w = font.getlength(text, direction=d, language=lang)
        if anchor_x == "r":
            x = x - w
        elif anchor_x == "c":
            x = x - w / 2
        draw.text((x, y), text, font=font, fill=fill, direction=d, language=lang)
        bb = draw.textbbox((x, y), text, font=font, direction=d, language=lang)
        return bb

    def paragraph(self, draw, text, font, box_l, box_r, y, align, fill=(20, 20, 20), spacing=1.45):
        lines = self.wrap(text, font, box_r - box_l)
        lh = font.size * spacing
        bbs = []
        for ln in lines:
            if align == "right":
                bb = self.draw_line(draw, box_r, y, ln, font, fill, "r")
            elif align == "center":
                bb = self.draw_line(draw, (box_l + box_r) / 2, y, ln, font, fill, "c")
            else:
                bb = self.draw_line(draw, box_l, y, ln, font, fill, "l")
            bbs.append(bb)
            y += lh
        x0 = min(b[0] for b in bbs); y0 = min(b[1] for b in bbs)
        x1 = max(b[2] for b in bbs); y1 = max(b[3] for b in bbs)
        return [x0, y0, x1, y1], y, lines


def _fmt_num(n: int | str, arabic_digits: bool) -> str:
    s = str(n)
    return s.translate(AR_DIGITS) if arabic_digits else s


def _rand_dates(rng: random.Random, ar_digits: bool):
    gy, gm, gd = rng.randint(2023, 2026), rng.randint(1, 12), rng.randint(1, 28)
    hy, hm, hd = rng.randint(1444, 1448), rng.randint(1, 12), rng.randint(1, 29)
    greg = f"{gd:02d}/{gm:02d}/{gy}"
    hij = f"{hd:02d}/{hm:02d}/{hy}"
    return _fmt_num(hij, ar_digits), _fmt_num(greg, ar_digits)


# --------------------------------------------------------------------------- graphic elements
def draw_logo(size: int, rng: random.Random) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = rng.choice([(20, 90, 60, 255), (120, 80, 20, 255), (30, 50, 120, 255)])
    c = size / 2
    d.ellipse([4, 4, size - 4, size - 4], outline=col, width=max(3, size // 30))
    pts = []
    for i in range(16):
        r = (size * 0.38) if i % 2 == 0 else (size * 0.18)
        a = math.pi * 2 * i / 16 - math.pi / 2
        pts.append((c + r * math.cos(a), c + r * math.sin(a)))
    d.polygon(pts, fill=col)
    d.ellipse([c - size * 0.08, c - size * 0.08, c + size * 0.08, c + size * 0.08], fill=(255, 255, 255, 255))
    return img


def draw_stamp(r: Renderer, size: int, lang: str, rng: random.Random) -> tuple[Image.Image, str]:
    """Round rubber stamp: ring text + centre text, semi-transparent ink."""
    ink = rng.choice([(40, 50, 160), (110, 40, 140), (170, 30, 40)])
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    a = rng.randint(150, 200)
    d.ellipse([3, 3, size - 3, size - 3], outline=ink + (a,), width=6)
    d.ellipse([size * 0.2, size * 0.2, size * 0.8, size * 0.8], outline=ink + (a,), width=3)
    centre = "وزارة الثقافة" if lang != "en" else "MINISTRY"
    f = r.font("Amiri-Bold.ttf" if lang != "en" else "NotoSans.ttf", size / DPI * 72 * 0.11)
    r.draw_line(d, size / 2, size * 0.43, centre, f, ink + (a,), "c")
    ring = "الصادر" if lang != "en" else "OUTGOING"
    f2 = r.font("Amiri-Bold.ttf" if lang != "en" else "NotoSans.ttf", size / DPI * 72 * 0.09)
    r.draw_line(d, size / 2, size * 0.07, ring, f2, ink + (a,), "c")
    img = img.rotate(rng.uniform(-25, 25), resample=Image.BICUBIC)
    return img, centre


def draw_signature(w: int, h: int, rng: random.Random) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = (20, 30, 110, 230)
    x, y = w * 0.1, h * 0.6
    pts = [(x, y)]
    for _ in range(rng.randint(6, 10)):
        x += rng.uniform(w * 0.05, w * 0.14)
        y = h * rng.uniform(0.2, 0.85)
        pts.append((min(x, w * 0.95), y))
    # Catmull-Rom-ish smoothing
    sm = []
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        for t in np.linspace(0, 1, 12):
            sm.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t + math.sin(t * math.pi) * h * 0.12 * (-1) ** i))
    d.line(sm, fill=ink, width=4, joint="curve")
    d.line([(w * 0.15, h * 0.85), (w * 0.85, h * 0.78)], fill=ink, width=3)
    return img


def paste_rgba(page: Image.Image, im: Image.Image, x: int, y: int, multiply=True):
    """Ink-like compositing (multiply) so stamps overlap text realistically."""
    if not multiply:
        page.paste(im, (x, y), im)
        return
    region = page.crop((x, y, x + im.width, y + im.height)).convert("RGB")
    base = np.asarray(region).astype(np.float32) / 255
    rgba = np.asarray(im).astype(np.float32) / 255
    alpha = rgba[..., 3:4]
    ink = rgba[..., :3]
    out = base * (1 - alpha) + base * ink * alpha
    page.paste(Image.fromarray((out * 255).clip(0, 255).astype(np.uint8)), (x, y))


# --------------------------------------------------------------------------- table
def table_spec(lang: str, rng: random.Random, ar_digits: bool):
    """Returns header rows + body rows with spans. Cells: (text, rowspan, colspan)."""
    n = lambda v: _fmt_num(v, ar_digits)
    if lang == "en":
        head = [[("No.", 2, 1), ("Project", 2, 1), ("Location", 2, 1), ("Cost (USD)", 1, 2)],
                [("Approved", 1, 1), ("Spent", 1, 1)]]
        names = ["Old Theatre", "City Museum", "Public Library", "Heritage House"]
        locs = ["North District", "Old City"]
    else:
        head = [[("م", 2, 1), ("اسم المشروع", 2, 1), ("الموقع", 2, 1), ("التكلفة (بالدينار)", 1, 2)],
                [("المعتمدة", 1, 1), ("المصروفة", 1, 1)]]
        names = ["المسرح القديم", "متحف المدينة", "المكتبة العامة", "بيت التراث"]
        locs = ["المنطقة الشمالية", "المدينة القديمة"]
    rng.shuffle(names)
    rows = []
    for i in range(3):
        appr = rng.randint(10, 99) * 1000
        spent = rng.randint(1, 9) * 1000
        row = [(n(i + 1), 1, 1), (names[i], 1, 1)]
        if i == 0:
            row.append((locs[0], 2, 1))  # rowspan 2
        elif i == 2:
            row.append((locs[1], 1, 1))
        row += [(n(appr), 1, 1), (n(spent), 1, 1)]
        rows.append(row)
    return head + rows, 2


def spans_to_grid(rows):
    """Place (text, rs, cs) cells into a grid. Returns list of (r, c, rs, cs, text, is_header)."""
    occ = {}
    cells = []
    for r, row in enumerate(rows):
        c = 0
        for text, rs, cs in row:
            while (r, c) in occ:
                c += 1
            for dr in range(rs):
                for dc in range(cs):
                    occ[(r + dr, c + dc)] = True
            cells.append((r, c, rs, cs, text))
            c += cs
    ncols = max(c for (_, c) in occ) + 1
    nrows = max(r for (r, _) in occ) + 1
    return cells, nrows, ncols


def cells_to_html(rows, n_header: int) -> str:
    out = ["<table>"]
    for i, row in enumerate(rows):
        tag = "th" if i < n_header else "td"
        out.append("<tr>")
        for text, rs, cs in row:
            attrs = (f' rowspan="{rs}"' if rs > 1 else "") + (f' colspan="{cs}"' if cs > 1 else "")
            out.append(f"<{tag}{attrs}>{text}</{tag}>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def render_table(r: Renderer, draw, rows, n_header, x_l, x_r, y, rtl: bool, font, font_b):
    cells, nrows, ncols = spans_to_grid(rows)
    weights = [0.6, 2.2, 1.8, 1.3, 1.3][:ncols]
    tot = sum(weights)
    widths = [(x_r - x_l) * w / tot for w in weights]
    row_h = font.size * 2.0
    # column x edges in visual order
    edges = [x_l]
    for w in (widths[::-1] if rtl else widths):
        edges.append(edges[-1] + w)
    def col_x(c):  # logical col -> visual [x0,x1]
        vc = ncols - 1 - c if rtl else c
        return edges[vc], edges[vc + 1]
    for (rr, c, rs, cs, text) in cells:
        xs = [col_x(cc) for cc in range(c, c + cs)]
        x0, x1 = min(a for a, _ in xs), max(b for _, b in xs)
        y0, y1 = y + rr * row_h, y + (rr + rs) * row_h
        if rr < n_header:
            draw.rectangle([x0, y0, x1, y1], fill=(225, 225, 225))
        draw.rectangle([x0, y0, x1, y1], outline=(30, 30, 30), width=2)
        f = font_b if rr < n_header else font
        bb = f.getbbox(text, direction=r._dir(text), language="ar" if r._dir(text) == "rtl" else "en")
        r.draw_line(draw, (x0 + x1) / 2, (y0 + y1) / 2 - (bb[1] + bb[3]) / 2, text, f, (15, 15, 15), "c")
    return [x_l, y, x_r, y + nrows * row_h], y + nrows * row_h


# --------------------------------------------------------------------------- page composer
def make_page(seed: int, lang: str, with_table=True, with_stamp=True, with_handwriting=True) -> tuple[Image.Image, GTPage]:
    """Compose a page; drops paragraphs until everything fits above the footer."""
    for n_paras in (3, 2, 1):
        page, gt, bottom = _make_page(seed, lang, n_paras, with_table, with_stamp, with_handwriting)
        if bottom < A4_PX[1] * 0.93:
            return page, gt
    return page, gt


def _make_page(seed, lang, n_paras, with_table, with_stamp, with_handwriting):
    rng = random.Random(seed)
    r = Renderer(rng)
    W, H = A4_PX
    page = Image.new("RGB", (W, H), (rng.randint(246, 255), rng.randint(244, 253), rng.randint(238, 250)))
    draw = ImageDraw.Draw(page)
    rtl = lang in ("ar", "mixed")
    ar_digits = rtl and rng.random() < 0.5
    gt = GTPage(id=f"synth_{lang}_{seed:04d}", direction="rtl" if rtl else "ltr", lang=lang,
                width_px=W, height_px=H, dpi=DPI)
    mL, mR = int(W * 0.09), int(W * 0.91)
    ar_font = rng.choice(AR_FONTS)
    en_font = rng.choice(EN_FONTS)
    body_font_name = ar_font if rtl else en_font
    body_pt = rng.choice([12, 13, 14]) if rtl else rng.choice([11, 12])
    fbody = r.font(body_font_name, body_pt)
    fbold = r.font(AR_BOLD.get(body_font_name, body_font_name), body_pt + 2)
    bid = iter(range(1, 999))
    nid = lambda: f"b{next(bid)}"

    # ---- letterhead: Arabic right, logo centre, English left (bilingual letterhead is standard)
    y = int(H * 0.04)
    fh_ar = r.font(AR_BOLD.get(ar_font, ar_font), 14)
    fh_en = r.font(en_font, 11)
    ar_head = ["وزارة الثقافة", "مديرية التراث الوطني"]
    en_head = ["Ministry of Culture", "National Heritage Directorate"]
    yy = y
    ar_bbs = []
    for ln in ar_head:
        ar_bbs.append(r.draw_line(draw, mR, yy, ln, fh_ar, (10, 10, 10), "r"))
        yy += fh_ar.size * 1.5
    yy = y + 6
    en_bbs = []
    for ln in en_head:
        en_bbs.append(r.draw_line(draw, mL, yy, ln, fh_en, (10, 10, 10), "l"))
        yy += fh_en.size * 1.6
    logo = draw_logo(int(W * 0.12), rng)
    lx, ly = W // 2 - logo.width // 2, y - 10
    paste_rgba(page, logo, lx, ly, multiply=False)
    union = lambda bbs: [min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs)]
    hdr_ar = GTBlock(nid(), "header", "ar", union(ar_bbs), text="\n".join(ar_head), align="right", bold=True, size_pt=14)
    hdr_en = GTBlock(nid(), "header", "en", union(en_bbs), text="\n".join(en_head), align="left", size_pt=11)
    logo_b = GTBlock(nid(), "logo", None, [lx, ly, lx + logo.width, ly + logo.height])
    gt.blocks += ([hdr_ar, logo_b, hdr_en] if rtl else [hdr_en, logo_b, hdr_ar])
    y = ly + logo.height + 20
    draw.line([(mL, y), (mR, y)], fill=(60, 60, 60), width=3)
    y += 30

    # ---- number / date lines (top, on the reading-start side)
    hij, greg = _rand_dates(rng, ar_digits)
    num = _fmt_num(f"{rng.randint(1, 9)}/{rng.randint(100, 9999)}", ar_digits)
    fsm = r.font(body_font_name, body_pt)
    if rtl:
        lines = [("doc_number", f"الرقم: {num}"), ("date", f"التاريخ: {hij} هـ"), ("date", f"الموافق: {greg} م")]
        x, anchor = mR, "r"
    else:
        lines = [("doc_number", f"Ref. No.: {num}"), ("date", f"Date: {greg}")]
        x, anchor = mL, "l"
    note_y = y
    for typ, txt in lines:
        bb = r.draw_line(draw, x, y, txt, fsm, (10, 10, 10), anchor)
        gt.blocks.append(GTBlock(nid(), typ, "ar" if rtl else "en", list(bb), text=txt,
                                 align="right" if rtl else "left", size_pt=body_pt))
        y += fsm.size * 1.6
    y += 25

    # ---- bismillah (Arabic letters) with tashkeel
    if rtl and rng.random() < 0.7:
        fb = r.font(AR_BOLD.get(ar_font, ar_font), body_pt + 2)
        bb = r.draw_line(draw, W / 2, y, BISMILLAH, fb, (10, 10, 10), "c")
        gt.blocks.append(GTBlock(nid(), "title", "ar", list(bb), text=BISMILLAH, align="center", bold=True, size_pt=body_pt + 2))
        y += fb.size * 2.0

    # ---- title
    title = rng.choice(AR_TITLES if rtl else EN_TITLES)
    bb = r.draw_line(draw, W / 2, y, title, fbold, (0, 0, 0), "c")
    gt.blocks.append(GTBlock(nid(), "title", "ar" if rtl else "en", list(bb), text=title, align="center", bold=True, size_pt=body_pt + 2))
    y += fbold.size * 2.2

    # ---- paragraphs
    fmt = {"n1": _fmt_num(rng.randint(100, 999), ar_digits), "d1": hij + " هـ",
           "n2": _fmt_num(rng.randint(5, 90) * 1000, ar_digits), "n3": _fmt_num(rng.randint(30, 120), ar_digits),
           "d2": _fmt_num(f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{rng.randint(2024, 2026)}", False)}
    if lang == "ar":
        pool = rng.sample(AR_PARAS, 2) + [rng.choice(AR_PARAS_NUM)]
    elif lang == "mixed":
        pool = [rng.choice(AR_PARAS)] + rng.sample(MIXED_PARAS, 2)
    else:
        pool = rng.sample(EN_PARAS, 3)
    rng.shuffle(pool)
    pool = pool[:n_paras]
    n_before_table = min(len(pool), rng.randint(1, 2)) if with_table else len(pool)
    align = "justify" if rng.random() < 0.3 else ("right" if rtl else "left")
    draw_align = "right" if rtl else "left"
    for i, p in enumerate(pool):
        p = p.format(**fmt)
        plang = "ar" if lang == "ar" else ("en" if lang == "en" else ("mixed" if any(c.isascii() and c.isalpha() for c in p) else "ar"))
        bb, y, _ = r.paragraph(draw, p, fbody, mL, mR, y, draw_align)
        gt.blocks.append(GTBlock(nid(), "paragraph", plang, bb, text=p, align=align if align != "justify" else draw_align, size_pt=body_pt))
        y += fbody.size * 0.6
        if with_table and i == n_before_table - 1:
            rows, nh = table_spec("en" if lang == "en" else "ar", rng, ar_digits)
            ft = r.font(body_font_name, body_pt - 1)
            ftb = r.font(AR_BOLD.get(body_font_name, body_font_name), body_pt - 1)
            tb, y = render_table(r, draw, rows, nh, mL + 20, mR - 20, y + 10, rtl, ft, ftb)
            gt.blocks.append(GTBlock(nid(), "table", "en" if lang == "en" else "ar", tb, html=cells_to_html(rows, nh)))
            y += 40

    # ---- closing + signature area (on the far side: left for RTL, right for LTR)
    closing = AR_CLOSING if rtl else EN_CLOSING
    bb = r.draw_line(draw, mR if rtl else mL, y, closing, fbody, (10, 10, 10), "r" if rtl else "l")
    gt.blocks.append(GTBlock(nid(), "paragraph", "ar" if rtl else "en", list(bb), text=closing, align="right" if rtl else "left", size_pt=body_pt))
    y += fbody.size * 2.0
    sig_lines = (["مدير عام التراث الوطني", "د. سامي عبد الرحمن"] if rtl else ["Director General", "Dr. Sami Abdulrahman"])
    sx = mL + int(W * 0.17) if rtl else mR - int(W * 0.17)
    sbbs = []
    for ln in sig_lines:
        sbbs.append(r.draw_line(draw, sx, y, ln, fbody, (10, 10, 10), "c"))
        y += fbody.size * 1.5
    gt.blocks.append(GTBlock(nid(), "paragraph", "ar" if rtl else "en", union(sbbs), text="\n".join(sig_lines), align="center", size_pt=body_pt))
    sig = draw_signature(int(W * 0.22), int(H * 0.05), rng)
    sgx, sgy = int(sx - sig.width / 2), int(y)
    paste_rgba(page, sig, sgx, sgy)
    gt.blocks.append(GTBlock(nid(), "signature", None, [sgx, sgy, sgx + sig.width, sgy + sig.height]))
    y += sig.height
    if with_stamp:
        st, st_text = draw_stamp(r, int(W * 0.19), lang, rng)
        stx = int(sx + (rng.uniform(0.0, 0.25) * W) * (1 if rtl else -1) - st.width / 2)
        sty = int(sgy - st.height * rng.uniform(0.5, 0.8))
        paste_rgba(page, st, stx, sty)
        gt.blocks.append(GTBlock(nid(), "stamp", lang if lang != "mixed" else "ar", [stx, sty, stx + st.width, sty + st.height], text=st_text))

    content_bottom = y
    # ---- handwritten margin note (top far-side margin, slightly rotated, blue)
    if with_handwriting:
        note = rng.choice(HW_NOTES_AR if rtl else HW_NOTES_EN)
        fhw = r.font(HW_AR if rtl else HW_EN, 20 if rtl else 24)
        tmp = Image.new("RGBA", (int(W * 0.35), int(fhw.size * 2.2)), (0, 0, 0, 0))
        r.draw_line(ImageDraw.Draw(tmp), 10, fhw.size * 0.3, note, fhw, (25, 40, 150, 235), "l")
        tmp = tmp.crop(tmp.getbbox()).rotate(rng.uniform(-8, 8), expand=True, resample=Image.BICUBIC)
        hx = mL if rtl else mR - tmp.width
        hy = int(note_y)
        paste_rgba(page, tmp, hx, hy)
        # reading order: margin note comes right after the number/date lines
        pos = max(i for i, b in enumerate(gt.blocks) if b.type in ("doc_number", "date")) + 1
        gt.blocks.insert(pos, GTBlock(nid(), "handwritten_note", "ar" if rtl else "en", [hx, hy, hx + tmp.width, hy + tmp.height], text=note))

    # ---- footer
    ffoot = r.font(body_font_name, 9)
    fy = int(H * 0.955)
    draw.line([(mL, fy - 15), (mR, fy - 15)], fill=(90, 90, 90), width=2)
    foot = ("هاتف: " + _fmt_num("06 4600000", ar_digits) + " - ص.ب " + _fmt_num("1234", ar_digits)) if rtl else "Tel: 06 4600000 - P.O. Box 1234"
    bb = r.draw_line(draw, W / 2, fy, foot, ffoot, (50, 50, 50), "c")
    gt.blocks.append(GTBlock(nid(), "footer", "ar" if rtl else "en", list(bb), text=foot, align="center", size_pt=9))
    return page, gt, content_bottom


# --------------------------------------------------------------------------- augmentation
def augment(page: Image.Image, level: str, seed: int) -> tuple[np.ndarray, dict]:
    """Photo-like augmentation. level: clean | mild | hard."""
    rng = np.random.default_rng(seed)
    img = cv2.cvtColor(np.asarray(page), cv2.COLOR_RGB2BGR)
    info: dict = {"level": level}
    if level == "clean":
        return img, info
    hard = level == "hard"
    h, w = img.shape[:2]
    # curvature (page bending): vertical displacement varying with x
    amp = rng.uniform(4, 18 if hard else 8)
    info["curve_amp_px"] = float(amp)
    xs = np.arange(w, dtype=np.float32)
    ys = np.arange(h, dtype=np.float32)
    mx, my = np.meshgrid(xs, ys)
    dy = amp * np.sin(np.pi * mx / w) * (0.5 + my / h)
    img = cv2.remap(img, mx, (my + dy).astype(np.float32), cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    # place on background with margin + perspective
    bg_h, bg_w = int(h * 1.25), int(w * 1.3)
    base = rng.uniform(40, 120, size=3)
    bg = (base + rng.normal(0, 12, size=(bg_h, bg_w, 3))).clip(0, 255).astype(np.uint8)
    bg = cv2.GaussianBlur(bg, (0, 0), 3)
    j = (0.06 if hard else 0.03)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    ox, oy = (bg_w - w) / 2, (bg_h - h) / 2
    dst = np.float32([[ox + rng.uniform(-j, j) * w, oy + rng.uniform(-j, j) * h],
                      [ox + w + rng.uniform(-j, j) * w, oy + rng.uniform(-j, j) * h],
                      [ox + w + rng.uniform(-j, j) * w, oy + h + rng.uniform(-j, j) * h],
                      [ox + rng.uniform(-j, j) * w, oy + h + rng.uniform(-j, j) * h]])
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, M, (bg_w, bg_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), M, (bg_w, bg_h))
    img = np.where(mask[..., None] > 0, warped, bg)
    info["corners"] = dst.tolist()
    # shadow: smooth multiplicative gradient + soft blob
    gx = np.linspace(0, 1, bg_w)[None, :]
    gy = np.linspace(0, 1, bg_h)[:, None]
    a, b = rng.uniform(-1, 1, 2)
    grad = 1 - (0.35 if hard else 0.18) * np.clip(a * gx + b * gy + rng.uniform(-0.5, 0.5), 0, 1)
    blob = np.zeros((bg_h, bg_w), np.float32)
    cx, cy = int(rng.uniform(0.2, 0.8) * bg_w), int(rng.uniform(0.2, 0.8) * bg_h)
    cv2.ellipse(blob, (cx, cy), (int(bg_w * rng.uniform(0.15, 0.35)), int(bg_h * rng.uniform(0.1, 0.25))), rng.uniform(0, 180), 0, 360, 1.0, -1)
    blob = cv2.GaussianBlur(blob, (0, 0), bg_w * 0.06)
    shade = grad * (1 - (0.35 if hard else 0.2) * blob)
    img = (img.astype(np.float32) * shade[..., None]).clip(0, 255)
    # warm/cool colour cast
    img *= rng.uniform(0.92, 1.05, size=3)[None, None, :]
    # blur
    sigma = rng.uniform(0.6, 1.6 if hard else 1.0)
    img = cv2.GaussianBlur(img.clip(0, 255).astype(np.uint8), (0, 0), sigma)
    info["blur_sigma"] = float(sigma)
    # sensor noise
    noise = rng.normal(0, 5 if hard else 3, img.shape)
    img = (img.astype(np.float32) + noise).clip(0, 255).astype(np.uint8)
    # downscale like a phone photo + JPEG
    scale = rng.uniform(0.7, 0.95)
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    q = int(rng.integers(45, 70) if hard else rng.integers(70, 90))
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    img = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    info.update(jpeg_q=q, scale=float(scale))
    return img, info


def generate_dataset(out_dir: Path, n_per_lang: int = 3, levels=("clean", "mild", "hard"), seed0: int = 0) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    k = seed0
    for lang in ("ar", "en", "mixed"):
        for i in range(n_per_lang):
            k += 1
            page, gt = make_page(k, lang)
            for lvl in levels:
                img, info = augment(page, lvl, k * 10 + len(lvl))
                stem = f"{gt.id}_{lvl}"
                p = out_dir / f"{stem}.jpg"
                cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                g = asdict(gt)
                g["augment"] = info
                g["image"] = p.name
                (out_dir / f"{stem}.gt.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
                written.append(p)
    return written
