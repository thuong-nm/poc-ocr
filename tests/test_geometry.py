import cv2
import numpy as np

from img2docx import geometry as G
from img2docx.config import GeometryCfg


def _photo(angle_jitter=0.05, seed=0, page=None):
    rng = np.random.default_rng(seed)
    if page is None:
        page = np.full((1400, 990, 3), 245, np.uint8)
        for y in range(120, 1300, 45):  # fake text lines
            cv2.rectangle(page, (90, y), (900 - int(rng.integers(0, 300)), y + 18), (30, 30, 30), -1)
    h, w = page.shape[:2]
    bg = np.full((int(h * 1.3), int(w * 1.4), 3), 70, np.uint8)
    ox, oy = (bg.shape[1] - w) / 2, (bg.shape[0] - h) / 2
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    j = angle_jitter
    dst = np.float32([[ox + rng.uniform(-j, j) * w, oy + rng.uniform(-j, j) * h],
                      [ox + w + rng.uniform(-j, j) * w, oy + rng.uniform(-j, j) * h],
                      [ox + w + rng.uniform(-j, j) * w, oy + h + rng.uniform(-j, j) * h],
                      [ox + rng.uniform(-j, j) * w, oy + h + rng.uniform(-j, j) * h]])
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(page, M, (bg.shape[1], bg.shape[0]))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), M, (bg.shape[1], bg.shape[0]))
    return np.where(mask[..., None] > 0, warped, bg), dst


def test_order_points():
    pts = np.float32([[10, 100], [100, 100], [100, 0], [0, 0]])
    o = G.order_points(pts)
    assert o.tolist() == [[0, 0], [100, 0], [100, 100], [10, 100]]


def test_find_quad_accuracy():
    for seed in range(5):
        img, true = _photo(seed=seed)
        q, cov = G.find_document_quad(img)
        assert q is not None
        diag = np.hypot(*img.shape[:2])
        assert np.abs(q - G.order_points(true)).max() < 0.015 * diag
        assert 0.3 < cov < 0.8


def test_no_boundary_for_tight_scan():
    page = np.full((1400, 990, 3), 245, np.uint8)
    cv2.putText(page, "text", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
    q, cov = G.find_document_quad(page)
    assert q is None and cov == 1.0


def test_warp_snaps_a4():
    img, true = _photo(seed=3)
    q, _ = G.find_document_quad(img)
    out, paper, wmm, hmm, dpi = G.warp_quad(img, q, 2400)
    assert paper == "A4" and (wmm, hmm) == (210.0, 297.0)
    assert out.shape[0] == 2400 and abs(out.shape[1] / out.shape[0] - 210 / 297) < 0.01


def test_deskew_recovers_angle():
    page = np.full((1400, 990), 245, np.uint8)
    for y in range(100, 1300, 40):
        cv2.rectangle(page, (80, y), (900, y + 14), 20, -1)
    rot = G.rotate_bound(cv2.cvtColor(page, cv2.COLOR_GRAY2BGR), 3.0)
    est = G.estimate_skew(cv2.cvtColor(rot, cv2.COLOR_BGR2GRAY), 8)
    assert abs(est + 3.0) < 0.4  # the correction is the opposite rotation


def test_heuristic_orientation_90():
    page = np.full((1400, 990), 245, np.uint8)
    for y in range(100, 1300, 40):
        cv2.rectangle(page, (80, y), (900, y + 14), 20, -1)
    assert G.heuristic_orientation(page) == 0
    assert G.heuristic_orientation(cv2.rotate(page, cv2.ROTATE_90_CLOCKWISE)) == 90


def test_correct_full_stage(synth_page):
    from img2docx.synthetic import augment

    page, gt = synth_page
    img, info = augment(page, "mild", 5)
    r = G.correct(img, GeometryCfg(orientation="heuristic"), G.OrientationDetector("heuristic"))
    assert r.quad is not None and r.paper == "A4"
    assert r.page.shape[0] == 2400
    assert r.rotation == 0


def test_orientation_all_rotations_arabic_page(synth_page):
    """PP-LCNet alone mis-flips some upright Arabic pages; the voting + OCR check must not."""
    import pytest
    from img2docx.recognizers.tesseract import resolve_tesseract_cmd

    try:
        cmd = resolve_tesseract_cmd(None)
    except FileNotFoundError:
        pytest.skip("tesseract not installed")
    page, _ = synth_page
    bgr = cv2.cvtColor(np.asarray(page), cv2.COLOR_RGB2BGR)
    o = G.OrientationDetector("tesseract", tesseract_cmd=cmd)
    for k, rot in [(0, None), (90, cv2.ROTATE_90_CLOCKWISE), (180, cv2.ROTATE_180), (270, cv2.ROTATE_90_COUNTERCLOCKWISE)]:
        im = bgr if rot is None else cv2.rotate(bgr, rot)
        fix, how = o.detect(im)
        assert (k + fix) % 360 == 0, (k, fix, how)
