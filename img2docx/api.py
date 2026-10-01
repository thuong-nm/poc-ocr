"""Minimal FastAPI service for ECM integration.

POST /convert (multipart file=<image>)  -> application/zip containing result.docx + result.json
POST /convert?format=json               -> IR JSON only
GET  /health
Run: img2docx serve --host 0.0.0.0 --port 8080 [--config config.yaml]
"""
from __future__ import annotations

import argparse
import io
import os
import tempfile
import threading
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from .config import load_config
from .pipeline import Pipeline

MAX_UPLOAD = 40 * 1024 * 1024
app = FastAPI(title="img2docx", version="1.0.0")
_pipe: Pipeline | None = None
_lock = threading.Lock()  # models are not re-entrant; one conversion at a time per process


def get_pipeline() -> Pipeline:
    global _pipe
    if _pipe is None:
        _pipe = Pipeline(load_config(os.environ.get("IMG2DOCX_CONFIG"), os.environ.get("IMG2DOCX_PROFILE")))
    return _pipe


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/convert")
async def convert_endpoint(file: UploadFile = File(...), format: str = Query("zip", pattern="^(zip|json)$")):
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file too large")
    suffix = Path(file.filename or "upload.jpg").suffix.lower() or ".jpg"
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / f"input{suffix}"
        src.write_bytes(data)
        out = Path(td) / "result.docx"
        try:
            with _lock:
                res = get_pipeline().convert(src, out, Path(td) / "result.json")
        except Exception as e:
            raise HTTPException(422, f"conversion failed: {type(e).__name__}: {e}")
        if format == "json":
            return JSONResponse(content=res.document.model_dump(mode="json"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in Path(td).rglob("*"):
                if p.is_file() and p != src:
                    z.write(p, p.relative_to(td))
        headers = {"Content-Disposition": 'attachment; filename="result.zip"',
                   "X-Needs-Review": str(res.document.review.needs_review).lower(),
                   "X-Page-Score": f"{res.document.review.page_score:.3f}"}
        return Response(buf.getvalue(), media_type="application/zip", headers=headers)


def serve(argv=None):
    import uvicorn

    ap = argparse.ArgumentParser(prog="img2docx serve")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--config")
    ap.add_argument("--profile")
    a = ap.parse_args(argv)
    if a.config:
        os.environ["IMG2DOCX_CONFIG"] = a.config
    if a.profile:
        os.environ["IMG2DOCX_PROFILE"] = a.profile
    uvicorn.run(app, host=a.host, port=a.port, workers=1)
    return 0
