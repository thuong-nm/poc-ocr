"""End-to-end on synthetic pages (CPU only: Tesseract + PaddleOCR + PP-DocLayout)."""
import json

import cv2
import pytest

from img2docx.config import load_config
from img2docx.evaluation import evaluate_page
from img2docx.synthetic import augment, make_page

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def pipe():
    from img2docx.pipeline import Pipeline

    # secondary engine off to keep the suite fast; layout model on (CPU)
    return Pipeline(load_config(profile="dev-cpu", overrides={"recognition": {"secondary": "none"}}))


@pytest.mark.parametrize("lang,level", [("ar", "mild"), ("en", "hard")])
def test_e2e_cer_and_structure(tmp_path, pipe, lang, level):
    from dataclasses import asdict

    page, gt = make_page(31 if lang == "ar" else 32, lang)
    img, info = augment(page, level, 9)
    p = tmp_path / "in.jpg"
    cv2.imwrite(str(p), img)
    res = pipe.convert(p, tmp_path / "out.docx", debug_dir=tmp_path / "dbg")
    assert res.docx_path.exists() and res.json_path.exists()
    pred = json.loads(res.json_path.read_text(encoding="utf-8"))
    g = asdict(gt)
    g["augment"] = info
    r = evaluate_page(g, pred)
    assert pred["page"]["direction"] == ("rtl" if lang == "ar" else "ltr")
    assert r["page_cer"] < 0.35
    body = [b for b in r["blocks"] if b.type == "paragraph"]
    assert sum(b.cer for b in body) / len(body) < 0.15
    assert r["tables"] and r["tables"][0]["teds_s"] > 0.9
    assert r["docno_found"] == r["docno_total"] == 1
    # debug dir has every stage
    for f in ("00_input.jpg", "01_geometry.jpg", "02_illumination.jpg", "03_layout_raw.jpg", "04_layout_final.jpg", "ir.json"):
        assert (tmp_path / "dbg" / f).exists()


def test_cli_batch(tmp_path):
    from img2docx.cli import main

    page, gt = make_page(33, "mixed", with_table=False)
    for i in range(2):
        img, _ = augment(page, "clean", i)
        cv2.imwrite(str(tmp_path / f"p{i}.jpg"), img)
    rc = main(["batch", str(tmp_path), "-o", str(tmp_path / "out"), "--workers", "2", "--profile", "dev-cpu"])
    assert rc == 0
    rep = json.loads((tmp_path / "out" / "batch_report.json").read_text())
    assert rep["ok"] == 2 and rep["pages_per_s"] > 0


def test_api_convert(tmp_path, monkeypatch):
    import io
    import zipfile

    from fastapi.testclient import TestClient

    from img2docx import api
    from img2docx.pipeline import Pipeline

    api._pipe = Pipeline(load_config(profile="dev-cpu", overrides={"recognition": {"secondary": "none"}}))
    client = TestClient(api.app)
    assert client.get("/health").json() == {"status": "ok"}
    page, _ = make_page(34, "en", with_table=False, with_stamp=False)
    img, _ = augment(page, "clean", 0)
    ok, buf = cv2.imencode(".jpg", img)
    r = client.post("/convert", files={"file": ("p.jpg", buf.tobytes(), "image/jpeg")})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "result.docx" in names and "result.json" in names
    r = client.post("/convert?format=json", files={"file": ("p.jpg", buf.tobytes(), "image/jpeg")})
    assert r.json()["schema_version"] == "1.0.0" and r.json()["page"]["direction"] == "ltr"
    assert client.post("/convert", files={"file": ("e.jpg", b"", "image/jpeg")}).status_code == 400
