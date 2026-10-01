"""Recognizer interface shared by all OCR / VLM backends."""
from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field

import numpy as np

UNREADABLE = "[؟]"
# bidi control / invisible formatting chars some engines emit (LRM, RLM, ALM, embeddings, isolates)
_BIDI_CTRL = re.compile("[‎‏؜‪-‮⁦-⁩﻿]")


def strip_bidi_controls(s: str) -> str:
    return _BIDI_CTRL.sub("", s)


@dataclass
class LineResult:
    text: str
    bbox: tuple[float, float, float, float] | None = None  # crop px
    confidence: float | None = None


@dataclass
class RecognitionResult:
    text: str | None = None
    html: str | None = None
    confidence: float | None = None              # 0..1
    token_logprobs: list[float] | None = None
    engine: str = ""
    lines: list[LineResult] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)  # e.g. "repetition", "too_long", "truncated"
    raw: str | None = None
    seconds: float = 0.0

    @property
    def mean_logprob(self) -> float | None:
        if not self.token_logprobs:
            return None
        return float(np.mean(self.token_logprobs))


@dataclass
class RegionHints:
    direction: str | None = None      # "rtl" | "ltr" (page-level guess)
    line_height_px: float | None = None
    n_lines: int | None = None
    page_w: int | None = None         # normalized page width (scale reference for line segmentation)
    max_tokens: int | None = None


class Recognizer(abc.ABC):
    name: str = "base"

    @property
    def engine_id(self) -> str:
        return self.name

    @abc.abstractmethod
    def recognize(self, crop: np.ndarray, region_type: str, hints: RegionHints | None = None) -> RecognitionResult:
        """crop: BGR uint8 (grayscale/colour, never binarized)."""

    def close(self) -> None:  # pragma: no cover
        pass
