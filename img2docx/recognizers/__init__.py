from __future__ import annotations

from ..config import RecognitionCfg
from .base import UNREADABLE, LineResult, RecognitionResult, Recognizer, RegionHints


def build_recognizer(name: str, cfg: RecognitionCfg, device: str = "cpu") -> Recognizer | None:
    """Factory: 'tesseract' | 'paddle' | 'vlm' | 'none'."""
    if name in (None, "none"):
        return None
    if name == "tesseract":
        from .tesseract import TesseractRecognizer

        return TesseractRecognizer(cfg.tesseract)
    if name == "paddle":
        from .paddle import PaddleRecognizer

        return PaddleRecognizer(cfg.paddle, device=device)
    if name == "vlm":
        from .qwen_vl import build_vlm

        return build_vlm(cfg.vlm, device=device)
    raise ValueError(f"unknown recognizer {name!r}")


__all__ = ["Recognizer", "RecognitionResult", "RegionHints", "LineResult", "UNREADABLE", "build_recognizer"]
