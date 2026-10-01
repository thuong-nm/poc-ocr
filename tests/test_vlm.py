"""VLM backend tests. Unit parts always run; live parts need a local OpenAI-compatible server."""
import numpy as np
import pytest

from img2docx.config import VlmCfg
from img2docx.recognizers.qwen_vl import OpenAICompatVLM, clean_output, max_tokens_for, prompt_for


def test_max_tokens_scales_with_area():
    cfg = VlmCfg()
    small = max_tokens_for((50, 300), "paragraph", cfg, 40)
    big = max_tokens_for((400, 1400), "paragraph", cfg, 40)
    table = max_tokens_for((400, 1400), "table", cfg, 40)
    assert cfg.max_tokens_min <= small < big < table <= cfg.max_tokens_max


def test_clean_output_strips_fences_and_loops():
    s, f = clean_output("```html\n<table><tr><td>a</td></tr></table>\n```", "table")
    assert s == "<table><tr><td>a</td></tr></table>" and not f
    s, f = clean_output("نص " + "مكرر جدا " * 10, "paragraph")
    assert "repetition_truncated" in f and s.count("مكرر") <= 2


def test_prompts_forbid_correction_and_keep_digits():
    p = prompt_for("paragraph")
    assert "Do not translate, correct" in p and "Arabic-Indic" in p and "[؟]" in p
    assert "rowspan" in prompt_for("table")


def test_lora_adapter_routing():
    cfg = VlmCfg(adapters={"printed": "lora-printed", "handwritten": "lora-hw", "table": "lora-table"})
    r = OpenAICompatVLM(cfg)
    assert r.adapter_for("paragraph") == "lora-printed"
    assert r.adapter_for("handwritten_note") == "lora-hw"
    assert r.adapter_for("table") == "lora-table"
    assert OpenAICompatVLM(VlmCfg()).adapter_for("paragraph") is None


def _live_number_crop():
    import random

    import cv2
    from PIL import Image, ImageDraw

    from img2docx.synthetic import Renderer

    r = Renderer(random.Random(0))
    img = Image.new("RGB", (900, 90), (250, 250, 250))
    r.draw_line(ImageDraw.Draw(img), 880, 15, "الرقم: ٤/٣٢٤١", r.font("Amiri-Regular.ttf", 16), (10, 10, 10), "r")
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


@pytest.fixture(scope="module")
def live_vlm():
    rec = OpenAICompatVLM(VlmCfg())
    if not rec.health():
        pytest.skip("no local VLM server")
    return rec


@pytest.mark.vlm
def test_live_vlm_keeps_digit_form_and_logprobs(live_vlm):
    res = live_vlm.recognize(_live_number_crop(), "doc_number")
    digits = [c for c in res.text if c.isdigit()]
    assert digits and all("\u0660" <= c <= "\u0669" for c in digits)  # no conversion to Latin digits
    assert res.text.startswith("الرقم")
    assert res.token_logprobs and 0 < res.confidence <= 1


@pytest.mark.vlm
@pytest.mark.xfail(reason="Qwen3-VL-2B Q4 misreads/reorders Arabic-Indic numbers (observed '١٣٢٣/٣'); "
                          "8B on the GPU server or the Tesseract cross-check is needed", strict=False)
def test_live_vlm_exact_arabic_indic_number(live_vlm):
    res = live_vlm.recognize(_live_number_crop(), "doc_number")
    assert "٤/٣٢٤١" in res.text

