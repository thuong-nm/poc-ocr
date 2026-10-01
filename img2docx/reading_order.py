"""Reading order: recursive XY-cut that respects page direction (RTL: right→left columns)."""
from __future__ import annotations

from typing import Sequence

Box = tuple[float, float, float, float]
FLOATING = {"stamp"}  # overlap other content; ordered by position afterwards


def _groups_1d(intervals: list[tuple[float, float, int]], min_gap: float) -> list[list[int]]:
    """Merge overlapping 1D intervals; return index groups separated by gaps > min_gap."""
    iv = sorted(intervals)
    groups: list[list[int]] = []
    end = None
    for a, b, i in iv:
        if end is None or a > end + min_gap:
            groups.append([i])
            end = b
        else:
            groups[-1].append(i)
            end = max(end, b)
    return groups


def _shrink(b: Box, f: float = 0.08) -> Box:
    """Tolerate small overlaps between neighbouring boxes (detector slop)."""
    w, h = b[2] - b[0], b[3] - b[1]
    return (b[0] + w * f, b[1] + h * f, b[2] - w * f, b[3] - h * f)


def xycut(boxes: Sequence[Box], idx: list[int], rtl: bool, depth: int = 0) -> list[int]:
    if len(idx) <= 1 or depth > 40:
        return list(idx)
    sb = {i: _shrink(boxes[i]) for i in idx}
    hgroups = _groups_1d([(sb[i][1], sb[i][3], i) for i in idx], 0.0)
    vgroups = _groups_1d([(sb[i][0], sb[i][2], i) for i in idx], 0.0)
    # Prefer a vertical (column) cut when it yields columns that are each tall relative to the
    # region; otherwise horizontal bands first (letters are mostly full-width blocks).
    region_h = max(boxes[i][3] for i in idx) - min(boxes[i][1] for i in idx)
    if len(vgroups) > 1:
        tall = all((max(boxes[i][3] for i in g) - min(boxes[i][1] for i in g)) > 0.5 * region_h for g in vgroups)
        if tall or len(hgroups) == 1:
            vgroups.sort(key=lambda g: min(boxes[i][0] for i in g), reverse=rtl)
            if rtl:
                vgroups.sort(key=lambda g: max(boxes[i][2] for i in g), reverse=True)
            return [j for g in vgroups for j in xycut(boxes, g, rtl, depth + 1)]
    if len(hgroups) > 1:
        hgroups.sort(key=lambda g: min(boxes[i][1] for i in g))
        return [j for g in hgroups for j in xycut(boxes, g, rtl, depth + 1)]
    # cannot cut: fall back to top-to-bottom then by direction
    return sorted(idx, key=lambda i: (round(boxes[i][1] / 20), -boxes[i][2] if rtl else boxes[i][0]))


def reading_order(boxes: Sequence[Box], types: Sequence[str], direction: str) -> list[int]:
    """Return block indices in reading order. Headers first, footers last, stamps by position."""
    rtl = direction == "rtl"
    n = len(boxes)
    headers = [i for i in range(n) if types[i] == "header" or (types[i] == "logo")]
    footers = [i for i in range(n) if types[i] == "footer"]
    floating = [i for i in range(n) if types[i] in FLOATING]
    body = [i for i in range(n) if i not in set(headers) | set(footers) | set(floating)]
    # header strip: everything whose box lies inside the vertical span of header blocks goes with them
    order = []
    if headers:
        order += xycut(boxes, headers, rtl)
    order += xycut(boxes, body, rtl)
    order += xycut(boxes, footers, rtl)
    for f in sorted(floating, key=lambda i: (boxes[i][1] + boxes[i][3]) / 2):
        cy = (boxes[f][1] + boxes[f][3]) / 2
        pos = 0
        for k, j in enumerate(order):
            if j in footers:
                break
            if boxes[j][1] <= cy:
                pos = k + 1
        order.insert(pos, f)
    return order


def alignment_direction_hint(line_boxes: Sequence[Box], page_w: float) -> str | None:
    """Pre-recognition guess: ragged-left + flush-right body lines => RTL."""
    body = [b for b in line_boxes if (b[2] - b[0]) > 0.35 * page_w]
    if len(body) < 3:
        return None
    import numpy as np

    lefts = np.array([b[0] for b in body]); rights = np.array([b[2] for b in body])
    sl, sr = float(np.std(lefts)), float(np.std(rights))
    if sr < 0.6 * sl:
        return "rtl"
    if sl < 0.6 * sr:
        return "ltr"
    return None
