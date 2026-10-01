"""Command line interface.

  img2docx input.jpg -o output.docx [--json out.json] [--debug-dir dbg/] [--config config.yaml] [--profile P]
  img2docx batch input_dir/ -o out_dir/ [--workers N] [--config config.yaml]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".bmp", ".webp"}


def _common(ap: argparse.ArgumentParser):
    ap.add_argument("--config", help="config.yaml")
    ap.add_argument("--profile", help="dev-cpu | dev-vlm | gpu-server (overrides config)")
    ap.add_argument("-v", "--verbose", action="count", default=0)


def _logging(v: int):
    level = logging.WARNING if v == 0 else (logging.INFO if v == 1 else logging.DEBUG)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("ppocr", "paddlex", "paddle", "httpx", "PIL"):
        logging.getLogger(noisy).setLevel(logging.ERROR)


def cmd_convert(argv):
    ap = argparse.ArgumentParser(prog="img2docx", description="Photo of a document -> editable DOCX (+ JSON IR)")
    ap.add_argument("input")
    ap.add_argument("-o", "--output", help="output .docx (default: next to input)")
    ap.add_argument("--json", help="output IR .json (default: next to .docx)")
    ap.add_argument("--debug-dir", help="save every intermediate stage here")
    _common(ap)
    a = ap.parse_args(argv)
    _logging(a.verbose or 1)
    from .config import load_config
    from .pipeline import Pipeline

    cfg = load_config(a.config, a.profile)
    res = Pipeline(cfg).convert(a.input, a.output, a.json, a.debug_dir)
    rv = res.document.review
    summary = {"docx": str(res.docx_path), "json": str(res.json_path), "needs_review": rv.needs_review,
               "page_score": rv.page_score, "reasons": rv.reasons, "warnings": res.warnings, "timings_s": res.timings_s}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


_WORKER = None


def _init_worker(cfg_path, profile, verbose):
    global _WORKER
    _logging(verbose)
    from .config import load_config
    from .pipeline import Pipeline

    _WORKER = Pipeline(load_config(cfg_path, profile))


def _work(img: str, out_dir: str):
    t = time.perf_counter()
    stem = Path(img).stem
    try:
        r = _WORKER.convert(img, Path(out_dir) / f"{stem}.docx", Path(out_dir) / f"{stem}.json")
        return {"input": img, "ok": True, "needs_review": r.document.review.needs_review,
                "page_score": r.document.review.page_score, "seconds": time.perf_counter() - t}
    except Exception as e:  # never silently fail: report per file
        logging.getLogger("img2docx").exception("failed on %s", img)
        return {"input": img, "ok": False, "error": f"{type(e).__name__}: {e}", "seconds": time.perf_counter() - t}


def cmd_batch(argv):
    ap = argparse.ArgumentParser(prog="img2docx batch")
    ap.add_argument("input_dir")
    ap.add_argument("-o", "--output", required=True, help="output directory")
    ap.add_argument("--workers", type=int, default=1)
    _common(ap)
    a = ap.parse_args(argv)
    _logging(a.verbose)
    imgs = sorted(str(p) for p in Path(a.input_dir).rglob("*") if p.suffix.lower() in IMAGE_EXT)
    if not imgs:
        print(f"no images found in {a.input_dir}", file=sys.stderr)
        return 2
    Path(a.output).mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    results = []
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_init_worker,
                             initargs=(a.config, a.profile, a.verbose)) as ex:
        futs = [ex.submit(_work, i, a.output) for i in imgs]
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            status = "OK " if r["ok"] else "ERR"
            extra = f"review={r.get('needs_review')} score={r.get('page_score')}" if r["ok"] else r["error"]
            print(f"[{len(results)}/{len(imgs)}] {status} {Path(r['input']).name} {r['seconds']:.1f}s {extra}", flush=True)
    wall = time.perf_counter() - t0
    ok = sum(r["ok"] for r in results)
    report = {"pages": len(imgs), "ok": ok, "failed": len(imgs) - ok, "wall_s": round(wall, 2),
              "pages_per_s": round(len(imgs) / wall, 4), "needs_review": sum(1 for r in results if r.get("needs_review")),
              "results": sorted(results, key=lambda r: r["input"])}
    (Path(a.output) / "batch_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: {ok}/{len(imgs)} ok, {report['pages_per_s']} pages/s ({wall:.1f}s wall, {a.workers} workers)")
    return 0 if ok == len(imgs) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "batch":
        return cmd_batch(argv[1:])
    if argv and argv[0] == "serve":
        from .api import serve

        return serve(argv[1:])
    return cmd_convert(argv)


if __name__ == "__main__":
    sys.exit(main())
