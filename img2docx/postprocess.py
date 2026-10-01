"""Post-processing: script/direction detection, bidi run splitting, dates & document numbers.

Nothing here changes recognized text (no spell correction, no digit conversion). Normalized
values (Latin digits, ISO dates) are written to metadata only.
"""
from __future__ import annotations

import re
import unicodedata

from .schema import Block, DateRef, Metadata

ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_TO_LATIN = str.maketrans(ARABIC_DIGITS + PERSIAN_DIGITS, "0123456789" * 2)
TASHKEEL = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭ]")
TATWEEL = "ـ"
D = r"[0-9٠-٩۰-۹]"


def to_latin_digits(s: str) -> str:
    return s.translate(_TO_LATIN)


def is_arabic_letter(c: str) -> bool:
    return unicodedata.bidirectional(c) in ("AL", "R") and c.isalpha()


def script_counts(text: str) -> tuple[int, int]:
    ar = sum(1 for c in text if is_arabic_letter(c))
    la = sum(1 for c in text if c.isascii() and c.isalpha())
    return ar, la


def detect_lang(text: str | None) -> str | None:
    if not text:
        return None
    ar, la = script_counts(text)
    tot = ar + la
    if tot == 0:
        return None
    if la <= 0.05 * tot:
        return "ar"
    if ar <= 0.05 * tot:
        return "en"
    return "mixed"


def text_direction(text: str | None, default: str = "rtl") -> str:
    if not text:
        return default
    ar, la = script_counts(text)
    if ar == la == 0:
        return default
    return "rtl" if ar >= la else "ltr"


def page_direction(blocks: list[Block], hint: str | None = None) -> str:
    """Direction from content: Arabic vs Latin letters in body text (header/footer weigh less)."""
    ar = la = 0.0
    for b in blocks:
        t = b.text or ""
        if b.html:
            from .tables import html_text

            t = html_text(b.html)
        a, l = script_counts(t)
        w = 0.3 if b.type in ("header", "footer") else 1.0
        ar += a * w
        la += l * w
    if ar == la == 0:
        return hint or "rtl"
    return "rtl" if ar >= la else "ltr"


# --------------------------------------------------------------------------- bidi runs
def _bidi_class(c: str) -> str:
    b = unicodedata.bidirectional(c)
    if b in ("R", "AL"):
        return "R"
    if b == "AN":
        return "AN"
    if b == "EN":
        return "EN"
    if b == "L":
        return "L"
    if b == "NSM":
        return "NSM"
    return "N"


def split_bidi_runs(text: str, base: str = "rtl") -> list[tuple[str, str]]:
    """Split text into (segment, 'rtl'|'ltr') runs for OOXML w:rtl marking.

    Simplified UAX#9: strong R/AL/AN -> rtl, L -> ltr; EN follows the previous strong type (W7) or
    base; NSM (diacritics) follow the previous char; neutrals between equal directions take that
    direction (N1), otherwise the base direction (N2).
    """
    if not text:
        return []
    cls = [_bidi_class(c) for c in text]
    dirs: list[str | None] = [None] * len(text)
    last_strong = None
    for i, k in enumerate(cls):
        if k in ("R", "AN"):
            dirs[i] = "rtl"; last_strong = "rtl"
        elif k == "L":
            dirs[i] = "ltr"; last_strong = "ltr"
        elif k == "EN":
            dirs[i] = "ltr" if last_strong == "ltr" else base
            if last_strong is None:
                dirs[i] = base
    for i, k in enumerate(cls):  # NSM: take previous char direction
        if k == "NSM":
            dirs[i] = dirs[i - 1] if i and dirs[i - 1] else base
    # neutrals
    i = 0
    n = len(text)
    while i < n:
        if dirs[i] is not None:
            i += 1
            continue
        j = i
        while j < n and dirs[j] is None:
            j += 1
        prev_d = dirs[i - 1] if i > 0 else None
        next_d = dirs[j] if j < n else None
        if prev_d and prev_d == next_d:
            d = prev_d
        else:
            d = base
        for k in range(i, j):
            dirs[k] = d
        i = j
    runs: list[tuple[str, str]] = []
    for c, d in zip(text, dirs):
        if runs and runs[-1][1] == d:
            runs[-1] = (runs[-1][0] + c, d)
        else:
            runs.append((c, d))
    return runs


# --------------------------------------------------------------------------- dates
HIJRI_MONTHS = {
    "محرم": 1, "صفر": 2, "ربيع الأول": 3, "ربيع الاول": 3, "ربيع الآخر": 4, "ربيع الثاني": 4,
    "جمادى الأولى": 5, "جمادى الاولى": 5, "جمادى الآخرة": 6, "جمادى الثانية": 6, "رجب": 7, "شعبان": 8,
    "رمضان": 9, "شوال": 10, "ذو القعدة": 11, "ذي القعدة": 11, "ذو الحجة": 12, "ذي الحجة": 12,
}
GREG_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7,
    "أغسطس": 8, "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
    "كانون الثاني": 1, "شباط": 2, "آذار": 3, "نيسان": 4, "أيار": 5, "حزيران": 6, "تموز": 7, "آب": 8,
    "أيلول": 9, "تشرين الأول": 10, "تشرين الثاني": 11, "كانون الأول": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
_HIJRI_SUFFIX = r"(?:\s*(?:هـ|ه\b|ھ|AH\b|A\.H\.?|H\b))"
_GREG_SUFFIX = r"(?:\s*(?:م\b|AD\b|A\.D\.?|CE\b))"
NUM_DATE = re.compile(
    rf"(?P<a>{D}{{1,4}})\s*[/\-\.]\s*(?P<b>{D}{{1,2}})\s*[/\-\.]\s*(?P<c>{D}{{1,4}})(?P<suf>{_HIJRI_SUFFIX}|{_GREG_SUFFIX})?"
)
_MONTHS_RE = "|".join(sorted((re.escape(m) for m in list(HIJRI_MONTHS) + list(GREG_MONTHS)), key=len, reverse=True))
TEXT_DATE = re.compile(rf"(?P<d>{D}{{1,2}})\s+(?:من\s+)?(?P<m>{_MONTHS_RE})\s*,?\s+(?P<y>{D}{{4}})(?P<suf>{_HIJRI_SUFFIX}|{_GREG_SUFFIX})?", re.I)


def _calendar(year: int, suffix: str | None) -> str | None:
    if suffix:
        s = suffix.strip()
        if s.startswith(("ه", "ھ", "A.H", "AH", "H")):
            return "hijri"
        return "gregorian"
    if 1300 <= year <= 1500:
        return "hijri"
    if 1800 <= year <= 2200:
        return "gregorian"
    return None


def find_dates(text: str, block_id: str) -> list[DateRef]:
    out: list[DateRef] = []
    for m in NUM_DATE.finditer(text):
        a, b, c = (int(to_latin_digits(m.group(k))) for k in "abc")
        if len(m.group("a")) == 4:
            y, mo, d = a, b, c
        elif len(m.group("c")) == 4:
            y, mo, d = c, b, a
        else:
            continue
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        cal = _calendar(y, m.group("suf"))
        if cal is None:
            continue
        out.append(DateRef(calendar=cal, raw=m.group(0).strip(), normalized=f"{y:04d}-{mo:02d}-{d:02d}", block_id=block_id))
    for m in TEXT_DATE.finditer(text):
        mon = m.group("m")
        key = mon.lower() if mon.isascii() else mon
        y = int(to_latin_digits(m.group("y")))
        d = int(to_latin_digits(m.group("d")))
        if key in HIJRI_MONTHS:
            cal, mo = "hijri", HIJRI_MONTHS[key]
        else:
            cal, mo = (_calendar(y, m.group("suf")) or "gregorian"), GREG_MONTHS[key]
        out.append(DateRef(calendar=cal, raw=m.group(0).strip(), normalized=f"{y:04d}-{mo:02d}-{d:02d}", block_id=block_id))
    return out


# --------------------------------------------------------------------------- document numbers
DOCNO_KEY = r"(?:الرقم\s*الإشاري|الرقم|رقم\s*الكتاب|رقم\s*القيد|رقم|العدد|المرجع|الإشارة|Ref(?:erence)?\.?\s*(?:No\.?)?|Our\s+Ref\.?|No\.)"
DOCNO = re.compile(rf"(?P<key>{DOCNO_KEY})\s*[:：\-]?\s*(?P<val>{D}[{D[1:-1]}A-Za-zء-ي/\\\-\.]*{D}|{D})", re.I)
DATE_KEY = re.compile(r"^\s*(?:التاريخ|الموافق|تاريخ|بتاريخ|Date|Dated)\s*[:：]?", re.I)


def find_doc_numbers(text: str, block_id: str, is_number_block: bool) -> list[dict[str, str]]:
    out = []
    for m in DOCNO.finditer(text):
        out.append({"raw": m.group(0).strip(), "value": m.group("val"), "value_latin": to_latin_digits(m.group("val")),
                    "role": "self" if is_number_block else "reference", "block_id": block_id})
    return out


def refine_type(b: Block) -> str:
    """Re-classify short text blocks as doc_number / date from content (layout can't tell)."""
    if b.type not in ("paragraph", "title", "header") or not b.text:
        return b.type
    t = b.text.strip()
    if len(t) > 70 or "\n" in t.strip():
        return b.type
    if DOCNO.match(t.strip()) or re.match(rf"^\s*{DOCNO_KEY}\s*[:：]", t, re.I):
        return "doc_number"
    if DATE_KEY.match(t) and (NUM_DATE.search(t) or TEXT_DATE.search(t)):
        return "date"
    if (NUM_DATE.fullmatch(t.strip()) or TEXT_DATE.fullmatch(t.strip())):
        return "date"
    return b.type


def line_kind(line: str) -> str | None:
    t = line.strip()
    if not t or len(t) > 70:
        return None
    if re.match(rf"^\s*{DOCNO_KEY}\s*[:：]?", t, re.I) and re.search(D, t):
        return "doc_number"
    if DATE_KEY.match(t) and (NUM_DATE.search(t) or TEXT_DATE.search(t)):
        return "date"
    return None


def build_metadata(blocks: list[Block]) -> Metadata:
    md = Metadata()
    langs = set()
    for b in blocks:
        text = b.text or ""
        if b.html:
            from .tables import html_text

            text = html_text(b.html)
        if b.type == "stamp":
            if b.text:
                md.stamp_texts.append({"text": b.text, "block_id": b.id})
            continue
        if b.lang:
            langs.add(b.lang)
        md.dates += find_dates(text, b.id)
        md.doc_numbers += find_doc_numbers(text, b.id, b.type == "doc_number")
    md.languages = sorted(langs)
    return md


def normalize_for_compare(s: str, drop_digits: bool = False) -> str:
    """For agreement/eval only: drop tashkeel/tatweel/bidi controls/whitespace."""
    from .recognizers.base import strip_bidi_controls

    s = strip_bidi_controls(unicodedata.normalize("NFC", s or ""))
    s = TASHKEEL.sub("", s).replace(TATWEEL, "")
    if drop_digits:  # Latin digits only: PaddleOCR-arabic is unreliable on those, fine on ٠-٩
        s = re.sub(r"[0-9]", "", s)
    s = "".join(c for c in s if not unicodedata.category(c).startswith("P"))  # engines differ on : / ، .
    return re.sub(r"\s+", "", s)
