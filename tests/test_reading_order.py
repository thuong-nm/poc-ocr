from img2docx.reading_order import alignment_direction_hint, reading_order

W = 1000


def test_rtl_single_column_top_to_bottom():
    boxes = [(100, 300, 900, 360), (100, 100, 900, 160), (100, 200, 900, 260)]
    assert reading_order(boxes, ["paragraph"] * 3, "rtl") == [1, 2, 0]


def test_rtl_same_row_right_first():
    # number/date block on the right, margin note on the left, same band
    boxes = [(100, 100, 300, 150), (650, 100, 900, 200), (100, 300, 900, 400)]
    assert reading_order(boxes, ["handwritten_note", "doc_number", "paragraph"], "rtl") == [1, 0, 2]
    assert reading_order(boxes, ["handwritten_note", "doc_number", "paragraph"], "ltr") == [0, 1, 2]


def test_two_columns_rtl_vs_ltr():
    #  title spanning both columns, then two tall columns with staggered paragraphs
    title = (100, 50, 900, 100)
    left = [(100, 150, 480, 400), (100, 420, 480, 700)]
    right = [(520, 150, 900, 300), (520, 330, 900, 700)]
    boxes = [title] + left + right
    types = ["title"] + ["paragraph"] * 4
    assert reading_order(boxes, types, "rtl") == [0, 3, 4, 1, 2]
    assert reading_order(boxes, types, "ltr") == [0, 1, 2, 3, 4]


def test_header_first_footer_last_stamp_floating():
    boxes = [(100, 900, 900, 950),   # footer
             (100, 200, 900, 300),   # paragraph
             (600, 20, 900, 80),     # header right (Arabic)
             (100, 20, 400, 80),     # header left (English)
             (300, 250, 600, 500),   # stamp overlapping paragraph + signature area
             (100, 400, 400, 450)]   # signature
    types = ["footer", "paragraph", "header", "header", "stamp", "signature"]
    order = reading_order(boxes, types, "rtl")
    assert order[:2] == [2, 3]
    assert order[-1] == 0
    assert order.index(4) > order.index(1)  # stamp placed after the paragraph it overlaps


def test_direction_hint_from_alignment():
    rtl_lines = [(100 + i * 37 % 200, y, 900, y + 30) for i, y in enumerate(range(100, 600, 50))]
    ltr_lines = [(100, y, 900 - i * 37 % 200, y + 30) for i, y in enumerate(range(100, 600, 50))]
    assert alignment_direction_hint(rtl_lines, W) == "rtl"
    assert alignment_direction_hint(ltr_lines, W) == "ltr"
