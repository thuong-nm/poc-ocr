"""Document boundary detection, perspective correction, optional dewarping, orientation and deskew."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from .config import GeometryCfg

log = logging.getLogger(__name__)

PAPER_MM = {"A4": (210.0, 297.0), "Letter": (215.9, 279.4)}


@dataclass
class GeometryResult:
    page: np.ndarray
    quad: np.ndarray | None          # 4x2 float32 in input-image px (tl, tr, br, bl)
    coverage: float | None
    rotation: int = 0                # clockwise degrees applied
    skew_deg: float = 0.0
    dewarped: bool = False
    paper: str | None = None
    width_mm: float = 210.0
    height_mm: float = 297.0
    est_dpi: float | None = None
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- boundary
def order_points(pts: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def _quad_from_contour(cnt: np.ndarray) -> np.ndarray | None:
    hull = cv2.convexHull(cnt)
    peri = cv2.arcLength(hull, True)
    for eps in (0.01, 0.02, 0.03, 0.04, 0.05, 0.07):
        ap = cv2.approxPolyDP(hull, eps * peri, True)
        if len(ap) == 4 and cv2.isContourConvex(ap):
            return ap.reshape(4, 2).astype(np.float32)
    # fallback: extreme points along diagonals (robust to rounded corners)
    p = hull.reshape(-1, 2).astype(np.float32)
    s, d = p.sum(1), p[:, 1] - p[:, 0]
    return np.array([p[np.argmin(s)], p[np.argmin(d)], p[np.argmax(s)], p[np.argmax(d)]], np.float32)


def _candidates(small: np.ndarray) -> list[np.ndarray]:
    """Binary masks that may isolate the sheet: brightness-minus-saturation Otsu, and edge closing."""
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    v = hsv[..., 2].astype(np.int16)
    s = hsv[..., 1].astype(np.int16)
    paper = np.clip(v - s, 0, 255).astype(np.uint8)
    paper = cv2.GaussianBlur(paper, (7, 7), 0)
    _, m1 = cv2.threshold(paper, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = np.ones((9, 9), np.uint8)
    m1 = cv2.morphologyEx(m1, cv2.MORPH_CLOSE, k, iterations=2)
    m1 = cv2.morphologyEx(m1, cv2.MORPH_OPEN, k)
    g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(g, (5, 5), 0), 40, 120)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)
    m2 = np.zeros_like(g)
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        cv2.drawContours(m2, [max(cnts, key=cv2.contourArea)], -1, 255, -1)
    return [m1, m2]


def find_document_quad(bgr: np.ndarray, min_area_ratio: float = 0.2) -> tuple[np.ndarray | None, float]:
    """Return (quad in input px, coverage) or (None, 1.0) when the photo is already a tight crop."""
    h, w = bgr.shape[:2]
    s = 900 / max(h, w)
    small = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    best, best_score = None, 0.0
    for mask in _candidates(small):
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:3]:
            area = cv2.contourArea(c)
            ratio = area / (sh * sw)
            if ratio < min_area_ratio or ratio > 0.985:
                continue
            q = _quad_from_contour(c)
            if q is None:
                continue
            qa = cv2.contourArea(q.reshape(-1, 1, 2))
            fill = area / max(qa, 1)  # how rectangular the blob is
            # reject quads that hug the image border on all sides (= no real boundary)
            margin = min(q[:, 0].min(), q[:, 1].min(), sw - q[:, 0].max(), sh - q[:, 1].max())
            score = ratio * min(fill, 1 / max(fill, 1e-6)) * (1.0 if margin > 2 else 0.5)
            if score > best_score:
                best, best_score = q, score
    if best is None:
        return None, 1.0
    quad = order_points(best / s)
    coverage = float(cv2.contourArea(quad.reshape(-1, 1, 2)) / (h * w))
    return quad, coverage


def rectangle_aspect(quad: np.ndarray, img_w: int, img_h: int) -> float | None:
    """True width/height of a photographed rectangle (Zhang & He 2007, principal point = image centre).

    Edge-length ratios are biased under perspective; this recovers the metric aspect from the
    homography. Returns None when the view is near-affine (focal length unobservable).
    """
    tl, tr, br, bl = quad.astype(np.float64)
    u0, v0 = img_w / 2.0, img_h / 2.0
    m1, m2, m3, m4 = (np.array([p[0], p[1], 1.0]) for p in (tl, tr, bl, br))
    k2 = np.dot(np.cross(m1, m4), m3) / np.dot(np.cross(m2, m4), m3)
    k3 = np.dot(np.cross(m1, m4), m2) / np.dot(np.cross(m3, m4), m2)
    n2 = k2 * m2 - m1
    n3 = k3 * m3 - m1
    if abs(n2[2]) < 1e-9 or abs(n3[2]) < 1e-9:
        return None
    f2 = -((n2[0] * n3[0] - (n2[0] * n3[2] + n2[2] * n3[0]) * u0 + n2[2] * n3[2] * u0 ** 2)
           + (n2[1] * n3[1] - (n2[1] * n3[2] + n2[2] * n3[1]) * v0 + n2[2] * n3[2] * v0 ** 2)) / (n2[2] * n3[2])
    if not np.isfinite(f2) or f2 <= 0:
        return None
    f = np.sqrt(f2)
    Ainv = np.linalg.inv(np.array([[f, 0, u0], [0, f, v0], [0, 0, 1.0]]))
    B = Ainv.T @ Ainv
    r2 = (n2 @ B @ n2) / (n3 @ B @ n3)
    if not np.isfinite(r2) or r2 <= 0:
        return None
    return float(np.sqrt(r2))


DEFAULT_PAPER = "A4"


def _snap_paper(w: float, h: float, default: str | None = None) -> tuple[str | None, float, float]:
    """Return (paper name, width_mm, height_mm) for portrait/landscape A4/Letter if aspect is close.

    A4 (1.414) and Letter (1.294) are only 9% apart and photos add error, so inside the band
    [1.25, 1.50] the default paper wins unless the other one matches within 1.5%.
    """
    default = default or DEFAULT_PAPER
    ar = max(w, h) / max(min(w, h), 1)
    orient = lambda name: (name, *PAPER_MM[name]) if h >= w else (name, PAPER_MM[name][1], PAPER_MM[name][0])
    for name, (pw, ph) in PAPER_MM.items():
        if name != default and abs(ar - ph / pw) / (ph / pw) < 0.015:
            return orient(name)
    if 1.25 <= ar <= 1.50:
        return orient(default)
    # unknown paper: assume A4 width
    pw = 210.0 if h >= w else 297.0
    return None, pw, pw * h / w


def warp_quad(bgr: np.ndarray, quad: np.ndarray, target_long: int) -> tuple[np.ndarray, str | None, float, float, float]:
    tl, tr, br, bl = quad
    wq = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    hq = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    ar = rectangle_aspect(quad, bgr.shape[1], bgr.shape[0])
    if ar is not None and abs((wq / ar) / hq - 1) < 0.15:
        hq = (hq + wq / ar) / 2  # blend: metric estimate is noisy when the camera model is off
    paper, wmm, hmm = _snap_paper(wq, hq)
    if paper:  # snap aspect ratio exactly to the paper format
        hq = wq * hmm / wmm if hq >= wq else hq
        if hq < wq:
            wq = hq * wmm / hmm
    est_dpi = float(wq / (wmm / 25.4))
    sc = target_long / max(wq, hq)
    W, H = int(round(wq * sc)), int(round(hq * sc))
    M = cv2.getPerspectiveTransform(quad.astype(np.float32), np.float32([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]]))
    out = cv2.warpPerspective(bgr, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return out, paper, wmm, hmm, est_dpi


# --------------------------------------------------------------------------- orientation / skew
def _ink_mask(gray: np.ndarray) -> np.ndarray:
    """Analysis-only binarization (never fed to recognizers)."""
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)


def estimate_skew(gray: np.ndarray, max_deg: float = 8.0) -> float:
    """Angle (deg, counter-clockwise positive) maximizing the horizontal projection-profile variance."""
    s = 1000 / max(gray.shape)
    g = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ink = _ink_mask(g)
    h, w = ink.shape
    c = (w / 2, h / 2)

    def score(a):
        M = cv2.getRotationMatrix2D(c, a, 1.0)
        r = cv2.warpAffine(ink, M, (w, h), flags=cv2.INTER_NEAREST)
        p = r.sum(1).astype(np.float64)
        return float(np.var(p))

    coarse = np.arange(-max_deg, max_deg + 1e-6, 0.5)
    best = max(coarse, key=score)
    fine = np.arange(best - 0.5, best + 0.5 + 1e-6, 0.1)
    return float(max(fine, key=score))


def rotate_bound(img: np.ndarray, angle_ccw: float, border=cv2.BORDER_REPLICATE) -> np.ndarray:
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle_ccw, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=border)


def rotate90(img: np.ndarray, cw_deg: int) -> np.ndarray:
    k = {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}[cw_deg % 360]
    return img if k is None else cv2.rotate(img, k)


def heuristic_orientation(gray: np.ndarray) -> int:
    """0 vs 90: text lines give a much spikier horizontal profile than vertical. Cannot see 180."""
    s = 800 / max(gray.shape)
    ink = _ink_mask(cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA))
    ink = cv2.dilate(ink, np.ones((1, 9), np.uint8))
    vh = np.var(ink.sum(1) / max(ink.shape[1], 1))
    vv = np.var(ink.sum(0) / max(ink.shape[0], 1))
    return 90 if vv > 1.6 * vh else 0


class OrientationDetector:
    """Returns clockwise rotation (0/90/180/270) that must be applied to make the page upright."""

    def __init__(self, method: str, tesseract_cmd: str | None = None, paddle_model_dir: str | None = None, device: str = "cpu"):
        self.method = method
        self.tesseract_cmd = tesseract_cmd
        self._paddle = None
        self._paddle_dir = paddle_model_dir
        self.device = device

    def _paddle_model(self):
        if self._paddle is None:
            from paddleocr import DocImgOrientationClassification

            kw = {"model_dir": self._paddle_dir} if self._paddle_dir else {}
            self._paddle = DocImgOrientationClassification(model_name="PP-LCNet_x1_0_doc_ori", device=self.device,
                                                           enable_mkldnn=False, **kw)
        return self._paddle

    def _paddle_vote(self, bgr) -> tuple[int, float] | None:
        try:
            r = self._paddle_model().predict(bgr, batch_size=1)[0]
            # label = clockwise rotation of the content (verified empirically); correction = inverse
            angle = int(r["label_names"][0])
            return (360 - angle) % 360, float(r["scores"][0])
        except Exception as e:
            log.warning("paddle orientation failed (%s)", e)
            return None

    def _osd_vote(self, gray) -> tuple[int, float] | None:
        try:
            import pytesseract

            if self.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
            s = 1600 / max(gray.shape)
            osd = pytesseract.image_to_osd(cv2.resize(gray, None, fx=s, fy=s), config="--psm 0")
            rot = int(re.search(r"Rotate: (\d+)", osd).group(1))
            conf = float(re.search(r"Orientation confidence: ([\d.]+)", osd).group(1))
            return rot % 360, conf
        except Exception as e:
            log.info("tesseract OSD unavailable (%s)", e)
            return None

    def _ocr_conf(self, gray: np.ndarray, rot: int, n_lines: int = 4) -> float:
        """Mean Tesseract confidence (psm 7) on the widest text lines after rotating by `rot`.
        Upside-down text gets clearly lower confidence than upright text in both scripts."""
        import pytesseract

        from .layout import ink_mask, remove_rules, text_lines

        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
        g = rotate90(gray, rot)
        W = g.shape[1]
        lines = text_lines(remove_rules(ink_mask(g)), W)
        lines = sorted(lines, key=lambda b: b[2] - b[0], reverse=True)[:n_lines]
        confs = []
        for x0, y0, x1, y1 in lines:
            pad = max(4, (y1 - y0) // 4)
            sub = g[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
            sub = cv2.copyMakeBorder(sub, 10, 10, 10, 10, cv2.BORDER_REPLICATE)
            d = pytesseract.image_to_data(sub, lang="ara+eng", config="--psm 7", output_type=pytesseract.Output.DICT)
            c = [float(x) for x, t in zip(d["conf"], d["text"]) if float(x) >= 0 and t.strip()]
            if c:
                confs.append(float(np.mean(c)))
        return float(np.mean(confs)) if confs else 0.0

    def detect(self, bgr: np.ndarray) -> tuple[int, str]:
        """Votes: PP-LCNet doc_ori (fast, but it sometimes flips upright Arabic pages to 180°)
        and Tesseract OSD. On disagreement, an OCR-confidence test decides."""
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        if self.method == "none":
            return 0, "none"
        if self.method == "heuristic":
            return heuristic_orientation(gray), "heuristic"
        votes = {}
        if self.method == "paddle":
            v = self._paddle_vote(bgr)
            if v and v[1] >= 0.6:
                votes["paddle"] = v
        v = self._osd_vote(gray)
        if v and v[1] >= 1.5:
            votes["osd"] = v
        desc = ",".join(f"{k}:{r}@{c:.2f}" for k, (r, c) in votes.items())
        rots = {r for r, _ in votes.values()}
        if len(votes) == 2 and len(rots) == 1:
            return rots.pop(), desc  # both models agree
        # one vote, none, or disagreement: OCR-confidence test over all four orientations
        try:
            confs = {r: self._ocr_conf(gray, r) for r in (0, 90, 180, 270)}
            best = max(confs, key=confs.get)
            if confs[best] <= 0:
                raise RuntimeError("no text")
            return best, (desc + " " if desc else "") + "ocr-check:" + ",".join(f"{r}={c:.0f}" for r, c in confs.items())
        except Exception as e:
            log.warning("orientation OCR check failed (%s)", e)
            if votes:
                return max(votes.values(), key=lambda v: v[1])[0], desc
            return heuristic_orientation(gray), "heuristic"

# --------------------------------------------------------------------------- dewarp
class UVDocDewarper:
    def __init__(self, device: str = "cpu", model_dir: str | None = None):
        from paddleocr import TextImageUnwarping

        kw = {"model_dir": model_dir} if model_dir else {}
        self.m = TextImageUnwarping(model_name="UVDoc", device=device, enable_mkldnn=False, **kw)

    def __call__(self, bgr: np.ndarray) -> np.ndarray:
        r = self.m.predict(bgr, batch_size=1)[0]
        out = np.asarray(r["doctr_img"])
        if out.dtype != np.uint8:
            out = np.clip(out, 0, 255).astype(np.uint8)
        return cv2.resize(out, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_CUBIC)


# --------------------------------------------------------------------------- full stage
def correct(bgr: np.ndarray, cfg: GeometryCfg, orienter: OrientationDetector | None = None,
            dewarper=None) -> GeometryResult:
    notes: list[str] = []
    quad, coverage = (None, None)
    if cfg.detect_boundary:
        quad, coverage = find_document_quad(bgr, cfg.min_doc_area_ratio)
    if quad is not None:
        page, paper, wmm, hmm, dpi = warp_quad(bgr, quad, cfg.target_long_side_px)
        notes.append("perspective-corrected")
    else:
        h, w = bgr.shape[:2]
        paper, wmm, hmm = _snap_paper(w, h)
        dpi = w / (wmm / 25.4)
        s = cfg.target_long_side_px / max(h, w)
        page = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
    dewarped = False
    if dewarper is not None:
        try:
            page = dewarper(page)
            dewarped = True
            notes.append("dewarped:UVDoc")
        except Exception as e:
            notes.append(f"dewarp failed: {e}")
    rotation = 0
    if orienter is not None:
        rotation, how = orienter.detect(page)
        notes.append(f"orientation:{how}")
        if rotation:
            page = rotate90(page, rotation)
            if rotation in (90, 270):
                wmm, hmm = hmm, wmm
                paper2, wmm, hmm = _snap_paper(page.shape[1], page.shape[0])
                paper = paper2 or paper
    skew = 0.0
    if cfg.deskew:
        skew = estimate_skew(cv2.cvtColor(page, cv2.COLOR_BGR2GRAY), cfg.max_deskew_deg)
        if abs(skew) >= 0.15:
            page = rotate_bound(page, skew)
            notes.append(f"deskew:{skew:.2f}deg")
    return GeometryResult(page=page, quad=quad, coverage=coverage, rotation=rotation, skew_deg=skew,
                          dewarped=dewarped, paper=paper, width_mm=wmm, height_mm=hmm, est_dpi=dpi, notes=notes)
