#!/usr/bin/env python
"""Run the pipeline on a synthetic dataset and write a markdown report.

  python scripts/evaluate.py data/synth -o reports/eval_dev-cpu.md [--config cfg.yaml] [--profile dev-vlm]
  python scripts/evaluate.py data/synth --pred-dir out/eval   # re-score existing predictions only
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from img2docx.evaluation import aggregate, evaluate_page, markdown_report  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("-o", "--report", default="reports/eval.md")
    ap.add_argument("--pred-dir", default=None, help="where predictions are written/read (default: <report>_pred/)")
    ap.add_argument("--config")
    ap.add_argument("--profile")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--filter", default="", help="substring filter on file names")
    ap.add_argument("--rescore", action="store_true", help="do not run the pipeline, only score existing predictions")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    data = Path(a.data_dir)
    gts = sorted(p for p in data.glob("*.gt.json") if a.filter in p.name)[: a.limit]
    report = Path(a.report)
    pred_dir = Path(a.pred_dir) if a.pred_dir else report.with_name(report.stem + "_pred")
    pred_dir.mkdir(parents=True, exist_ok=True)
    pipe = None
    if not a.rescore:
        from img2docx.config import load_config
        from img2docx.pipeline import Pipeline

        cfg = load_config(a.config, a.profile)
        pipe = Pipeline(cfg)
    results, engines = [], {}
    t0 = time.time()
    for i, gp in enumerate(gts):
        gt = json.loads(gp.read_text(encoding="utf-8"))
        stem = gp.name.replace(".gt.json", "")
        pj = pred_dir / f"{stem}.json"
        if pipe is not None:
            res = pipe.convert(data / gt["image"], pred_dir / f"{stem}.docx", pj)
            engines = res.document.engines
        pred = json.loads(pj.read_text(encoding="utf-8"))
        engines = engines or pred.get("engines", {})
        r = evaluate_page(gt, pred)
        results.append(r)
        print(f"[{i + 1}/{len(gts)}] {stem}: page CER {r['page_cer']:.3f}  "
              f"TEDS {r['tables'][0]['teds'] if r['tables'] else float('nan'):.3f}  {r['seconds'] or 0:.1f}s", flush=True)
    agg = aggregate(results)
    title = f"img2docx evaluation — {a.profile or (a.config or 'default config')} — {len(results)} pages"
    md = markdown_report(agg, results, title, engines)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(md, encoding="utf-8")
    report.with_suffix(".json").write_text(json.dumps(agg, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(md.split("## CER by block language")[0])
    print(f"report: {report}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
