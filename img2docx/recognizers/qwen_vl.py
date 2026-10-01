"""Qwen3-VL recognizer.

Backends:
  * ``openai``       – any OpenAI-compatible server: vLLM (`vllm serve Qwen/Qwen3-VL-8B-Instruct`),
                       llama.cpp `llama-server` (GGUF + mmproj), or Ollama (`/v1`). All three are local.
  * ``transformers`` – in-process HF transformers (`Qwen3VLForConditionalGeneration`), optional PEFT LoRA.

LoRA: ``vlm.adapters`` maps region type (or "printed"/"handwritten") -> adapter. With vLLM the adapter
is selected by sending its --lora-modules *name* as the request ``model``; with transformers it is a
PEFT directory loaded once and activated per request.
"""
from __future__ import annotations

import base64
import logging
import math
import re
import time

import cv2
import numpy as np

from ..config import VlmCfg
from .base import UNREADABLE, RecognitionResult, Recognizer, RegionHints, strip_bidi_controls

log = logging.getLogger(__name__)

_RULES = (
    "Rules: copy the text exactly as written in the image. Do not translate, correct, normalize, "
    "summarize or complete anything. Keep the original language and script (Arabic and/or English). "
    "Keep every digit in its original form: Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩) stay Arabic-Indic, "
    "Latin digits (0123456789) stay Latin. Keep diacritics (tashkeel) only if they are visible. "
    "Keep line breaks. If a word cannot be read, write " + UNREADABLE + " instead of guessing."
)

PROMPTS = {
    "text": "Transcribe the text in this image. " + _RULES + " Output only the transcription.",
    "handwritten_note": "This image contains handwritten text. Transcribe it. " + _RULES + " Output only the transcription.",
    "table": (
        "Convert this table to HTML. Use only <table>, <tr>, <th>, <td>. Use rowspan and colspan for merged cells. "
        "Within each row list cells in reading order (for Arabic right-to-left tables the rightmost cell comes first). "
        "Use <th> for header cells. " + _RULES + " Output only the HTML table."
    ),
    "stamp": "Read the text printed on this stamp/seal. " + _RULES + " Output only the text.",
}


def prompt_for(region_type: str) -> str:
    if region_type in PROMPTS:
        return PROMPTS[region_type]
    return PROMPTS["text"]


def max_tokens_for(crop_shape, region_type: str, cfg: VlmCfg, line_h: float | None) -> int:
    """Budget proportional to the region's text capacity (area / line height²) – curbs hallucination."""
    h, w = crop_shape[:2]
    lh = line_h or max(12.0, min(h, 60.0))
    n_lines = max(1.0, h / (lh * 1.25))
    chars_per_line = max(4.0, w / (lh * 0.45))
    est = n_lines * chars_per_line * 0.55 * cfg.tokens_per_line_factor  # ~0.55 tokens/char for ar/en BPE
    if region_type == "table":
        est *= 3.0  # HTML markup overhead
    return int(np.clip(est + 16, cfg.max_tokens_min, cfg.max_tokens_max))


def clean_output(raw: str, region_type: str) -> tuple[str, list[str]]:
    flags = []
    s = raw.strip()
    s = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", s).strip()
    if region_type == "table":
        m = re.search(r"<table.*?</table>", s, flags=re.S | re.I)
        if m:
            s = sanitize_table_html(m.group(0))
        else:
            flags.append("no_html_table")
    s = strip_bidi_controls(s)
    # repetition loop guard: same >=6-char chunk repeated 4+ times in a row
    m = re.search(r"(.{6,40}?)(?:\s*\1){3,}", s, flags=re.S)
    if m:
        s = s[: m.start()] + m.group(1)
        flags.append("repetition_truncated")
    return s, flags


def sanitize_table_html(html: str) -> str:
    """Keep only table/tr/th/td and rowspan/colspan (models add style, data-bbox, thead, ...)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    t = soup.find("table")
    out = ["<table>"]
    for tr in t.find_all("tr"):
        out.append("<tr>")
        for td in tr.find_all(["td", "th"], recursive=False):
            attrs = ""
            for k in ("rowspan", "colspan"):
                v = td.get(k)
                if v and str(v).isdigit() and int(v) > 1:
                    attrs += f' {k}="{int(v)}"'
            text = td.get_text(" ", strip=True).replace("&", "&amp;").replace("<", "&lt;")
            out.append(f"<{td.name}{attrs}>{text}</{td.name}>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def encode_crop(crop: np.ndarray, max_side: int) -> str:
    h, w = crop.shape[:2]
    s = min(1.0, max_side / max(h, w))
    if s < 1:
        crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    # tiny crops (single words) are upscaled; VLM patching is 16-32px
    if min(crop.shape[:2]) < 48:
        f = 48 / min(crop.shape[:2])
        crop = cv2.resize(crop, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    ok, buf = cv2.imencode(".png", crop)
    return base64.b64encode(buf.tobytes()).decode()


def _confidence_from_logprobs(lps: list[float] | None) -> float | None:
    if not lps:
        return None
    lps = np.asarray(lps, dtype=np.float64)
    mean_p = float(np.exp(lps.mean()))
    # penalize a few very uncertain tokens (often the misread characters)
    low = float(np.mean(lps < math.log(0.5)))
    return max(0.0, min(1.0, mean_p - 0.5 * low))


class _VLMBase(Recognizer):
    def __init__(self, cfg: VlmCfg):
        self.cfg = cfg

    def adapter_for(self, region_type: str) -> str | None:
        a = self.cfg.adapters
        if region_type in a:
            return a[region_type]
        kind = "handwritten" if region_type == "handwritten_note" else "printed"
        return a.get(kind)

    def recognize(self, crop: np.ndarray, region_type: str, hints: RegionHints | None = None) -> RecognitionResult:
        hints = hints or RegionHints()
        t = time.time()
        mt = hints.max_tokens or max_tokens_for(crop.shape, region_type, self.cfg, hints.line_height_px)
        raw, lps, finish = self._generate(crop, prompt_for(region_type), mt, self.adapter_for(region_type))
        text, flags = clean_output(raw, region_type)
        if finish == "length":
            flags.append("truncated_max_tokens")
        conf = _confidence_from_logprobs(lps)
        if conf is None:
            conf = 0.7  # server returned no logprobs; neutral prior, agreement decides
            flags.append("no_logprobs")
        if flags:
            conf *= 0.7
        r = RecognitionResult(engine=self.engine_id, token_logprobs=lps, confidence=conf, flags=flags, raw=raw,
                              seconds=time.time() - t)
        if region_type == "table" and "no_html_table" not in flags:
            r.html = text
        else:
            r.text = text
        return r

    def _generate(self, crop, prompt, max_tokens, adapter) -> tuple[str, list[float] | None, str | None]:
        raise NotImplementedError


class OpenAICompatVLM(_VLMBase):
    """vLLM / llama.cpp / Ollama via /v1/chat/completions (local HTTP only)."""

    name = "vlm-openai"

    def __init__(self, cfg: VlmCfg):
        super().__init__(cfg)
        import httpx

        self.client = httpx.Client(base_url=cfg.base_url.rstrip("/"), timeout=cfg.timeout_s,
                                   headers={"Authorization": f"Bearer {cfg.api_key}"})

    @property
    def engine_id(self) -> str:
        return f"qwen3-vl[{self.cfg.model}]@{self.cfg.base_url}"

    def health(self) -> bool:
        try:
            return self.client.get("/models", timeout=5).status_code == 200
        except Exception:
            return False

    def _generate(self, crop, prompt, max_tokens, adapter):
        b64 = encode_crop(crop, self.cfg.max_image_side)
        body = {
            "model": adapter or self.cfg.model,
            "temperature": self.cfg.temperature,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]}],
        }
        if self.cfg.request_logprobs:
            body["logprobs"] = True
            body["top_logprobs"] = 1
        r = self.client.post("/chat/completions", json=body)
        if r.status_code >= 400 and self.cfg.request_logprobs:
            # some servers reject logprobs for multimodal requests -> retry without
            body.pop("logprobs", None); body.pop("top_logprobs", None)
            r = self.client.post("/chat/completions", json=body)
        r.raise_for_status()
        ch = r.json()["choices"][0]
        text = ch["message"].get("content") or ""
        lps = None
        lp = ch.get("logprobs")
        if lp and lp.get("content"):
            lps = [float(t["logprob"]) for t in lp["content"] if t.get("logprob") is not None]
        return text, lps, ch.get("finish_reason")

    def close(self):
        self.client.close()


class TransformersVLM(_VLMBase):
    """In-process Qwen3-VL via transformers (GPU server without vLLM, or CPU for tests)."""

    name = "vlm-transformers"

    def __init__(self, cfg: VlmCfg, device: str = "cuda"):
        super().__init__(cfg)
        import torch
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

        dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32, "auto": "auto"}[cfg.dtype]
        if device == "cpu" and dtype == torch.float16:
            dtype = torch.float32
        kw = {"dtype": dtype}
        if cfg.load_in_4bit:
            from transformers import BitsAndBytesConfig

            kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16)
        self.torch = torch
        self.model = Qwen3VLForConditionalGeneration.from_pretrained(cfg.model_path, device_map=device, **kw)
        self.processor = AutoProcessor.from_pretrained(cfg.model_path)
        self._adapters: set[str] = set()
        if cfg.adapters:
            from peft import PeftModel

            for path in sorted(set(cfg.adapters.values())):  # adapter name == its path
                if not isinstance(self.model, PeftModel):
                    self.model = PeftModel.from_pretrained(self.model, path, adapter_name=path)
                else:
                    self.model.load_adapter(path, adapter_name=path)
                self._adapters.add(path)
        self.model.eval()

    @property
    def engine_id(self) -> str:
        return f"qwen3-vl[{self.cfg.model_path}]@transformers"

    def _generate(self, crop, prompt, max_tokens, adapter):
        from PIL import Image

        torch = self.torch
        h, w = crop.shape[:2]
        s = min(1.0, self.cfg.max_image_side / max(h, w))
        if s < 1:
            crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        img = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        messages = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": prompt}]}]
        inputs = self.processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                    return_dict=True, return_tensors="pt").to(self.model.device)
        ctx = None
        if self._adapters:
            if adapter in self._adapters:
                self.model.set_adapter(adapter)
            else:
                ctx = self.model.disable_adapter()
        with torch.inference_mode():
            if ctx is not None:
                with ctx:
                    out = self._gen(inputs, max_tokens)
            else:
                out = self._gen(inputs, max_tokens)
        seq = out.sequences[0, inputs["input_ids"].shape[1]:]
        lps = []
        for step, tok in enumerate(seq.tolist()):
            if step >= len(out.scores):
                break
            lp = torch.log_softmax(out.scores[step][0].float(), dim=-1)[tok].item()
            lps.append(lp)
        eos = self.processor.tokenizer.eos_token_id
        finish = "length" if len(seq) >= max_tokens and (len(seq) == 0 or seq[-1].item() != eos) else "stop"
        text = self.processor.decode(seq, skip_special_tokens=True, clean_up_tokenization_spaces=False)
        return text, lps, finish

    def _gen(self, inputs, max_tokens):
        return self.model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False,
                                   output_scores=True, return_dict_in_generate=True)


def build_vlm(cfg: VlmCfg, device: str = "cpu") -> _VLMBase:
    if cfg.backend == "openai":
        return OpenAICompatVLM(cfg)
    return TransformersVLM(cfg, device="cuda" if device == "cuda" else "cpu")
