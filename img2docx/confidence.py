"""Block / page confidence and review flags."""
from __future__ import annotations

from rapidfuzz.distance import Levenshtein

from .config import ConfidenceCfg
from .postprocess import normalize_for_compare
from .recognizers.base import UNREADABLE
from .schema import Block, QAReport, ReviewSummary, TEXT_TYPES


def agreement(a: str | None, b: str | None, ignore_digits: bool = False) -> float | None:
    """1 - normalized edit distance between two transcriptions (after light normalization)."""
    if a is None or b is None:
        return None
    na, nb = normalize_for_compare(a, ignore_digits), normalize_for_compare(b, ignore_digits)
    if not na and not nb:
        return 1.0
    return 1.0 - Levenshtein.normalized_distance(na, nb)


def score_block(b: Block, engine_conf: float | None, agree: float | None, flags: list[str], cfg: ConfidenceCfg) -> None:
    reasons = list(flags)
    base = engine_conf if engine_conf is not None else 0.5
    if agree is not None:
        s = cfg.w_engine * base + cfg.w_agreement * agree
        if agree < 0.6:
            reasons.append(f"engines disagree (agreement {agree:.2f})")
    else:
        s = base
    if b.type == "handwritten_note":
        s -= cfg.handwritten_penalty
        reasons.append("handwritten")
    txt = b.text or b.html or ""
    if UNREADABLE in txt:
        n = txt.count(UNREADABLE)
        s -= min(0.3, 0.05 * n)
        reasons.append(f"{n} unreadable word(s) marked {UNREADABLE}")
    if not txt.strip():
        s = min(s, 0.2)
        reasons.append("empty transcription")
    s = max(0.0, min(1.0, s))
    b.confidence = round(s, 4)
    if s < cfg.block_review_threshold:
        reasons.append(f"confidence {s:.2f} < {cfg.block_review_threshold}")
    b.needs_review = s < cfg.block_review_threshold or b.type == "handwritten_note" or UNREADABLE in txt
    b.review_reasons = reasons


SEVERE_QA = ("blurry", "low resolution", "glare", "effective resolution")


def page_review(blocks: list[Block], qa: QAReport, cfg: ConfidenceCfg) -> ReviewSummary:
    tot = 0.0
    wsum = 0.0
    reasons = []
    for b in blocks:
        if (b.type in TEXT_TYPES or b.type == "table") and b.confidence is not None:
            n = max(1, len(b.text or b.html or ""))
            tot += b.confidence * n
            wsum += n
    score = tot / wsum if wsum else 0.0
    flagged = [b for b in blocks if b.needs_review]
    if flagged:
        reasons.append(f"{len(flagged)} block(s) need review: " + ", ".join(f"{b.id}({b.type})" for b in flagged[:12]))
    if score < cfg.page_review_threshold:
        reasons.append(f"page score {score:.2f} < {cfg.page_review_threshold}")
    for w in qa.warnings:
        if any(k in w for k in SEVERE_QA):
            reasons.append("image quality: " + w)
    if not wsum:
        reasons.append("no text recognized")
    return ReviewSummary(page_score=round(score, 4), needs_review=bool(reasons), reasons=reasons)
