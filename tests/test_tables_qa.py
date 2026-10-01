import random

import cv2
import numpy as np
from PIL import Image, ImageDraw

from img2docx import qa
from img2docx.config import QACfg
from img2docx.evaluation import teds
from img2docx.synthetic import Renderer, cells_to_html, render_table, table_spec
from img2docx.tables import cells_to_html as grid_html, detect_grid, parse_html_table


def _table_image(rtl: bool):
    rng = random.Random(3)
    r = Renderer(rng)
    img = Image.new("RGB", (1600, 500), (250, 250, 250))
    d = ImageDraw.Draw(img)
    rows, nh = table_spec("ar" if rtl else "en", rng, False)
    f = r.font("Amiri-Regular.ttf" if rtl else "NotoSans.ttf", 12)
    bb, _ = render_table(r, d, rows, nh, 40, 1560, 40, rtl, f, f)
    x0, y0, x1, y1 = (int(v) for v in bb)
    crop = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)[y0 - 8:y1 + 8, x0 - 8:x1 + 8]
    return crop, cells_to_html(rows, nh)


def test_grid_structure_rtl_and_ltr():
    for rtl in (True, False):
        crop, gt = _table_image(rtl)
        cells = detect_grid(crop, rtl=rtl)
        assert cells is not None
        assert teds(gt, grid_html(cells), structure_only=True) == 1.0


def test_parse_html_spans():
    cells, nr, nc = parse_html_table('<table><tr><td rowspan="2">a</td><td colspan="2">b</td></tr><tr><td>c</td><td>d</td></tr></table>')
    assert (nr, nc) == (2, 3)
    pos = {(c.row, c.col): c.text for c in cells}
    assert pos == {(0, 0): "a", (0, 1): "b", (1, 1): "c", (1, 2): "d"}


def test_blur_metric_orders_sharp_vs_blurred():
    img = np.full((1200, 900, 3), 240, np.uint8)
    for y in range(50, 1150, 30):
        cv2.putText(img, "Lorem ipsum dolor sit amet", (40, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    sharp = qa.blur_variance(img)
    blurred = qa.blur_variance(cv2.GaussianBlur(img, (0, 0), 3))
    assert sharp > 5 * blurred
    rep = qa.assess(cv2.GaussianBlur(img, (0, 0), 6), QACfg())
    assert any("blurry" in w for w in rep.warnings)


def test_glare_detection():
    img = np.full((800, 600, 3), 200, np.uint8)
    cv2.circle(img, (300, 300), 120, (255, 255, 255), -1)
    assert qa.glare_ratio(img) > 0.05
    assert qa.glare_ratio(np.full((800, 600, 3), 250, np.uint8)) == 0.0  # white paper is not glare


def test_load_exif_rotation_and_heic(tmp_path):
    from PIL import Image as PImage

    arr = np.zeros((100, 200, 3), np.uint8)
    arr[:, :50] = 255
    im = PImage.fromarray(arr)
    exif = im.getexif()
    exif[0x0112] = 6  # rotate 90 CW on display
    im.save(tmp_path / "r.jpg", exif=exif)
    li = qa.load_image(tmp_path / "r.jpg")
    assert li.bgr.shape[:2] == (200, 100)
    import pillow_heif  # noqa: F401  (registered by qa)

    im.save(tmp_path / "x.heic")
    li = qa.load_image(tmp_path / "x.heic")
    assert li.bgr.shape[:2] == (200, 100)  # HEIC keeps the EXIF orientation too


def test_missing_file_raises():
    import pytest

    with pytest.raises(qa.ImageLoadError):
        qa.load_image("/nonexistent.jpg")
