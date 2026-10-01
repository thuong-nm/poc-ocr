#!/usr/bin/env python
"""Generate synthetic Arabic/English/mixed official letters + ground truth.

Usage: python scripts/gen_synthetic.py -o data/synth -n 3 --levels clean mild hard
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from img2docx.synthetic import generate_dataset  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="data/synth")
    ap.add_argument("-n", "--per-lang", type=int, default=3)
    ap.add_argument("--levels", nargs="+", default=["clean", "mild", "hard"])
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    paths = generate_dataset(Path(a.out), a.per_lang, tuple(a.levels), a.seed)
    print(f"wrote {len(paths)} images to {a.out}")


if __name__ == "__main__":
    main()
