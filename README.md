# img2docx — on-premise Photo → DOCX for Arabic / English official documents

img2docx converts a phone or camera photo (JPG, PNG, HEIC) of an official letter into an editable
**.docx**. It keeps the text, the reading order and the structure: RTL paragraphs, mixed
Arabic/English lines, tables with merged cells, letterhead/header/footer, stamps, signatures and
handwritten notes. Next to the .docx it writes a versioned **JSON IR**
(`img2docx/schema.py`). That JSON is the contract for review tools and ECM indexing: blocks,
boxes, per-block confidence, `needs_review` with reasons, and extracted Hijri/Gregorian dates and
document numbers.

Everything runs locally. The runtime makes no cloud OCR or LLM calls; models are downloaded once
at setup.

```
photo ─► QA ─► geometry (quad → warp → [UVDoc] → orientation vote → deskew) ─► illumination flatten
      ─► layout (PP-DocLayout + line/ink heuristics) ─► recognition (primary + cross-check)
      ─► post-process (bidi runs, dates, doc-no) ─► reading order (RTL/LTR XY-cut) ─► confidence
      ─► IR JSON ─► DOCX (w:bidi, w:rtl, cs fonts, bidiVisual tables, header/footer, floating stamp)
```

## Models and licenses (verified on Hugging Face / Ollama, 2026-10-01)

| Role | Model | License |
|---|---|---|
| Layout | `PaddlePaddle/PP-DocLayout_plus-L` (alt. `PP-DocLayoutV3`) | Apache-2.0 |
| Orientation | `PaddlePaddle/PP-LCNet_x1_0_doc_ori` + Tesseract OSD vote | Apache-2.0 |
| Dewarp (optional) | `PaddlePaddle/UVDoc` | Apache-2.0 |
| Classic OCR | Tesseract 5.5 `ara`+`eng` (tessdata / tessdata_best) | Apache-2.0 |
| Classic OCR (cross-check) | `PaddlePaddle/arabic_PP-OCRv5_mobile_rec`, `en_PP-OCRv5_mobile_rec` | Apache-2.0 |
| VLM, GPU server | `Qwen/Qwen3-VL-8B-Instruct` (or `-FP8`, `Qwen3-VL-4B-Instruct`) via vLLM | Apache-2.0 |
| VLM, 4 GB dev box | Ollama `qwen3-vl:2b-instruct-q4_K_M` (= `Qwen/Qwen3-VL-2B-Instruct`; GGUF `Qwen/Qwen3-VL-2B-Instruct-GGUF`) | Apache-2.0 |

DocLayout-YOLO is **not** used. Its weights are Apache-2.0, but inference needs an AGPL-3.0
ultralytics fork. Fonts in `assets/fonts` (OFL-1.1) are used only by the synthetic data
generator. PyMuPDF (AGPL) is a dev/eval-only dependency for rendering PDFs and is never used by
the runtime pipeline. See [PLAN.md](PLAN.md) for the full list and trade-offs.

## Setup (online once, then offline)

```bash
# 1. Python 3.11 env + Tesseract (no root needed with conda)
conda create -p .venv -c conda-forge python=3.11 tesseract
.venv/bin/pip install "paddlepaddle==3.3.1" "paddleocr==3.7.0"   # GPU: paddlepaddle-gpu (see Dockerfile)
.venv/bin/pip install -e ".[api,dev]"
# (Debian/Ubuntu alternative: apt install tesseract-ocr tesseract-ocr-ara)

# 2. Download all models once (PaddleX models, tessdata_best, and optionally the VLM)
PYTHON=.venv/bin/python scripts/download_models.sh --vlm ollama-2b    # or hf-8b / hf-4b / none

# 3. From now on there is no internet at runtime (config runtime.offline: true sets HF_HUB_OFFLINE etc.)
```

Optional local tools:
* **Ollama** (dev VLM). It installs without root: download the Linux tarball, run `ollama serve`, then
  `ollama pull qwen3-vl:2b-instruct-q4_K_M`.
* **LibreOffice** (only for the visual render check and tests). The AppImage from
  libreoffice.org can be extracted with `--appimage-extract`. Point `SOFFICE` at
  `.../program/soffice` if it is not on PATH.

## Usage

```bash
img2docx photo.jpg -o out/letter.docx [--json out/letter.json] [--debug-dir dbg/] [--config config.yaml] [--profile dev-vlm]
img2docx batch photos/ -o out/ --workers 4           # writes out/batch_report.json, prints pages/s
img2docx serve --host 0.0.0.0 --port 8080            # POST /convert (multipart file) -> zip(docx+json); ?format=json
```

```python
from img2docx.pipeline import convert
res = convert("photo.jpg", "out.docx", "config.yaml")
res.document.review.needs_review, res.document.metadata.dates
```

`--debug-dir` saves every stage:
* `00_input.jpg`, `01_geometry.jpg`, `02_illumination.jpg`
* `03_layout_raw.jpg` (model + heuristic regions)
* `04_layout_final.jpg` (final types + reading order)
* `crops/` (every region crop as sent to the engines)
* `raw/` (raw output of every engine for every block)
* `ir.json`

Stage timings are logged and stored in `timings_s` in the JSON.

### Profiles (`--profile` or `profile:` in YAML; see `config.example.yaml`)

| profile | primary | cross-check | where |
|---|---|---|---|
| `dev-cpu` (default) | Tesseract (own line segmentation, per-line LSTM) | PaddleOCR rec | any CPU |
| `dev-vlm` | Qwen3-VL-2B Q4 via Ollama (~2 GB VRAM) | Tesseract | 4 GB GPU box |
| `gpu-server` | Qwen3-VL-8B-Instruct via vLLM | PaddleOCR | ≥ 24 GB GPU (8B bf16), or 16 GB with FP8 |

Paddle models (layout, orientation, OCR rec) run on CUDA when a CUDA paddle wheel is installed.
If not, or if CUDA fails or runs out of memory, they fall back to CPU automatically. The VLM
always runs in its own server process.

GPU server via Docker: `scripts/download_models.sh --vlm hf-8b --models-dir ./models`, then
`docker compose up` (services `vllm` + `img2docx` API on :8080).

## Faithfulness rules (enforced in code)

* No spell-correction, normalization or translation anywhere. Normalized values (Latin digits,
  ISO dates) exist **only** in `metadata`, and `raw` keeps the original string.
* Digit forms are preserved. VLM prompts demand it, and the classic engines output what they see.
* Unreadable words become `[؟]` (Tesseract words below `unreadable_word_conf`; the VLM is prompted
  to do the same). Their presence lowers confidence and sets `needs_review`.
* No aggressive binarization: recognizers get colour/grayscale crops. Binary masks are used only
  for analysis (line finding, rules, orientation).
* Stamp ink overlapping printed text is suppressed in text crops (by colour). Stamps, signatures,
  logos and figures are inserted as images and never OCR'd into body text. Stamp text goes to
  `metadata.stamp_texts` only.
* Hallucination guards for the VLM:
  * `max_tokens` scales with region area / line height
  * repetition-loop truncation
  * `finish_reason=length` flag
  * low logprob penalty
  * cross-engine agreement
  * a flag for diacritics that only the VLM produced
  * digit-heavy lines prefer a confident classic engine (small VLMs reorder digit groups)

## Confidence and review

Per block: `0.6·engine_conf + 0.4·agreement`.
* `engine_conf` comes from VLM token logprobs (mean probability minus a penalty for very uncertain
  tokens) or from Tesseract word confidences.
* `agreement` is 1 − normalized edit distance between the primary and cross-check engines,
  ignoring tashkeel/whitespace, and digits for Paddle.
* Then: −0.15 for handwriting, and a penalty for `[؟]` marks.

Page score = character-weighted mean of the block scores. `needs_review` is true when any block
is below `block_review_threshold`, the page score is below `page_review_threshold`, there is a
handwritten note or `[؟]`, or a severe QA warning (blur, low effective dpi, glare). The reasons
are listed in `review.reasons` and per block.

## DOCX details

* Section `w:bidi`. Paragraphs carry an explicit `w:bidi` (or `w:val="0"` for LTR paragraphs on
  RTL pages). Runs are split with a UAX#9-style splitter; Arabic runs get `w:rtl` and English runs
  inside RTL paragraphs stay LTR.
* Fonts: `w:rFonts w:cs="Simplified Arabic"` (configurable) plus `w:ascii/hAnsi` (Arial),
  `w:sz` + `w:szCs`, `w:b` + `w:bCs`, `w:lang w:bidi="ar-SA"`. Size is estimated from the
  measured line height.
* Alignment is in visual terms. For bidi paragraphs `w:jc` left/right are logical in Word and
  LibreOffice, and the builder handles this; it is verified by rendering in
  `tests/test_docx_render.py`.
* Tables are built from HTML with `gridSpan`/`vMerge`. RTL tables get `w:bidiVisual`, and header
  cells are bold and shaded.
* The letterhead goes into the DOCX header as a borderless 3-cell band: Arabic right, logo centre,
  English left. Footer blocks go into the DOCX footer.
* Stamps are floating `wp:anchor` images placed behind text at their original page position.
  Signatures, logos and figures are inline images aligned by position.
* Optional: `docx.highlight_low_confidence` (yellow highlight) and `docx.comment_low_confidence`
  (a Word comment with the score and reasons).

## Plugging in a fine-tuned LoRA adapter later

Both VLM backends route by region type via `recognition.vlm.adapters` (keys: a region type such as
`table`, or `printed` / `handwritten`):

* **vLLM**: `vllm serve Qwen/Qwen3-VL-8B-Instruct --enable-lora --max-lora-rank 64 --lora-modules printed=/models/lora/printed hw=/models/lora/hw`
  with `adapters: {printed: printed, handwritten: hw}`. The adapter name is sent as the request
  `model`.
* **transformers**: `backend: transformers`, `adapters: {printed: /models/lora/printed, handwritten: /models/lora/hw}`.
  The PEFT adapters are loaded once and switched per request. With no matching adapter, the base
  model is used.

Train the adapters with the same prompts as `img2docx/recognizers/qwen_vl.py::PROMPTS` on
region crops. The synthetic generator plus real reviewed IR JSON make a ready-made dataset.

## Testing and evaluation

```bash
pytest -q                         # unit + e2e (CPU) + LibreOffice render; VLM tests skip without a server
pytest -q -m "not slow"           # fast subset
python scripts/gen_synthetic.py -o data/synth -n 4 --seed 100      # ar / en / mixed × clean / mild / hard
python scripts/evaluate.py data/synth -o reports/eval_dev-cpu.md --profile dev-cpu
python scripts/evaluate.py data/synth -o reports/eval_dev-vlm.md --profile dev-vlm
```

The generator renders letters with Pillow + libraqm (HarfBuzz shaping, FriBiDi), so connected
Arabic letters and bidi order are correct. Each letter has:
* a letterhead and logo, number/Hijri/Gregorian dates, and a basmala with tashkeel
* paragraphs, including mixed Arabic/English
* a table with rowspan + colspan
* a closing line, signature, overlapping stamp, handwritten margin note (Aref Ruqaa / Caveat) and footer

It then applies curvature, perspective, desk background, shadows, blur, noise, downscaling and
JPEG compression. The ground truth is kept in `*.gt.json`.

`evaluate.py` reports:
* CER/WER per block type, language and degradation level (content-aligned, so block merges and
  splits don't distort it), plus diacritics-insensitive CER
* TEDS and TEDS-S for tables
* Kendall τ for reading order
* block-type accuracy
* stamp/signature/logo recall
* date and document-number extraction accuracy
* runtime per page

Reports are in `reports/`.

## Results (synthetic set: 36 pages = 12 letters × clean/mild/hard; full reports in `reports/`)

| profile | page CER | paragraph CER | English CER | table TEDS-S | reading order τ | s/page (GTX 1650 box) |
|---|---|---|---|---|---|---|
| dev-cpu, 36 pages | 0.170 | 0.151 | 0.064 | 1.000 | 0.908 | 18.8 |
| dev-cpu, 12 mild pages | 0.146 | 0.138 | 0.073 | 1.000 | 0.898 | 17.4 |
| dev-vlm (Qwen3-VL-2B Q4), 12 mild pages | 0.138 | 0.110 | 0.056 | 1.000 | 0.929 | 160 |

Other results:
* Stamp recall is 1.00, logo 1.00, signature 0.39.
* With the VLM, date extraction rises from 40% to 65% and doc-number extraction from 50% to 67%.
* UVDoc on the hard subset: CER 0.201 → 0.193 at +3 s/page, so it is off by default and on in
  `gpu-server`.

A Vietnamese project report is in [reports/BAO_CAO_vi.md](reports/BAO_CAO_vi.md).

## Known limitations

* **Handwriting.** Tesseract and Paddle cannot read Ruqaa/cursive handwriting. Qwen3-VL-2B gets
  short notes roughly right. Handwritten blocks are always flagged `needs_review`. A
  handwriting LoRA on the 8B model is the intended fix.
* **Calligraphic / decorative text** (e.g. Thuluth headers, basmala with full tashkeel). The classic
  engines garble it; prefer the VLM on the GPU server and expect review. Tesseract also degrades on
  fonts with heavy stacked ligatures (e.g. Amiri: ~0.45 CER on some pages vs ~0.1 on Naskh/Sans fonts).
* **Arabic-Indic digits (٠-٩) with Tesseract** are often misread (e.g. `٣/٣٧٤٥` → `P/PVEO`).
  PaddleOCR reads them better but drops `/` and `:`. The agreement check flags these lines for
  review rather than guessing. Dates/numbers on such pages need the VLM (8B) or human review.
* **Small VLM (2B Q4)** sometimes adds tashkeel that isn't in the image, and misreads or
  reorders Arabic-Indic numbers. This is mitigated by cross-checks and flags, not solved. Use 8B
  in production.
* **Very low-quality photos** (heavy blur, <120 effective dpi, glare over text). QA warns and
  confidence drops, but text may be wrong. Re-take the photo.
* **Handwriting/signature detection** relies on coloured-ink heuristics. Black-ink handwriting is
  treated as print, so its OCR confidence (and the review flag) is the safety net.
* Layout is geared to letters and forms (XY-cut reading order). Complex magazine-style layouts are
  out of scope. Output aims for correct structure and content, not pixel-identical layout.
* Paddle's Arabic recognizer mangles Latin digits inside RTL lines, so the agreement score
  ignores digits for Paddle.
* CPU dev mode is slow: roughly 30–45 s/page on 8 threads (layout ~8 s, recognition ~20 s).
