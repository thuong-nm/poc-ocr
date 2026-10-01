"""Layout analysis: PP-DocLayout regions + classical line-based recall pass + ink-colour heuristics.

Output regions use our classes (schema.BlockType). doc_number/date are refined after recognition
(postprocess.refine_types), because they are only distinguishable by content.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

from .config import LayoutCfg

log = logging.getLogger(__name__)

# PP-DocLayout(_plus / V2 / V3) label -> our class. Unknown labels map to "paragraph".
LABEL_MAP = {
    "text": "paragraph", "paragraph": "paragraph", "content": "paragraph", "abstract": "paragraph",
    "reference": "paragraph", "reference_content": "paragraph", "algorithm": "paragraph",
    "formula": "paragraph", "formula_number": "paragraph", "aside_text": "paragraph",
    "footnote": "footer", "vision_footnote": "footer",
    "doc_title": "title", "paragraph_title": "title", "title": "title",
    "figure_title": "paragraph", "table_title": "paragraph", "chart_title": "paragraph",
    "header": "header", "footer": "footer", "number": "footer",
    "table": "table", "image": "figure", "figure": "figure", "chart": "figure",
    "header_image": "logo", "footer_image": "figure", "seal": "stamp", "list": "list",
}


@dataclass
class Region:
    type: str
    bbox: tuple[float, float, float, float]
    score: float
    source: str
    raw_label: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def area(self) -> float:
        x0, y0, x1, y1 = self.bbox
        return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _inter(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def containment(a, b) -> float:
    """fraction of a inside b"""
    return _inter(a, b) / max(_area(a), 1e-6)


# --------------------------------------------------------------------------- ink analysis (analysis only)
def ink_mask(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 41, 18)


def colored_ink_mask(bgr: np.ndarray) -> np.ndarray:
    """Pen/stamp ink that is clearly coloured (blue, violet, red, green), not black/gray print."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    s, v = hsv[..., 1], hsv[..., 2]
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    paper = float(np.percentile(g, 90))
    # light stamp ink after multiply-compositing has S≈50-60; near-black pixels have unstable hue/sat
    m = ((s > 42) & (v < paper - 20) & (v > 60)).astype(np.uint8) * 255
    return cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def remove_rules(ink: np.ndarray) -> np.ndarray:
    h, w = ink.shape
    hor = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(25, w // 12), 1)))
    ver = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(25, h // 12))))
    return cv2.subtract(ink, cv2.bitwise_or(hor, ver))


def text_lines(ink: np.ndarray, page_w: int) -> list[tuple[int, int, int, int]]:
    """Text-line boxes from an ink mask: horizontal smearing + connected components."""
    kx = max(9, page_w // 70)
    sm = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (kx, 3)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(sm, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if h < page_w * 0.006 or h > page_w * 0.08 or w < page_w * 0.012:
            continue
        if a < 0.12 * w * h * 0.5:  # extremely sparse = noise
            continue
        out.append((x, y, x + w, y + h))
    return out


def group_lines(lines: list[tuple[int, int, int, int]]) -> list[list[tuple[int, int, int, int]]]:
    """Group vertically adjacent, horizontally overlapping lines into blocks."""
    lines = sorted(lines, key=lambda b: b[1])
    groups: list[list] = []
    for ln in lines:
        lh = ln[3] - ln[1]
        placed = False
        for g in groups:
            last = g[-1]
            gx0, gx1 = min(b[0] for b in g), max(b[2] for b in g)
            gap = ln[1] - last[3]
            ov = min(gx1, ln[2]) - max(gx0, ln[0])
            if -lh * 0.5 < gap < 0.9 * max(lh, last[3] - last[1]) and ov > 0.3 * min(gx1 - gx0, ln[2] - ln[0]):
                g.append(ln)
                placed = True
                break
        if not placed:
            groups.append([ln])
    return groups


def _union(bs):
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


# --------------------------------------------------------------------------- backends
class PaddleLayout:
    def __init__(self, cfg: LayoutCfg, device: str = "cpu"):
        from paddleocr import LayoutDetection

        kw = {"model_dir": cfg.model_dir} if cfg.model_dir else {}
        self.cfg = cfg
        self.model = LayoutDetection(model_name=cfg.model_name, device=device, enable_mkldnn=False,
                                     threshold=cfg.threshold, **kw)

    def detect(self, bgr: np.ndarray) -> list[Region]:
        res = self.model.predict(bgr, batch_size=1)[0]
        out = []
        for b in res["boxes"]:
            lab = b["label"]
            x0, y0, x1, y1 = (float(v) for v in b["coordinate"])
            out.append(Region(LABEL_MAP.get(lab, "paragraph"), (x0, y0, x1, y1), float(b["score"]),
                              f"{self.cfg.model_name}:{lab}", raw_label=lab))
        return out


class LayoutAnalyzer:
    def __init__(self, cfg: LayoutCfg, device: str = "cpu"):
        self.cfg = cfg
        self.model = None
        if cfg.backend == "paddle":
            try:
                self.model = PaddleLayout(cfg, device)
            except Exception as e:
                log.warning("layout model unavailable (%s); using heuristic layout only", e)
                if device != "cpu":
                    try:
                        self.model = PaddleLayout(cfg, "cpu")
                    except Exception:
                        self.model = None

    @property
    def engine_id(self) -> str:
        return self.cfg.model_name if self.model is not None else "heuristic"

    def analyze(self, page: np.ndarray) -> list[Region]:
        H, W = page.shape[:2]
        regions: list[Region] = []
        if self.model is not None:
            try:
                regions = self.model.detect(page)
            except Exception as e:  # e.g. CUDA OOM -> retry on CPU once
                log.warning("layout inference failed (%s); retrying on CPU", e)
                try:
                    self.model = PaddleLayout(self.cfg, "cpu")
                    regions = self.model.detect(page)
                except Exception as e2:
                    log.error("layout model failed on CPU too (%s); heuristic only", e2)
        gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
        ink = ink_mask(gray)
        col = colored_ink_mask(page) if self.cfg.detect_ink_colors else np.zeros_like(gray)
        bx, by = int(W * 0.02), int(H * 0.015)  # photo-border residue is never content
        for m in (ink, col):
            m[:by] = 0; m[-by:] = 0; m[:, :bx] = 0; m[:, -bx:] = 0
        regions = [self._refine_image_region(r, page, col, ink) for r in regions]
        regions = [x for r in regions for x in self._split_colored(r, col, W, H)]
        regions = self._dedupe(regions)
        if self.cfg.detect_ink_colors:
            regions = self._carve_colored(regions, page, ink, col, W, H)
        if self.cfg.fill_uncovered_text:
            regions += self._uncovered(regions, ink, col, W, H)
        regions = self._dedupe(regions)
        for r in regions:
            r.bbox = (max(0.0, r.bbox[0]), max(0.0, r.bbox[1]), min(float(W), r.bbox[2]), min(float(H), r.bbox[3]))
        return [r for r in regions if r.area > 0]

    # ---- helpers
    @staticmethod
    def _dedupe(regions: list[Region]) -> list[Region]:
        """Resolve overlapping detections.

        * text inside a table -> dropped
        * image-like regions may overlap text (stamps over text): only deduped within their family
        * nested text boxes: when a big text box is (mostly) tiled by smaller ones, keep the fine
          boxes (one per paragraph/line group); otherwise keep the big one
        """
        prio = {"table": 5, "stamp": 4, "logo": 4, "figure": 3, "signature": 3, "header": 2, "footer": 2,
                "title": 2, "handwritten_note": 2, "paragraph": 1, "list": 1, "doc_number": 1, "date": 1}
        text_like = {"paragraph", "title", "header", "footer", "list", "doc_number", "date", "handwritten_note"}
        regs = sorted(regions, key=lambda r: (prio.get(r.type, 0), r.score, r.area), reverse=True)
        drop: set[int] = set()
        for i, r in enumerate(regs):
            if i in drop:
                continue
            for j, k in enumerate(regs):
                if j == i or j in drop:
                    continue
                c = containment(r.bbox, k.bbox)  # r inside k
                if c < 0.5:
                    continue
                if r.type in text_like and k.type == "table" and c > 0.6:
                    drop.add(i); break
                r_text, k_text = r.type in text_like, k.type in text_like
                if r_text != k_text:
                    continue
                if not r_text:
                    if c > 0.75:
                        drop.add(i if prio.get(r.type, 0) <= prio.get(k.type, 0) else j)
                    continue
                # both text: is k tiled by smaller text boxes (including r)?
                inner = [x for x in regs if x is not k and x.type in text_like and containment(x.bbox, k.bbox) > 0.5]
                cover = sum(_inter(x.bbox, k.bbox) for x in inner) / max(_area(k.bbox), 1)
                if len(inner) >= 2 and cover > 0.6:
                    drop.add(j)
                elif c > 0.75 or (c > 0.5 and r.area < k.area):
                    drop.add(i); break
        return [r for i, r in enumerate(regs) if i not in drop]

    @staticmethod
    def _refine_image_region(r: Region, page: np.ndarray, col: np.ndarray, ink: np.ndarray) -> Region:
        H, W = page.shape[:2]
        x0, y0, x1, y1 = (int(v) for v in r.bbox)
        if r.type in ("header", "title", "paragraph") and min(x1 - x0, y1 - y0) > 0.08 * W and _is_graphic(ink[y0:y1, x0:x1]):
            r.type = "logo" if y1 < H * 0.22 else "figure"
            r.source += "+graphic"
        if r.type not in ("figure", "logo", "stamp"):
            return r
        if r.type == "figure" and _is_texty(ink[y0:y1, x0:x1], col[y0:y1, x0:x1], W):
            r.type = "paragraph"  # detector called a text line (e.g. calligraphic basmala) an image
            r.source += "+texty"
            return r
        sub = col[y0:y1, x0:x1] > 0
        ik = ink[y0:y1, x0:x1] > 0
        frac = float((sub & ik).sum() / max(1, ik.sum())) if sub.size else 0.0  # coloured share of the ink
        w, h = x1 - x0, y1 - y0
        squareish = 0.6 < w / max(h, 1) < 1.6
        if r.type == "figure":
            if y1 < H * 0.2 and abs((x0 + x1) / 2 - W / 2) < W * 0.2:
                r.type = "logo"
            elif frac > 0.3 and squareish and w > 0.08 * W:
                r.type = "stamp"
            elif frac > 0.5:
                r.type = LayoutAnalyzer._classify_colored(col[y0:y1, x0:x1] > 0, (x0, y0, w, h), W, H)
                r.source += "+colored"
        r.extra["colored_frac"] = frac
        return r

    def _carve_colored(self, regions: list[Region], page, ink, col, W, H) -> list[Region]:
        """Inside text regions: mostly-coloured ink => handwriting/signature; a large coloured
        blob below/above black text lines (signature under a name) is split off."""
        out = []
        text_like = {"paragraph", "title", "header", "footer", "list"}
        for r in regions:
            if r.type not in text_like:
                out.append(r)
                continue
            x0, y0, x1, y1 = (int(v) for v in r.bbox)
            ci = col[y0:y1, x0:x1] > 0
            ki = ink[y0:y1, x0:x1] > 0
            n_ink = max(1, int(ki.sum()))
            colored_frac = float((ci & ki).sum()) / n_ink
            if colored_frac > 0.6:
                blob = ci
                r.type = self._classify_colored(blob, (x0, y0, x1 - x0, y1 - y0), W, H)
                r.source += f"+colored:{colored_frac:.2f}"
                out.append(r)
                continue
            if colored_frac < 0.08:
                out.append(r)
                continue
            # split: rows dominated by coloured ink at the bottom or top of the box
            sat = cv2.cvtColor(page[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)[..., 1]
            black = ki & (sat < 40) & ~cv2.dilate(ci.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
            black = cv2.morphologyEx(black.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
            rows_b = black.sum(1) > max(6, 0.02 * (x1 - x0))
            rows_c = ci.sum(1) > max(3, 0.01 * (x1 - x0))
            if not rows_b.any():
                out.append(r); continue
            yb0, yb1 = _main_row_cluster(rows_b, black.sum(1))
            below = rows_c.copy(); below[:yb1] = False
            above = rows_c.copy(); above[yb0:] = False
            carved = False
            for part, (py0, py1) in (("below", (yb1, len(rows_c))), ("above", (0, yb0))):
                sel = below if part == "below" else above
                if sel.sum() < 0.01 * H:
                    continue
                ys = np.where(sel)[0]
                cb = ci[ys.min():ys.max() + 1]
                xs = np.where(cb.any(0))[0]
                bb = (x0 + xs.min(), y0 + ys.min(), x0 + xs.max() + 1, y0 + ys.max() + 1)
                typ = self._classify_colored(cb[:, xs.min():xs.max() + 1], (bb[0], bb[1], bb[2] - bb[0], bb[3] - bb[1]), W, H)
                out.append(Region(typ, tuple(float(v) for v in bb), 0.5, f"heuristic:carved-from:{r.raw_label}"))
                carved = True
            if carved:
                r.bbox = (r.bbox[0], float(y0 + yb0), r.bbox[2], float(y0 + yb1))
            out.append(r)
        return out

    def _uncovered(self, regions: list[Region], ink: np.ndarray, col: np.ndarray, W: int, H: int) -> list[Region]:
        mask = remove_rules(ink)
        image_like = {"stamp", "logo", "figure", "signature", "handwritten_note"}
        col_d = cv2.dilate(col, np.ones((5, 5), np.uint8))
        for r in regions:
            x0, y0, x1, y1 = (int(v) for v in r.bbox)
            pad = 4
            if r.type in ("stamp", "signature"):
                # stamps/signatures overlap printed text: hide only their coloured ink so black
                # text underneath (e.g. the signatory's name) still gets its own text region
                sl = (slice(max(0, y0 - pad), y1 + pad), slice(max(0, x0 - pad), x1 + pad))
                mask[sl][col_d[sl] > 0] = 0
                continue
            mask[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad] = 0
        new: list[Region] = []
        # 1) coloured-ink blobs (stamps over text, signatures, handwriting not found by the model)
        cmask = col.copy()
        for r in regions:
            if r.type in image_like:
                x0, y0, x1, y1 = (int(v) for v in r.bbox)
                cmask[y0:y1, x0:x1] = 0
        cm = cv2.morphologyEx(cmask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (W // 40, H // 120)))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(cm, 8)
        for i in range(1, n):
            x, y, w, h, a = stats[i]
            if w < W * 0.03 or h < H * 0.008 or a < 0.0005 * W * H or w * h > 0.2 * W * H:
                continue
            blob = (cmask[y:y + h, x:x + w] > 0)
            if blob.mean() < 0.01:
                continue
            bb = (x, y, x + w, y + h)
            typ = self._classify_colored(blob, (x, y, w, h), W, H)
            inside_text = any(containment(bb, r.bbox) > 0.6 for r in regions if r.type not in image_like and r.type != "table")
            if typ != "stamp" and inside_text:
                continue  # coloured text inside a text region (handled by _carve_colored)
            new.append(Region(typ, tuple(float(v) for v in bb), 0.5, f"heuristic:colored-ink:{typ}"))
            if typ != "stamp":
                mask[y:y + h, x:x + w] = 0
            else:
                mask[cv2.dilate(cmask, np.ones((3, 3), np.uint8)) > 0] = 0
        # 2) black text lines not covered by the model
        lines = text_lines(mask, W)
        for g in group_lines(lines):
            b = _union(g)
            if (b[2] - b[0]) * (b[3] - b[1]) < 0.0008 * W * H:
                continue
            sub = mask[b[1]:b[3], b[0]:b[2]]
            if sub.mean() / 255 < 0.04:
                continue
            new.append(Region("paragraph", tuple(float(v) for v in b), 0.4, "heuristic:lines",
                              extra={"n_lines": len(g)}))
        return new

    def _split_colored(self, r: Region, col: np.ndarray, W: int, H: int) -> list[Region]:
        """An image box often spans a stamp *and* the signature next to it: split it into its
        separate coloured-ink blobs and classify each."""
        if r.type not in ("figure", "stamp", "signature", "handwritten_note") or r.type == "logo":
            return [r]
        x0, y0, x1, y1 = (int(v) for v in r.bbox)
        sub = col[y0:y1, x0:x1].copy()
        if sub.size == 0 or sub.mean() / 255 < 0.003:
            return [r]
        out: list[Region] = []
        # round rubber stamps first (Hough), then whatever coloured ink remains (signature, notes)
        for (cx, cy, rad) in _find_circles(sub, W):
            bb = (float(max(0, x0 + cx - rad)), float(max(0, y0 + cy - rad)), float(x0 + cx + rad), float(y0 + cy + rad))
            out.append(Region("stamp", bb, r.score, r.source + "+circle", raw_label=r.raw_label))
            cv2.circle(sub, (int(cx), int(cy)), int(rad * 1.08), 0, -1)
        if out and sub.mean() / 255 < 0.002:
            return out
        cm = cv2.morphologyEx(sub, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (W // 90, W // 90)))
        n, lab, st, _ = cv2.connectedComponentsWithStats(cm, 8)
        blobs = [st[i] for i in range(1, n) if st[i][2] > W * 0.03 and st[i][3] > H * 0.008]
        if len(blobs) < 2 and not out:
            if len(blobs) == 1 and r.type in ("figure", "handwritten_note", "signature"):
                bx, by, bw, bh, _ = blobs[0]
                r.type = self._classify_colored(sub[by:by + bh, bx:bx + bw] > 0, (x0 + bx, y0 + by, bw, bh), W, H)
            return [r]
        for bx, by, bw, bh, _ in blobs:
            bb = (float(x0 + bx), float(y0 + by), float(x0 + bx + bw), float(y0 + by + bh))
            typ = self._classify_colored(sub[by:by + bh, bx:bx + bw] > 0, (x0 + bx, y0 + by, bw, bh), W, H)
            out.append(Region(typ, bb, r.score, r.source + f"+split:{typ}", raw_label=r.raw_label))
        return out

    @staticmethod
    def _classify_colored(blob: np.ndarray, xywh, W, H) -> str:
        x, y, w, h = xywh
        ar = w / max(h, 1)
        if 0.7 < ar < 1.4 and w > W * 0.08:
            return "stamp"
        # join broken pen strokes before looking for the dominant stroke
        blob = cv2.dilate(blob.astype(np.uint8), np.ones((5, 5), np.uint8))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(blob, 8)
        widths = sorted((s[2] for s in stats[1:]), reverse=True)
        biggest = widths[0] if widths else 0
        # signature: one or two long continuous strokes spanning most of the box
        if biggest > 0.55 * w and n - 1 <= 4 and w > 0.1 * W:
            return "signature"
        return "handwritten_note"


def _find_circles(colored: np.ndarray, W: int) -> list[tuple[float, float, float]]:
    """Ring-shaped stamps in a coloured-ink mask (HoughCircles on the blurred mask)."""
    if colored.size == 0 or min(colored.shape) < W * 0.08:
        return []
    m = cv2.GaussianBlur(colored, (0, 0), 2)
    c = cv2.HoughCircles(m, cv2.HOUGH_GRADIENT, dp=1.5, minDist=W * 0.1, param1=80, param2=40,
                         minRadius=int(W * 0.04), maxRadius=int(W * 0.14))
    if c is None:
        return []
    out = []
    for cx, cy, rad in c[0][:3]:
        # verify: enough coloured ink along the circumference (a real ring)
        ang = np.linspace(0, 2 * np.pi, 180, endpoint=False)
        xs = np.clip((cx + rad * np.cos(ang)).astype(int), 0, colored.shape[1] - 1)
        ys = np.clip((cy + rad * np.sin(ang)).astype(int), 0, colored.shape[0] - 1)
        ring = cv2.dilate(colored, np.ones((7, 7), np.uint8))[ys, xs] > 0
        if ring.mean() > 0.55:
            out.append((float(cx), float(cy), float(rad)))
    return out


def _is_texty(ink_crop: np.ndarray, col_crop: np.ndarray, W: int) -> bool:
    """A detector 'image' that is really a line of (black) text: thin wide line boxes, little colour."""
    if ink_crop.size == 0 or (col_crop > 0).mean() > 0.02 or _is_graphic(ink_crop):
        return False
    lines = text_lines(ink_crop, W)
    if not lines:
        return False
    covered = sum(b[2] - b[0] for b in lines) / max(1, ink_crop.shape[1])
    return covered > 0.5 and all((b[3] - b[1]) < 0.06 * W for b in lines)


def _main_row_cluster(rows: np.ndarray, weight: np.ndarray) -> tuple[int, int]:
    """Row runs -> clusters (gap < 1.5x run height); return [y0, y1) of the heaviest cluster."""
    runs, i, n = [], 0, len(rows)
    while i < n:
        if rows[i]:
            j = i
            while j < n and rows[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    big = [r for r in runs if r[1] - r[0] >= 6] or runs
    lh = float(np.median([b - a for a, b in big]))
    clusters = [[big[0]]]
    for a, b in big[1:]:
        if a - clusters[-1][-1][1] < 1.5 * lh:
            clusters[-1].append((a, b))
        else:
            clusters.append([(a, b)])
    best = max(clusters, key=lambda c: sum(weight[a:b].sum() for a, b in c))
    return best[0][0], best[-1][1]


def _is_graphic(ink_crop: np.ndarray) -> bool:
    """Logo/emblem vs text: graphics have one dominant connected component and dense fill."""
    if ink_crop.size == 0:
        return False
    h, w = ink_crop.shape
    if not (0.5 < w / max(h, 1) < 2.0):
        return False
    n, lab, st, _ = cv2.connectedComponentsWithStats((ink_crop > 0).astype(np.uint8), 8)
    if n <= 1:
        return False
    areas = st[1:, 4]
    big = areas.max() / max(areas.sum(), 1)
    bw, bh = st[1 + int(np.argmax(areas)), 2], st[1 + int(np.argmax(areas)), 3]
    return bool(big > 0.35 and bw > 0.5 * w and bh > 0.5 * h)


def draw_regions(page: np.ndarray, regions, labels=None) -> np.ndarray:
    colors = {"paragraph": (0, 160, 0), "title": (200, 0, 0), "table": (0, 0, 220), "header": (160, 0, 160),
              "footer": (160, 0, 160), "stamp": (0, 140, 255), "signature": (0, 200, 255), "logo": (255, 120, 0),
              "figure": (128, 128, 0), "handwritten_note": (255, 0, 255), "doc_number": (0, 90, 200), "date": (0, 90, 200),
              "list": (0, 120, 60)}
    vis = page.copy()
    for i, r in enumerate(regions):
        t = r.type
        bb = r.bbox if hasattr(r, "bbox") and isinstance(r.bbox, tuple) else r.bbox.as_list()
        x0, y0, x1, y1 = (int(v) for v in bb)
        c = colors.get(t, (90, 90, 90))
        cv2.rectangle(vis, (x0, y0), (x1, y1), c, 3)
        txt = labels[i] if labels else t
        cv2.putText(vis, txt, (x0 + 3, max(14, y0 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, c, 2)
    return vis
