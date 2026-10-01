"""Configuration (pydantic) loaded from YAML. All model paths/IDs live here."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class GeometryCfg(BaseModel):
    detect_boundary: bool = True
    min_doc_area_ratio: float = 0.20      # quad must cover >= this fraction of the photo
    dewarp: Literal["none", "uvdoc"] = "none"
    orientation: Literal["paddle", "tesseract", "heuristic", "none"] = "paddle"
    deskew: bool = True
    max_deskew_deg: float = 8.0
    target_long_side_px: int = 2400       # normalized page resolution (≈ 200 dpi for A4)


class IlluminationCfg(BaseModel):
    enabled: bool = True
    kernel_frac: float = 0.035            # background-estimation kernel ~ fraction of page width


class QACfg(BaseModel):
    min_blur_var: float = 60.0
    min_long_side_px: int = 1500
    max_glare_ratio: float = 0.02
    min_coverage: float = 0.25


class LayoutCfg(BaseModel):
    backend: Literal["paddle", "heuristic"] = "paddle"
    model_name: str = "PP-DocLayout_plus-L"
    model_dir: str | None = None          # local dir (offline); None = PaddleX cache
    threshold: float = 0.35
    fill_uncovered_text: bool = True       # classical line detection adds regions the model missed
    detect_ink_colors: bool = True         # stamp / signature / handwriting heuristics


class TesseractCfg(BaseModel):
    cmd: str | None = None                # path to binary; None = PATH / env TESSERACT_CMD
    tessdata_dir: str | None = None
    langs: str = "ara+eng"
    psm_block: int = 6
    psm_line: int = 7
    unreadable_word_conf: float = 15.0    # words below this conf -> "[؟]"


class PaddleOcrCfg(BaseModel):
    rec_model_ar: str = "arabic_PP-OCRv5_mobile_rec"
    rec_model_en: str = "en_PP-OCRv5_mobile_rec"
    model_root: str | None = None         # dir containing <model_name>/ subdirs (offline)
    enable_mkldnn: bool = False           # paddle 3.3 oneDNN bug with these models (see PLAN.md)


class VlmCfg(BaseModel):
    backend: Literal["openai", "transformers"] = "openai"
    # openai-compatible server: vLLM (`vllm serve`), llama.cpp `llama-server`, or Ollama (/v1)
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "EMPTY"
    model: str = "qwen3-vl:2b-instruct-q4_K_M"
    # transformers backend
    model_path: str = "Qwen/Qwen3-VL-2B-Instruct"
    dtype: Literal["float16", "bfloat16", "float32", "auto"] = "float16"
    load_in_4bit: bool = False
    # LoRA: region_type -> adapter. For vLLM: the --lora-modules *name*; for transformers: a PEFT dir.
    adapters: dict[str, str] = Field(default_factory=dict)
    timeout_s: float = 300.0
    temperature: float = 0.0
    max_tokens_min: int = 32
    max_tokens_max: int = 2048
    tokens_per_line_factor: float = 1.6    # tokens ≈ factor * chars_per_line_estimate * n_lines
    max_image_side: int = 1280            # crop resized before upload
    request_logprobs: bool = True


class RecognitionCfg(BaseModel):
    primary: Literal["tesseract", "paddle", "vlm"] = "tesseract"
    secondary: Literal["tesseract", "paddle", "vlm", "none"] = "paddle"
    # per-region-type override of the primary engine, e.g. {"table": "vlm", "handwritten_note": "vlm"}
    primary_by_type: dict[str, str] = Field(default_factory=dict)
    ocr_stamps_to_metadata: bool = True
    numeric_prefer_classic: bool = True    # digit-heavy lines: confident Tesseract beats a (small) VLM
    tesseract: TesseractCfg = Field(default_factory=TesseractCfg)
    paddle: PaddleOcrCfg = Field(default_factory=PaddleOcrCfg)
    vlm: VlmCfg = Field(default_factory=VlmCfg)


class ConfidenceCfg(BaseModel):
    w_engine: float = 0.6
    w_agreement: float = 0.4
    handwritten_penalty: float = 0.15
    block_review_threshold: float = 0.75
    page_review_threshold: float = 0.85
    agreement_ignore_digits_for: list[str] = Field(default_factory=lambda: ["paddle"])


class DocxCfg(BaseModel):
    font_cs: str = "Simplified Arabic"    # complex-script (Arabic) font
    font_latin: str = "Arial"
    font_fallback: str = "Arial"
    default_size_pt: float = 13.0
    min_size_pt: float = 8.0
    max_size_pt: float = 28.0
    highlight_low_confidence: bool = False
    comment_low_confidence: bool = False
    low_confidence_threshold: float = 0.75
    insert_images: bool = True
    stamp_floating: bool = True           # anchor stamps behind text at their relative position
    font_size_from_line_height: bool = True
    # pt = measured line ink height (pt) * factor; fitted with scripts/calibrate_fonts.py on the synthetic set
    line_height_to_pt_ar: float = 0.86
    line_height_to_pt_latin: float = 1.0


class RuntimeCfg(BaseModel):
    device: Literal["auto", "cpu", "cuda"] = "auto"
    max_image_side: int = 5000
    paddlex_cache: str | None = None      # sets PADDLE_PDX_CACHE_HOME
    offline: bool = True                  # forbid model downloads at runtime


class Config(BaseModel):
    profile: str = "dev-cpu"
    runtime: RuntimeCfg = Field(default_factory=RuntimeCfg)
    qa: QACfg = Field(default_factory=QACfg)
    geometry: GeometryCfg = Field(default_factory=GeometryCfg)
    illumination: IlluminationCfg = Field(default_factory=IlluminationCfg)
    layout: LayoutCfg = Field(default_factory=LayoutCfg)
    recognition: RecognitionCfg = Field(default_factory=RecognitionCfg)
    confidence: ConfidenceCfg = Field(default_factory=ConfidenceCfg)
    docx: DocxCfg = Field(default_factory=DocxCfg)

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()[:12]


PROFILES: dict[str, dict] = {
    # Classic engines only. Runs anywhere (CPU).
    "dev-cpu": {},
    # 4 GB GPU dev box: Qwen3-VL-2B (Ollama) as primary, Tesseract as cross-check.
    "dev-vlm": {
        "recognition": {"primary": "vlm", "secondary": "tesseract",
                        "vlm": {"backend": "openai", "base_url": "http://localhost:11434/v1",
                                "model": "qwen3-vl:2b-instruct-q4_K_M"}},
    },
    # GPU server: vLLM serving Qwen3-VL-8B-Instruct, PaddleOCR as cross-check.
    "gpu-server": {
        "runtime": {"device": "cuda"},
        "geometry": {"dewarp": "uvdoc"},
        "recognition": {"primary": "vlm", "secondary": "paddle",
                        "vlm": {"backend": "openai", "base_url": "http://localhost:8000/v1",
                                "model": "Qwen/Qwen3-VL-8B-Instruct", "max_image_side": 1600}},
    },
}


def _deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path: str | os.PathLike | None = None, profile: str | None = None, overrides: dict | None = None) -> Config:
    data: dict = {}
    if path:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    prof = profile or data.get("profile") or "dev-cpu"
    if prof not in PROFILES:
        raise ValueError(f"unknown profile {prof!r}; choose from {sorted(PROFILES)}")
    merged = _deep_merge(PROFILES[prof], data)
    if overrides:
        merged = _deep_merge(merged, overrides)
    merged["profile"] = prof
    return Config.model_validate(merged)
