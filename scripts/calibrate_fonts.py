#!/usr/bin/env python
"""Fit docx.line_height_to_pt (per script) from synthetic GT font sizes vs measured line heights.

  python scripts/calibrate_fonts.py data/synth reports/eval_dev-cpu_v1_pred
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from img2docx.evaluation import evaluate_page  # noqa: E402

data, pred_dir = Path(sys.argv[1]), Path(sys.argv[2])
ratios = {"ar": [], "en": []}
for gp in sorted(data.glob("*.gt.json")):
    pj = pred_dir / gp.name.replace(".gt.json", ".json")
    if not pj.exists():
        continue
    gt, pred = json.loads(gp.read_text()), json.loads(pj.read_text())
    by_order = {b["order"]: b for b in pred["blocks"]}
    px_per_mm = pred["page"]["width_px"] / pred["page"]["width_mm"]
    r = evaluate_page(gt, pred)
    gts = [g for g in gt["blocks"] if g["type"] in ("paragraph", "title", "doc_number", "date") and g.get("text")]
    for g, s in zip([g for g in gt["blocks"] if g.get("text") and g["type"] in
                     {"title", "paragraph", "list", "header", "footer", "doc_number", "date", "handwritten_note"}], r["blocks"]):
        if g["type"] not in ("paragraph", "title", "doc_number", "date") or s.cer > 0.2 or s.pred_order is None:
            continue
        pb = by_order.get(s.pred_order)
        if not pb or not pb.get("line_height_px") or not g.get("size_pt"):
            continue
        ink_pt = pb["line_height_px"] / px_per_mm * 2.83465
        ratios["en" if g["lang"] == "en" else "ar"].append(g["size_pt"] / ink_pt)
for k, v in ratios.items():
    if v:
        print(f"{k}: n={len(v)} median factor={statistics.median(v):.3f}  p25={statistics.quantiles(v, n=4)[0]:.3f} p75={statistics.quantiles(v, n=4)[2]:.3f}")
