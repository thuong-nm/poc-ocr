"""Shadow removal / background flattening. Keeps colour and grayscale detail (no binarization)."""
from __future__ import annotations

import cv2
import numpy as np


def estimate_background(channel: np.ndarray, k: int) -> np.ndarray:
    """Paper background: close (remove dark ink) then smooth, at reduced resolution for speed."""
    h, w = channel.shape
    s = 0.25
    small = cv2.resize(channel, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ks = max(3, int(k * s) | 1)
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ks, ks)))
    bg = cv2.medianBlur(bg, ks if ks <= 255 else 255)
    bg = cv2.GaussianBlur(bg, (0, 0), ks / 2)
    return cv2.resize(bg, (w, h), interpolation=cv2.INTER_CUBIC)


def flatten(bgr: np.ndarray, kernel_frac: float = 0.035, paper_level: float = 245.0) -> np.ndarray:
    """Divide each channel by its estimated background so paper becomes uniform ~paper_level.

    Ink keeps its relative contrast (and colour: blue stamps stay blue), so Arabic dots and
    diacritics are preserved for the recognizers.
    """
    k = max(15, int(min(bgr.shape[:2]) * kernel_frac))
    out = np.empty_like(bgr)
    for c in range(3):
        ch = bgr[..., c]
        bg = estimate_background(ch, k).astype(np.float32)
        norm = ch.astype(np.float32) / np.maximum(bg, 1.0) * paper_level
        out[..., c] = np.clip(norm, 0, 255).astype(np.uint8)
    return out
