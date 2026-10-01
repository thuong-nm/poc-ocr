"""Table structure: ruling-line grid detection with merged cells, HTML build/parse."""
from __future__ import annotations

import html as _html
from dataclasses import dataclass

import cv2
import numpy as np
from bs4 import BeautifulSoup


@dataclass
class Cell:
    row: int
    col: int          # logical column (0 = first in reading order: rightmost for RTL tables)
    rowspan: int
    colspan: int
    bbox: tuple[int, int, int, int]  # in table-crop px
    text: str = ""
    header: bool = False


def _cluster(vals: list[float], tol: float) -> list[float]:
    vals = sorted(vals)
    out: list[list[float]] = []
    for v in vals:
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [float(np.mean(c)) for c in out]


def detect_grid(crop_bgr: np.ndarray, rtl: bool) -> list[Cell] | None:
    """Detect a ruled grid and merged cells. Returns None if no grid with >=2x2 cells is found."""
    g = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    ink = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 12)
    # kernels longer than tall glyph strokes (alef/lam ~1.2 x-height) but shorter than a row
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, w // 12), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(30, h // 7)))
    hor = cv2.dilate(cv2.morphologyEx(ink, cv2.MORPH_OPEN, hk), np.ones((3, 3), np.uint8))
    ver = cv2.dilate(cv2.morphologyEx(ink, cv2.MORPH_OPEN, vk), np.ones((3, 3), np.uint8))

    def segs(mask, axis):
        n, _, st, _ = cv2.connectedComponentsWithStats(mask, 8)
        out = []
        for i in range(1, n):
            x, y, ww, hh, _ = st[i]
            out.append((y + hh / 2, x, x + ww) if axis == 0 else (x + ww / 2, y, y + hh))
        return out

    hs, vs = segs(hor, 0), segs(ver, 1)
    ys = _cluster([s[0] for s in hs if s[2] - s[1] > w * 0.08], tol=max(4, h * 0.012))
    xs = _cluster([s[0] for s in vs if s[2] - s[1] > h * 0.15], tol=max(4, w * 0.008))
    if len(ys) < 3 or len(xs) < 3:
        return None
    nr, nc = len(ys) - 1, len(xs) - 1

    def has_v(c_edge: int, r: int) -> bool:  # vertical line at xs[c_edge] between ys[r]..ys[r+1]
        x = int(xs[c_edge]); y0, y1 = int(ys[r]), int(ys[r + 1])
        band = ver[y0:y1, max(0, x - 3):x + 4]
        return band.size > 0 and (band.max(1) > 0).mean() > 0.55

    def has_h(r_edge: int, c: int) -> bool:
        y = int(ys[r_edge]); x0, x1 = int(xs[c]), int(xs[c + 1])
        band = hor[max(0, y - 3):y + 4, x0:x1]
        return band.size > 0 and (band.max(0) > 0).mean() > 0.55

    parent = list(range(nr * nc))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for r in range(nr):
        for c in range(nc):
            if c + 1 < nc and not has_v(c + 1, r):
                parent[find(r * nc + c)] = find(r * nc + c + 1)
            if r + 1 < nr and not has_h(r + 1, c):
                parent[find(r * nc + c)] = find((r + 1) * nc + c)
    groups: dict[int, list[tuple[int, int]]] = {}
    for r in range(nr):
        for c in range(nc):
            groups.setdefault(find(r * nc + c), []).append((r, c))
    cells = []
    for members in groups.values():
        r0, r1 = min(m[0] for m in members), max(m[0] for m in members)
        c0, c1 = min(m[1] for m in members), max(m[1] for m in members)
        bbox = (int(xs[c0]), int(ys[r0]), int(xs[c1 + 1]), int(ys[r1 + 1]))
        lc0 = (nc - 1 - c1) if rtl else c0  # logical column index
        cells.append(Cell(r0, lc0, r1 - r0 + 1, c1 - c0 + 1, bbox))
    cells.sort(key=lambda c: (c.row, c.col))
    return cells


def mark_header_rows(cells: list[Cell], crop_bgr: np.ndarray) -> None:
    """Rows whose cells are shaded (darker background) are considered header rows."""
    g = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    paper = float(np.percentile(g, 90))
    row_shade: dict[int, list[float]] = {}
    for c in cells:
        x0, y0, x1, y1 = c.bbox
        sub = g[y0 + 4:y1 - 4, x0 + 4:x1 - 4]
        if sub.size:
            row_shade.setdefault(c.row, []).append(float(np.percentile(sub, 75)))
    hdr = {r for r, v in row_shade.items() if paper - np.median(v) > 8}
    # header rows must be a prefix
    k = 0
    while k in hdr:
        k += 1
    for c in cells:
        # a rowspan cell starting in the header is a header cell
        c.header = c.row < k


def cells_to_html(cells: list[Cell]) -> str:
    rows: dict[int, list[Cell]] = {}
    for c in cells:
        rows.setdefault(c.row, []).append(c)
    out = ["<table>"]
    for r in sorted(rows):
        out.append("<tr>")
        for c in sorted(rows[r], key=lambda c: c.col):
            tag = "th" if c.header else "td"
            attrs = (f' rowspan="{c.rowspan}"' if c.rowspan > 1 else "") + (f' colspan="{c.colspan}"' if c.colspan > 1 else "")
            out.append(f"<{tag}{attrs}>{_html.escape(c.text, quote=False)}</{tag}>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


@dataclass
class GridCell:
    row: int
    col: int
    rowspan: int
    colspan: int
    text: str
    header: bool


def parse_html_table(html: str) -> tuple[list[GridCell], int, int]:
    """Parse first <table>: resolve row/colspans into grid positions (logical order)."""
    soup = BeautifulSoup(html, "html.parser")
    t = soup.find("table")
    if t is None:
        return [], 0, 0
    occ: set[tuple[int, int]] = set()
    cells: list[GridCell] = []
    for r, tr in enumerate(t.find_all("tr")):
        c = 0
        for td in tr.find_all(["td", "th"], recursive=False):
            while (r, c) in occ:
                c += 1
            try:
                rs = max(1, int(td.get("rowspan", 1)))
                cs = max(1, int(td.get("colspan", 1)))
            except ValueError:
                rs = cs = 1
            for dr in range(rs):
                for dc in range(cs):
                    occ.add((r + dr, c + dc))
            text = td.get_text(" ", strip=True)
            cells.append(GridCell(r, c, rs, cs, text, td.name == "th"))
            c += cs
    nrows = max((r for r, _ in occ), default=-1) + 1
    ncols = max((c for _, c in occ), default=-1) + 1
    return cells, nrows, ncols


def html_text(html: str) -> str:
    cells, _, _ = parse_html_table(html)
    return " ".join(c.text for c in cells)
