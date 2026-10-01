from img2docx.postprocess import (detect_lang, find_dates, find_doc_numbers, line_kind, refine_type,
                                  split_bidi_runs, text_direction)
from img2docx.schema import BBox, Block
from img2docx.confidence import agreement


def runs(t, base="rtl"):
    return [(s, d) for s, d in split_bidi_runs(t, base)]


def test_bidi_pure_arabic_single_run():
    assert runs("وزارة الثقافة") == [("وزارة الثقافة", "rtl")]


def test_bidi_mixed_english_inside_arabic():
    r = runs("يعقد مؤتمر Digital Heritage في القاعة")
    assert r == [("يعقد مؤتمر ", "rtl"), ("Digital Heritage", "ltr"), (" في القاعة", "rtl")]


def test_bidi_latin_digits_follow_previous_strong():
    # digits after Arabic stay in the RTL run (rendered LTR by Word anyway); after English they are LTR
    assert runs("الرقم 812 بتاريخ") == [("الرقم 812 بتاريخ", "rtl")]
    assert runs("نظام ECM 2025 الجديد") == [("نظام ", "rtl"), ("ECM 2025", "ltr"), (" الجديد", "rtl")]


def test_bidi_arabic_indic_digits_are_rtl():
    assert runs("Ref ١٢٣", "ltr") == [("Ref ", "ltr"), ("١٢٣", "rtl")]


def test_bidi_diacritics_stay_with_letters():
    t = "بِسْمِ اللَّهِ"
    assert runs(t) == [(t, "rtl")]


def test_bidi_ltr_paragraph_with_arabic_word():
    assert runs("Ministry وزارة office", "ltr") == [("Ministry ", "ltr"), ("وزارة", "rtl"), (" office", "ltr")]


def test_bidi_roundtrip_is_lossless():
    t = "تم إرسال الملف PDF إلى قسم IT قبل 15/10/2025، شكراً."
    assert "".join(s for s, _ in split_bidi_runs(t)) == t


def test_lang_and_direction():
    assert detect_lang("وزارة الثقافة") == "ar"
    assert detect_lang("Ministry of Culture") == "en"
    assert detect_lang("نظام ECM الجديد") == "mixed"
    assert text_direction("Ministry") == "ltr" and text_direction("وزارة") == "rtl"


def test_dates_hijri_gregorian_both_digit_forms():
    d = find_dates("التاريخ: ١٢/٠٣/١٤٤٦ هـ الموافق 15/09/2024 م", "b1")
    assert [(x.calendar, x.normalized) for x in d] == [("hijri", "1446-03-12"), ("gregorian", "2024-09-15")]
    assert d[0].raw == "١٢/٠٣/١٤٤٦ هـ"  # raw keeps the original digits


def test_dates_textual_months():
    d = find_dates("حرر في 5 رمضان 1445 هـ", "b")
    assert d[0].calendar == "hijri" and d[0].normalized == "1445-09-05"
    d = find_dates("Date: 3 March 2025", "b")
    assert d[0].calendar == "gregorian" and d[0].normalized == "2025-03-03"


def test_doc_numbers():
    n = find_doc_numbers("الرقم: ٤/٣٢٤١", "b", True)
    assert n[0]["value"] == "٤/٣٢٤١" and n[0]["value_latin"] == "4/3241" and n[0]["role"] == "self"
    n = find_doc_numbers("Ref. No.: 7/6547", "b", True)
    assert n[0]["value"] == "7/6547"


def test_refine_type_and_line_kind():
    b = Block(id="x", type="paragraph", bbox=BBox.of([0, 0, 1, 1]), text="الرقم: 1/6486")
    assert refine_type(b) == "doc_number"
    b.text = "التاريخ: 16/02/1445 هـ"
    assert refine_type(b) == "date"
    b.text = "بالإشارة إلى كتابكم رقم 812 بتاريخ 16/02/1445 هـ بشأن تنظيم معرض الكتاب الدولي، نفيدكم بالموافقة"
    assert refine_type(b) == "paragraph"
    assert line_kind("Date: 02/10/2024") == "date"


def test_agreement_normalization():
    assert agreement("بِسْمِ اللَّهِ", "بسم الله") == 1.0  # tashkeel/whitespace ignored for agreement only
    assert agreement("الرقم 14", "الرقم", ignore_digits=True) == 1.0
    assert agreement("abc", "xyz") == 0.0
