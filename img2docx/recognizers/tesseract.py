"""Tesseract 5 (LSTM) backend, ara+eng. Tables via ruling-line grid + per-cell OCR."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from ..config import TesseractCfg
from ..tables import cells_to_html, detect_grid, mark_header_rows
from .base import UNREADABLE, LineResult, RecognitionResult, Recognizer, RegionHints, strip_bidi_controls


def _has_suspicious_latin(text: str) -> bool:
    """Arabic-dominant line containing short Latin tokens (typical ara+eng confusion)."""
    import re

    ar = sum(1 for c in text if "\u0600" <= c <= "\u06ff")
    lat = re.findall(r"[A-Za-z]+", text)
    return ar > 10 and any(len(w) <= 4 for w in lat) and sum(len(w) for w in lat) < 0.25 * ar


def resolve_tesseract_cmd(cmd: str | None) -> str:
    cands = [cmd, os.environ.get("TESSERACT_CMD"), shutil.which("tesseract")]
    # local conda env next to the running interpreter
    import sys

    cands.append(str(Path(sys.executable).parent / "tesseract"))
    for c in cands:
        if c and Path(c).exists():
            return c
    raise FileNotFoundError("tesseract binary not found (set recognition.tesseract.cmd or TESSERACT_CMD)")


class TesseractRecognizer(Recognizer):
    name = "tesseract"

    def __init__(self, cfg: TesseractCfg):
        self.cfg = cfg
        self.cmd = resolve_tesseract_cmd(cfg.cmd)
        pytesseract.pytesseract.tesseract_cmd = self.cmd
        self._base_config = f'--tessdata-dir "{cfg.tessdata_dir}"' if cfg.tessdata_dir else ""
        self._version = str(pytesseract.get_tesseract_version())

    @property
    def engine_id(self) -> str:
        return f"tesseract-{self._version}:{self.cfg.langs}"

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _prep(crop: np.ndarray, line_h: float | None) -> tuple[np.ndarray, float]:
        """Grayscale + rescale so text lines are ~48px tall (Tesseract's sweet spot). No binarization."""
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        s = 1.0
        if line_h and line_h > 0:
            s = float(np.clip(48.0 / line_h, 0.5, 3.0))
        if abs(s - 1) > 0.05:
            g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
        g = cv2.copyMakeBorder(g, 12, 12, 12, 12, cv2.BORDER_REPLICATE)
        return g, s

    def _langs(self, hints: RegionHints | None) -> str:
        langs = self.cfg.langs
        parts = langs.split("+")
        if hints and hints.direction == "ltr" and "eng" in parts:  # primary language first
            parts = ["eng"] + [p for p in parts if p != "eng"]
        return "+".join(parts)

    def _ocr(self, gray: np.ndarray, psm: int, langs: str, scale: float, border=(12, 12)) -> tuple[str, float, list[LineResult]]:
        d = pytesseract.image_to_data(gray, lang=langs, config=f"--psm {psm} {self._base_config}",
                                      output_type=pytesseract.Output.DICT)
        lines: dict[tuple, list[int]] = {}
        for i, w in enumerate(d["text"]):
            if d["level"][i] != 5:
                continue
            w = strip_bidi_controls(w).strip()
            if not w:
                continue
            key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
            lines.setdefault(key, []).append(i)
        out_lines: list[LineResult] = []
        tot_c, tot_n = 0.0, 0
        for key in sorted(lines, key=lambda k: min(d["top"][i] for i in lines[k])):
            idx = lines[key]
            words = []
            confs = []
            for i in idx:
                w = strip_bidi_controls(d["text"][i]).strip()
                c = float(d["conf"][i])
                if c >= 0 and c < self.cfg.unreadable_word_conf:
                    w = UNREADABLE
                words.append(w)
                if c >= 0:
                    confs.append(c)
                    tot_c += c * len(w)
                    tot_n += len(w)
            x0 = min(d["left"][i] for i in idx); y0 = min(d["top"][i] for i in idx)
            x1 = max(d["left"][i] + d["width"][i] for i in idx); y1 = max(d["top"][i] + d["height"][i] for i in idx)
            bx, by = border
            bb = ((x0 - bx) / scale, (y0 - by) / scale, (x1 - bx) / scale, (y1 - by) / scale)
            out_lines.append(LineResult(" ".join(words), bb, (np.mean(confs) / 100) if confs else None))
        text = "\n".join(l.text for l in out_lines)
        conf = (tot_c / tot_n / 100) if tot_n else 0.0
        return text, conf, out_lines

    def _ocr_lines(self, crop: np.ndarray, hints: RegionHints) -> tuple[str, float, list[LineResult]]:
        """Segment lines ourselves (Tesseract's own segmentation often splits Arabic lines into
        columns), then OCR each line with --psm 7. Falls back to block mode."""
        from ..layout import ink_mask, text_lines

        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        pw = hints.page_w or max(g.shape[1], 1000)
        boxes = sorted(text_lines(ink_mask(g), pw), key=lambda b: b[1])
        langs = self._langs(hints)
        if not boxes:
            gray, s = self._prep(crop, hints.line_height_px)
            return self._ocr(gray, self.cfg.psm_block, langs, s)
        med = float(np.median([b[3] - b[1] for b in boxes]))
        out: list[LineResult] = []
        tot_c = tot_n = 0.0
        for (x0, y0, x1, y1) in boxes:
            lh = y1 - y0
            pad = int(max(4, 0.25 * lh))
            ox, oy = max(0, x0 - pad), max(0, y0 - pad)
            sub = g[oy:y1 + pad, ox:x1 + pad]
            psm = self.cfg.psm_line if lh < 1.7 * med else self.cfg.psm_block  # merged lines -> block mode
            s0 = float(np.clip(48.0 / (min(lh, med * 1.2)), 0.5, 3.0))
            if 0.8 < s0 < 1.25:
                s0 = 1.0
            # Tesseract's LSTM occasionally returns nothing / garbage for a line at one scale: retry
            best = None
            for s in dict.fromkeys([s0, 1.0, round(s0 * 1.4, 2), round(s0 * 0.75, 2)]):
                img = sub if s == 1.0 else cv2.resize(sub, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
                img = cv2.copyMakeBorder(img, 15, 15, 20, 20, cv2.BORDER_CONSTANT, value=int(np.percentile(sub, 95)))
                cand = self._ocr(img, psm, langs, s, border=(20, 15))
                if cand[0].strip() and (best is None or cand[1] > best[1]):
                    best = cand
                if best is not None and best[1] >= 0.75:
                    break
            if best is None:
                continue
            # ara+eng sometimes emits low-confidence Latin junk words inside Arabic lines
            # ('Se', 'Ue' for علماً): retry the line with Arabic only and keep the more confident read
            if "+" in langs and _has_suspicious_latin(best[0]):
                img = cv2.copyMakeBorder(sub, 15, 15, 20, 20, cv2.BORDER_CONSTANT, value=int(np.percentile(sub, 95)))
                alt = self._ocr(img, psm, "ara", 1.0, border=(20, 15))
                if alt[0].strip() and alt[1] > best[1]:
                    best = alt
            text, conf, lines = best
            n = len(text)
            tot_c += conf * n; tot_n += n
            for l in lines:
                if l.bbox:
                    l.bbox = (l.bbox[0] + ox, l.bbox[1] + oy, l.bbox[2] + ox, l.bbox[3] + oy)
            if len(lines) == 1:
                lines[0].bbox = (float(x0), float(y0), float(x1), float(y1))
            out += lines
        text = "\n".join(l.text for l in out)
        return text, (tot_c / tot_n if tot_n else 0.0), out

    # ------------------------------------------------------------------ API
    def recognize(self, crop: np.ndarray, region_type: str, hints: RegionHints | None = None) -> RecognitionResult:
        t = time.time()
        hints = hints or RegionHints()
        if region_type == "table":
            r = self._table(crop, hints)
        else:
            text, conf, lines = self._ocr_lines(crop, hints)
            r = RecognitionResult(text=text, confidence=conf, engine=self.engine_id, lines=lines)
        r.seconds = time.time() - t
        return r

    def _table(self, crop: np.ndarray, hints: RegionHints) -> RecognitionResult:
        rtl = hints.direction != "ltr"
        cells = detect_grid(crop, rtl=rtl)
        if not cells:
            gray, s = self._prep(crop, hints.line_height_px)
            text, conf, lines = self._ocr(gray, 6, self._langs(hints), s)
            res = RecognitionResult(text=text, confidence=conf * 0.8, engine=self.engine_id, lines=lines)
            res.flags.append("table_grid_not_found")
            return res
        mark_header_rows(cells, crop)
        confs, ns = [], []
        for c in cells:
            x0, y0, x1, y1 = c.bbox
            pad = 4
            sub = crop[y0 + pad:y1 - pad, x0 + pad:x1 - pad]
            if sub.size == 0:
                continue
            text, conf, lines = self._ocr_lines(sub, hints)
            c.text = " ".join(text.split())
            if c.text:
                confs.append(conf); ns.append(len(c.text))
        conf = float(np.average(confs, weights=ns)) if confs else 0.0
        return RecognitionResult(html=cells_to_html(cells), text=None, confidence=conf, engine=self.engine_id)
