# PLAN — img2docx (photo → editable DOCX, Arabic/English)

## Environment (inspected 2026-10-01)
| Item | Value |
|---|---|
| OS | Windows + WSL2, Ubuntu 24.04.1, kernel 5.15 (WSL) |
| CPU / RAM | 8 threads, 15 GiB RAM |
| GPU | NVIDIA GTX 1650, 4 GiB VRAM (~2.9 GiB free; desktop uses ~1.2 GiB), Turing → fp16/int8/int4 only, **no bf16** |
| Driver / CUDA | 595.97 / CUDA 13.2 runtime support |
| Python | conda-prefix env `./.venv`, Python 3.11 (system 3.12 untouched; no sudo) |
| Disk | ~800 GB free |
| Missing system tools | tesseract, libreoffice, ollama → installed without root: tesseract from conda-forge, LibreOffice AppImage (extracted) in `~/.local/opt/libreoffice`, Ollama tarball in `~/.local/opt/ollama` |

## Models (IDs and licenses checked against the Hugging Face API / Ollama library on 2026-10-01)
| Role | Model ID | License | Where it runs |
|---|---|---|---|
| Primary VLM (GPU server) | `Qwen/Qwen3-VL-8B-Instruct` (or `-FP8`), `Qwen/Qwen3-VL-4B-Instruct` | Apache-2.0 | vLLM (OpenAI-compatible server) or HF transformers |
| Primary VLM (dev box, 4 GB) | Ollama `qwen3-vl:2b-instruct-q4_K_M` (verified tag; also `qwen3-vl:2b-instruct`, `-q8_0`) (= `Qwen/Qwen3-VL-2B-Instruct`), GGUF alt: `Qwen/Qwen3-VL-2B-Instruct-GGUF` (`Qwen3VL-2B-Instruct-Q4_K_M.gguf` + `mmproj-…-Q8_0.gguf`) for llama.cpp | Apache-2.0 | Ollama / llama-server HTTP API |
| Layout | `PaddlePaddle/PP-DocLayout_plus-L` (alternatives evaluated: `PP-DocLayoutV3`, `PP-DocLayout-M/S`) | Apache-2.0 | PaddleX (CPU by default, GPU optional) |
| Page orientation | `PaddlePaddle/PP-LCNet_x1_0_doc_ori` (+ Tesseract OSD fallback) | Apache-2.0 | PaddleX |
| Dewarp (optional) | `PaddlePaddle/UVDoc` | Apache-2.0 | PaddleX, off by default |
| Classic OCR #1 | Tesseract 5.5 `ara`+`eng` traineddata (tesseract-ocr/tessdata) | Apache-2.0 | local binary |
| Classic OCR #2 | `PaddlePaddle/PP-OCRv5_server_det` + `PaddlePaddle/arabic_PP-OCRv5_mobile_rec` (+ `en_PP-OCRv5_mobile_rec`) | Apache-2.0 | PaddleOCR 3.7 |

**Rejected / notes**
- DocLayout-YOLO (`juliozhao/DocLayout-YOLO-DocStructBench`): the weights are labelled Apache-2.0, but inference requires the authors' fork of **ultralytics, which is AGPL-3.0**. That is a risk for commercial on-prem distribution, so it is not used.
- DocTr (dewarping): no maintained commercially licensed weights. UVDoc via PaddleX is used instead.
- PaddleOCR-VL-1.6 (0.9B, Apache-2.0) is a strong option for the future. It is not wired in now because the spec asks for Qwen3-VL.

## Libraries (all permissive)
paddlepaddle 3.3 / paddleocr 3.7 / paddlex (Apache-2.0), opencv-python-headless (Apache-2.0), Pillow 12 with bundled libraqm (MIT-CMU), pillow-heif (BSD-3), python-docx 1.2 (MIT), lxml (BSD), pydantic 2 (MIT), typer (MIT), fastapi + uvicorn (MIT/BSD), rapidfuzz (MIT), python-bidi (LGPL-3.0, used only as a dynamically imported library; it can be swapped for our own UAX#9-lite run splitter, which is what we actually use), httpx (BSD), pytesseract (Apache-2.0), PyMuPDF (**AGPL**: used only in dev/eval tooling to rasterize PDFs, never in the runtime package; `pdftoppm` is an alternative).

Fonts (synthetic data only): Noto Naskh Arabic, Noto Sans Arabic, Amiri, Aref Ruqaa, Noto Serif/Sans, Caveat. All SIL OFL 1.1.

## Architecture
```
load+QA → geometry (quad detect → warp → [UVDoc] → orientation) → illumination flatten
→ layout (PP-DocLayout → our classes, heuristics for doc_number/date/handwritten)
→ reading order (direction detection, RTL/LTR XY-cut column-aware)
→ recognition (router: region_type → recognizer; primary + cross-check)
→ postprocess (bidi runs, dates/doc-no → metadata; no correction)
→ confidence (logprobs ⊕ engine agreement ⊕ handwriting penalty) → IR JSON (pydantic, versioned)
→ DOCX builder (python-docx + raw OOXML: bidi, rtl, cs fonts, bidiVisual, merged cells, header/footer, images)
```
- Every recognizer implements `Recognizer.recognize(crop, region_type) -> RecognitionResult`.
- VLM backends share one OpenAI-compatible HTTP client (vLLM, llama.cpp `llama-server`, and Ollama's `/v1` all speak it). `transformers` is a separate in-process backend.
- LoRA adapters: a config map `region_type → adapter name`. vLLM serves adapters by name via `--lora-modules`. Transformers loads them via PEFT.
- `max_tokens` scales with region area (tokens ≈ k · area / line_height²). This caps hallucinated run-on output.

## Trade-offs
- On the 4 GB card, the default fast path is Tesseract (+ PaddleOCR cross-check). Qwen3-VL-2B Q4 via Ollama is opt-in (`--profile dev-vlm`): ~2 GB VRAM, slow and weaker on Arabic than 8B.
- Paddle runs on CPU on the dev box. A GPU paddle wheel for Turing + CUDA 12 is possible, but it would compete with Ollama for the 4 GB. Layout + OCR on CPU takes about seconds per page.
- No aggressive binarization. Illumination flattening divides by an estimated background and keeps grayscale.
- Reading order uses a recursive XY-cut that respects page direction. This is robust for letters and forms. Exotic magazine layouts are out of scope.

## Milestones
1. Skeleton: QA → warp → Tesseract → IR → DOCX (end to end) + synthetic generator.
2. Layout model + reading order + tables (Tesseract cells / VLM HTML).
3. PaddleOCR cross-check + confidence + review flags.
4. VLM backends (Ollama dev, vLLM/transformers server) + LoRA hooks.
5. Eval report, LibreOffice render check, Docker, README.
