"""DOCX -> PDF -> PNG via LibreOffice headless (visual verification of RTL layout)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def find_soffice() -> str | None:
    for c in (os.environ.get("SOFFICE"), shutil.which("soffice"), shutil.which("libreoffice")):
        if c and Path(c).exists():
            return c
    for p in Path.home().glob(".local/opt/libreoffice/opt/libreoffice*/program/soffice"):
        return str(p)
    return None


def docx_to_pdf(docx: str | Path, out_dir: str | Path, soffice: str | None = None, timeout: int = 180) -> Path:
    soffice = soffice or find_soffice()
    if not soffice:
        raise FileNotFoundError("LibreOffice (soffice) not found; set SOFFICE")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as profile:  # isolated profile: parallel-safe, no first-run dialogs
        cmd = [soffice, f"-env:UserInstallation=file://{profile}", "--headless", "--norestore",
               "--convert-to", "pdf", "--outdir", str(out_dir), str(docx)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
    pdf = out_dir / (Path(docx).stem + ".pdf")
    if not pdf.exists():
        raise RuntimeError(f"LibreOffice did not produce {pdf}")
    return pdf


def pdf_to_pngs(pdf: str | Path, dpi: int = 80) -> list[Path]:
    import pymupdf  # dev/eval-only dependency (AGPL) – not used by the runtime pipeline

    out = []
    with pymupdf.open(str(pdf)) as d:
        for i, page in enumerate(d):
            p = Path(pdf).with_name(f"{Path(pdf).stem}_p{i + 1}.png")
            page.get_pixmap(dpi=dpi).save(str(p))
            out.append(p)
    return out
