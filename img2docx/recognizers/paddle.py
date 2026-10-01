"""PaddleOCR 3.x text recognition (PP-OCRv5 arabic / en rec models) on our own line segmentation.

Used mainly as the cross-check engine. The PP-OCRv5 detector is skipped: on CPU it costs ~25 s per
page, and full-page detection + recognition degrades badly on long Arabic lines. Our line
segmentation + batched recognition is ~10x faster and more accurate. Known limitation (verified):
the arabic rec model drops or mangles Latin digits inside RTL lines -> agreement ignores digits.
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from ..config import PaddleOcrCfg
from .base import LineResult, RecognitionResult, Recognizer, RegionHints, strip_bidi_controls


class PaddleRecognizer(Recognizer):
    name = "paddle"

    def __init__(self, cfg: PaddleOcrCfg, device: str = "cpu"):
        from paddleocr import TextRecognition

        self.cfg = cfg
        self.device = device
        self._rec = {}
        for key, name in (("rtl", cfg.rec_model_ar), ("ltr", cfg.rec_model_en)):
            kw = {"model_dir": str(Path(cfg.model_root) / name)} if cfg.model_root else {}
            self._rec[key] = TextRecognition(model_name=name, device=device, enable_mkldnn=cfg.enable_mkldnn, **kw)

    @property
    def engine_id(self) -> str:
        return f"paddleocr:{self.cfg.rec_model_ar}/{self.cfg.rec_model_en}"

    def recognize(self, crop: np.ndarray, region_type: str, hints: RegionHints | None = None) -> RecognitionResult:
        from ..layout import ink_mask, text_lines

        t = time.time()
        hints = hints or RegionHints()
        rtl = hints.direction != "ltr"
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        boxes = sorted(text_lines(ink_mask(g), hints.page_w or max(g.shape[1], 1000)), key=lambda b: b[1])
        if not boxes:
            boxes = [(0, 0, crop.shape[1], crop.shape[0])]
        ink = ink_mask(g)
        imgs, owner = [], []
        for li, (x0, y0, x1, y1) in enumerate(boxes):
            pad = int(max(4, 0.2 * (y1 - y0)))
            ys0, xs0 = max(0, y0 - pad), max(0, x0 - pad)
            sub = crop[ys0:y1 + pad, xs0:x1 + pad]
            chunks = _split_long_line(ink[ys0:y1 + pad, xs0:x1 + pad], y1 - y0)
            if rtl:
                chunks = chunks[::-1]  # reading order: right chunk first
            for a, b in chunks:
                imgs.append(cv2.copyMakeBorder(sub[:, a:b], 4, 4, 8, 8, cv2.BORDER_REPLICATE))
                owner.append(li)
        res = self._rec["rtl" if rtl else "ltr"].predict(imgs, batch_size=8)
        per_line: dict[int, list] = {}
        for li, r in zip(owner, res):
            per_line.setdefault(li, []).append(r)
        lines = []
        for li, rs in sorted(per_line.items()):
            txt = " ".join(strip_bidi_controls(r["rec_text"]).strip() for r in rs).strip()
            if txt:
                sc = float(np.mean([r["rec_score"] for r in rs]))
                lines.append(LineResult(" ".join(txt.split()), tuple(float(v) for v in boxes[li]), sc))
        n = sum(len(l.text) for l in lines)
        conf = sum(l.confidence * len(l.text) for l in lines) / n if n else 0.0
        return RecognitionResult(text="\n".join(l.text for l in lines), confidence=conf, engine=self.engine_id,
                                 lines=lines, seconds=time.time() - t)


def _split_long_line(ink: np.ndarray, line_h: int, max_aspect: float = 12.0) -> list[tuple[int, int]]:
    """Cut a wide line image at inter-word gaps so each chunk has aspect <= max_aspect."""
    h, w = ink.shape
    lh = max(8, line_h)
    if w <= max_aspect * lh:
        return [(0, w)]
    col = (ink > 0).sum(0)
    empty = col == 0
    # gap centres: runs of empty columns at least 0.2*lh wide
    gaps = []
    i = 0
    while i < w:
        if empty[i]:
            j = i
            while j < w and empty[j]:
                j += 1
            if j - i >= 0.2 * lh:
                gaps.append((i + j) // 2)
            i = j
        else:
            i += 1
    cuts, start = [], 0
    target = int(max_aspect * lh * 0.85)
    while w - start > max_aspect * lh:
        cands = [g for g in gaps if start + 0.3 * target < g <= start + target]
        if not cands:
            cands = [g for g in gaps if g > start + 0.3 * target]
            if not cands:
                break
            cut = cands[0]
        else:
            cut = cands[-1]
        cuts.append(cut)
        start = cut
    edges = [0] + cuts + [w]
    return [(edges[k], edges[k + 1]) for k in range(len(edges) - 1) if edges[k + 1] - edges[k] > 2]
