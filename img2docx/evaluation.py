"""Evaluation against synthetic ground truth: CER/WER, TEDS, reading order, layout & metadata."""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from bs4 import BeautifulSoup
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from .postprocess import TASHKEEL, find_dates, find_doc_numbers, to_latin_digits
from .recognizers.base import strip_bidi_controls

TEXT_GT_TYPES = {"title", "paragraph", "list", "header", "footer", "doc_number", "date", "handwritten_note"}
IMAGE_GT_TYPES = {"stamp", "signature", "logo"}


# --------------------------------------------------------------------------- text metrics
def norm_ws(s: str) -> str:
    s = strip_bidi_controls(unicodedata.normalize("NFC", s or ""))
    return " ".join(s.split())


def strip_diacritics(s: str) -> str:
    return TASHKEEL.sub("", s).replace("ـ", "")


def cer(ref: str, hyp: str) -> float:
    ref, hyp = norm_ws(ref), norm_ws(hyp)
    if not ref:
        return 0.0 if not hyp else 1.0
    return Levenshtein.distance(ref, hyp) / len(ref)


def wer(ref: str, hyp: str) -> float:
    r, h = norm_ws(ref).split(), norm_ws(hyp).split()
    if not r:
        return 0.0 if not h else 1.0
    return Levenshtein.distance(r, h) / len(r)


def align_substring(ref: str, page_text: str) -> tuple[str, int, int]:
    """Best-matching substring of the predicted page text for a GT block (handles merges/splits)."""
    ref_n = norm_ws(ref)
    if not ref_n or not page_text:
        return "", -1, -1
    if len(ref_n) > len(page_text):
        return page_text, 0, len(page_text)
    al = fuzz.partial_ratio_alignment(ref_n, page_text)
    if al is None or al.score < 45:  # nothing similar: the block was missed (CER = 1)
        return "", -1, -1
    s, e = al.dest_start, al.dest_end
    # extend to word boundaries so a cut word counts as an error only once
    while s > 0 and not page_text[s - 1].isspace():
        s -= 1
    while e < len(page_text) and not page_text[e].isspace():
        e += 1
    return page_text[s:e], s, e


# --------------------------------------------------------------------------- TEDS
class _Node:
    __slots__ = ("label", "text", "children")

    def __init__(self, label, text="", children=None):
        self.label, self.text, self.children = label, text, children or []


def _html_tree(html: str) -> _Node:
    soup = BeautifulSoup(html or "", "html.parser")
    t = soup.find("table")
    root = _Node("table")
    if t is None:
        return root
    for tr in t.find_all("tr"):
        rn = _Node("tr")
        for td in tr.find_all(["td", "th"], recursive=False):
            label = f"td:{td.get('rowspan', '1')}:{td.get('colspan', '1')}"
            rn.children.append(_Node(label, norm_ws(td.get_text(" ", strip=True))))
        root.children.append(rn)
    return root


def _postorder(root: _Node):
    nodes, lmd = [], []

    def rec(n):
        first = None
        for c in n.children:
            l = rec(c)
            if first is None:
                first = l
        nodes.append(n)
        idx = len(nodes) - 1
        lmd.append(first if first is not None else idx)
        return lmd[idx]

    rec(root)
    return nodes, lmd


def tree_edit_distance(a: _Node, b: _Node, structure_only: bool = False) -> float:
    """Zhang–Shasha ordered tree edit distance (insert/delete 1, rename per TEDS rules)."""
    an, al = _postorder(a)
    bn, bl = _postorder(b)

    def rename(x: _Node, y: _Node) -> float:
        if x.label != y.label:
            return 1.0
        if structure_only or not x.label.startswith("td"):
            return 0.0
        if not x.text and not y.text:
            return 0.0
        return Levenshtein.normalized_distance(x.text, y.text)

    def keyroots(lmd):
        seen, kr = {}, []
        for i in range(len(lmd) - 1, -1, -1):
            if lmd[i] not in seen:
                seen[lmd[i]] = i
                kr.append(i)
        return sorted(kr)

    td = [[0.0] * len(bn) for _ in an]
    for i in keyroots(al):
        for j in keyroots(bl):
            li, lj = al[i], bl[j]
            m, n = i - li + 2, j - lj + 2
            fd = [[0.0] * n for _ in range(m)]
            for x in range(1, m):
                fd[x][0] = fd[x - 1][0] + 1
            for y in range(1, n):
                fd[0][y] = fd[0][y - 1] + 1
            for x in range(1, m):
                for y in range(1, n):
                    ii, jj = li + x - 1, lj + y - 1
                    if al[ii] == li and bl[jj] == lj:
                        fd[x][y] = min(fd[x - 1][y] + 1, fd[x][y - 1] + 1, fd[x - 1][y - 1] + rename(an[ii], bn[jj]))
                        td[ii][jj] = fd[x][y]
                    else:
                        p, q = al[ii] - li, bl[jj] - lj
                        fd[x][y] = min(fd[x - 1][y] + 1, fd[x][y - 1] + 1, fd[p][q] + td[ii][jj])
    return td[len(an) - 1][len(bn) - 1]


def teds(ref_html: str, hyp_html: str | None, structure_only: bool = False) -> float:
    a = _html_tree(ref_html)
    if not hyp_html:
        return 0.0
    b = _html_tree(hyp_html)
    na, nb = len(_postorder(a)[0]), len(_postorder(b)[0])
    return 1.0 - tree_edit_distance(a, b, structure_only) / max(na, nb, 1)


# --------------------------------------------------------------------------- reading order
def kendall_tau(seq: list[int]) -> float | None:
    """seq: predicted rank for GT items in GT order. 1 = identical order."""
    n = len(seq)
    if n < 2:
        return None
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            if seq[i] == seq[j]:
                continue
            if seq[i] < seq[j]:
                conc += 1
            else:
                disc += 1
    tot = conc + disc
    return (conc - disc) / tot if tot else None


# --------------------------------------------------------------------------- page evaluation
@dataclass
class BlockScore:
    page: str
    level: str
    page_lang: str
    type: str
    lang: str
    ref: str
    hyp: str
    cer: float
    cer_nodiac: float
    wer: float
    pred_type: str | None
    pred_order: int | None


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def evaluate_page(gt: dict, pred: dict) -> dict:
    level = gt.get("augment", {}).get("level", "?")
    blocks = sorted(pred["blocks"], key=lambda b: b["order"])
    # predicted page text with char->block map
    parts, owner = [], []
    for b in blocks:
        if b["type"] in ("table",) or not b.get("text") or b["type"] in IMAGE_GT_TYPES | {"figure"}:
            continue
        t = norm_ws(b["text"])
        if parts:
            parts.append(" "); owner.append(None)
        parts.append(t); owner.extend([b] * len(t))
    page_text = "".join(parts)
    scores: list[BlockScore] = []
    gt_text_blocks = [g for g in gt["blocks"] if g["type"] in TEXT_GT_TYPES and g.get("text")]
    for g in gt_text_blocks:
        hyp, s, e = align_substring(g["text"], page_text)
        pb = None
        if s >= 0:
            cnt = defaultdict(int)
            for o in owner[s:e]:
                if o is not None:
                    cnt[o["id"]] += 1
            if cnt:
                bid = max(cnt, key=cnt.get)
                pb = next(b for b in blocks if b["id"] == bid)
        c = cer(g["text"], hyp)
        scores.append(BlockScore(gt["id"], level, gt["lang"], g["type"], g.get("lang") or "-", norm_ws(g["text"]), hyp, c,
                                 cer(strip_diacritics(g["text"]), strip_diacritics(hyp)), wer(g["text"], hyp),
                                 pb["type"] if pb else None, pb["order"] if pb else None))
    # page-level CER over all text (order independent part is handled above; this one is order-sensitive)
    gt_page = " ".join(norm_ws(g["text"]) for g in gt_text_blocks)
    page_cer = cer(gt_page, page_text)
    # tables
    tabs = []
    pred_tables = [b for b in blocks if b["type"] == "table" and b.get("html")]
    for g in gt["blocks"]:
        if g["type"] != "table":
            continue
        best = max(pred_tables, key=lambda b: teds(g["html"], b["html"], True), default=None)
        tabs.append({"teds": teds(g["html"], best["html"]) if best else 0.0,
                     "teds_s": teds(g["html"], best["html"], True) if best else 0.0, "found": best is not None})
    # image-like element recall (bbox scaled from GT page to predicted page; approximate for photos)
    sx = pred["page"]["width_px"] / gt["width_px"]; sy = pred["page"]["height_px"] / gt["height_px"]
    img_rec = {}
    for t in IMAGE_GT_TYPES:
        gts = [g for g in gt["blocks"] if g["type"] == t]
        if not gts:
            continue
        hit = 0
        for g in gts:
            gb = [g["bbox"][0] * sx, g["bbox"][1] * sy, g["bbox"][2] * sx, g["bbox"][3] * sy]
            if any(b["type"] == t and _iou(gb, [b["bbox"][k] for k in ("x0", "y0", "x1", "y1")]) > 0.25 for b in blocks):
                hit += 1
        img_rec[t] = (hit, len(gts))
    # reading order: GT order of matched blocks vs predicted order
    seq = [s.pred_order for s in scores if s.pred_order is not None and s.type not in ("handwritten_note",)]
    tau = kendall_tau(seq)
    # metadata
    md = pred.get("metadata", {})
    gt_dates = {d.normalized for g in gt["blocks"] if g["type"] == "date" for d in find_dates(g["text"], "")}
    pr_dates = {d["normalized"] for d in md.get("dates", [])}
    gt_nos = {to_latin_digits(n["value"]) for g in gt["blocks"] if g["type"] == "doc_number" for n in find_doc_numbers(g["text"], "", True)}
    pr_nos = {n["value_latin"] for n in md.get("doc_numbers", []) if n.get("role") == "self"}
    return {
        "page": gt["id"], "level": level, "lang": gt["lang"], "blocks": scores, "page_cer": page_cer, "tables": tabs,
        "image_recall": img_rec, "kendall_tau": tau, "seconds": pred.get("timings_s", {}).get("total"),
        "dates_found": len(gt_dates & pr_dates), "dates_total": len(gt_dates),
        "docno_found": len(gt_nos & pr_nos), "docno_total": len(gt_nos),
        "needs_review": pred.get("review", {}).get("needs_review"),
        "page_score": pred.get("review", {}).get("page_score"),
    }


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")


def aggregate(results: list[dict]) -> dict:
    blocks = [b for r in results for b in r["blocks"]]
    out: dict = {}

    def group(key):
        g = defaultdict(list)
        for b in blocks:
            g[key(b)].append(b)
        # micro-averaged CER: sum of edits / sum of ref chars
        res = {}
        for k, bs in sorted(g.items()):
            n = sum(len(b.ref) for b in bs)
            res[k] = {"n": len(bs), "cer": sum(b.cer * len(b.ref) for b in bs) / max(n, 1),
                      "cer_nodiac": sum(b.cer_nodiac * len(b.ref) for b in bs) / max(n, 1),
                      "wer": _mean([b.wer for b in bs]),
                      "type_acc": _mean([1.0 if b.pred_type == b.type else 0.0 for b in bs])}
        return res

    out["by_type"] = group(lambda b: b.type)
    out["by_lang"] = group(lambda b: b.lang)
    out["by_level"] = group(lambda b: b.level)
    out["by_page_lang"] = group(lambda b: b.page_lang)
    out["by_level_lang"] = group(lambda b: f"{b.level}/{b.page_lang}")
    out["overall"] = group(lambda b: "all")["all"] if blocks else {}
    tabs = [t for r in results for t in r["tables"]]
    out["tables"] = {"n": len(tabs), "teds": _mean([t["teds"] for t in tabs]), "teds_s": _mean([t["teds_s"] for t in tabs]),
                     "found": _mean([1.0 if t["found"] else 0.0 for t in tabs])}
    tabs_lvl = defaultdict(list)
    for r in results:
        for t in r["tables"]:
            tabs_lvl[r["level"]].append(t)
    out["tables_by_level"] = {k: {"teds": _mean([t["teds"] for t in v]), "teds_s": _mean([t["teds_s"] for t in v])} for k, v in sorted(tabs_lvl.items())}
    img = defaultdict(lambda: [0, 0])
    for r in results:
        for k, (h, n) in r["image_recall"].items():
            img[k][0] += h; img[k][1] += n
    out["image_recall"] = {k: v[0] / v[1] for k, v in img.items() if v[1]}
    out["reading_order_tau"] = _mean([r["kendall_tau"] for r in results])
    out["page_cer"] = _mean([r["page_cer"] for r in results])
    out["seconds_per_page"] = _mean([r["seconds"] for r in results])
    out["dates_acc"] = sum(r["dates_found"] for r in results) / max(1, sum(r["dates_total"] for r in results))
    out["docno_acc"] = sum(r["docno_found"] for r in results) / max(1, sum(r["docno_total"] for r in results))
    out["review_rate"] = _mean([1.0 if r["needs_review"] else 0.0 for r in results])
    out["pages"] = len(results)
    return out


def markdown_report(agg: dict, results: list[dict], title: str, engines: dict | None = None) -> str:
    L = [f"# {title}", ""]
    if engines:
        L += ["Engines: " + ", ".join(f"`{k}`={v}" for k, v in engines.items()), ""]
    o = agg.get("overall", {})
    L += ["## Summary", "", "| metric | value |", "|---|---|",
          f"| pages | {agg['pages']} |",
          f"| text blocks | {o.get('n', 0)} |",
          f"| CER (micro, strict) | {o.get('cer', float('nan')):.3f} |",
          f"| CER (diacritics-insensitive) | {o.get('cer_nodiac', float('nan')):.3f} |",
          f"| WER (mean) | {o.get('wer', float('nan')):.3f} |",
          f"| page CER (order-sensitive) | {agg['page_cer']:.3f} |",
          f"| block type accuracy | {o.get('type_acc', float('nan')):.3f} |",
          f"| table TEDS / TEDS-S | {agg['tables']['teds']:.3f} / {agg['tables']['teds_s']:.3f} (n={agg['tables']['n']}) |",
          f"| reading order Kendall τ | {agg['reading_order_tau']:.3f} |",
          f"| date extraction acc | {agg['dates_acc']:.3f} |",
          f"| doc-number extraction acc | {agg['docno_acc']:.3f} |",
          f"| image element recall | " + ", ".join(f"{k} {v:.2f}" for k, v in sorted(agg['image_recall'].items())) + " |",
          f"| pages flagged needs_review | {agg['review_rate']:.2f} |",
          f"| runtime s/page (mean) | {agg['seconds_per_page']:.1f} |", ""]
    for key, name in (("by_type", "block type"), ("by_lang", "block language"), ("by_level", "degradation level"),
                      ("by_level_lang", "level / page language")):
        L += [f"## CER by {name}", "", f"| {name} | n | CER | CER no-diac | WER | type acc |", "|---|---|---|---|---|---|"]
        for k, v in agg[key].items():
            L.append(f"| {k} | {v['n']} | {v['cer']:.3f} | {v['cer_nodiac']:.3f} | {v['wer']:.3f} | {v['type_acc']:.2f} |")
        L.append("")
    L += ["## Tables by level", "", "| level | TEDS | TEDS-S |", "|---|---|---|"]
    for k, v in agg["tables_by_level"].items():
        L.append(f"| {k} | {v['teds']:.3f} | {v['teds_s']:.3f} |")
    L += ["", "## Per page", "", "| page | level | page CER | TEDS | τ | s | review | score |", "|---|---|---|---|---|---|---|---|"]
    for r in results:
        t = r["tables"][0]["teds"] if r["tables"] else float("nan")
        tau = r["kendall_tau"] if r["kendall_tau"] is not None else float("nan")
        L.append(f"| {r['page']} | {r['level']} | {r['page_cer']:.3f} | {t:.3f} | {tau:.2f} | {r['seconds'] or 0:.1f} | {r['needs_review']} | {r['page_score']} |")
    # worst blocks for debugging
    worst = sorted((b for r in results for b in r["blocks"]), key=lambda b: -b.cer)[:15]
    L += ["", "## Worst blocks", "", "| page | type | CER | ref | hyp |", "|---|---|---|---|---|"]
    for b in worst:
        esc = lambda s: s.replace("|", "\\|")[:90]
        L.append(f"| {b.page}/{b.level} | {b.type} | {b.cer:.2f} | {esc(b.ref)} | {esc(b.hyp)} |")
    return "\n".join(L) + "\n"
