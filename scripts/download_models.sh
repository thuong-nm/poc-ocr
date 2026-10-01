#!/usr/bin/env bash
# One-time ONLINE setup. Afterwards img2docx runs fully offline.
#
#   scripts/download_models.sh [--vlm none|ollama-2b|hf-2b|hf-4b|hf-8b] [--models-dir ./models]
#
# Everything is fetched from the model authors' official repos (licenses: see README / PLAN.md):
#   PaddlePaddle/PP-DocLayout_plus-L, PP-LCNet_x1_0_doc_ori, UVDoc,
#   arabic_PP-OCRv5_mobile_rec, en_PP-OCRv5_mobile_rec          (Apache-2.0)
#   tesseract-ocr/tessdata_best ara, eng, osd                     (Apache-2.0)
#   Qwen/Qwen3-VL-{2B,4B,8B}-Instruct  or Ollama qwen3-vl:2b-instruct-q4_K_M (Apache-2.0)
set -euo pipefail

VLM="ollama-2b"
MODELS_DIR="$(cd "$(dirname "$0")/.." && pwd)/models"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vlm) VLM="$2"; shift 2 ;;
    --models-dir) MODELS_DIR="$2"; shift 2 ;;
    *) echo "unknown arg $1"; exit 2 ;;
  esac
done
PY="${PYTHON:-python}"
mkdir -p "$MODELS_DIR"
export PADDLE_PDX_CACHE_HOME="$MODELS_DIR/paddlex"
export PADDLE_PDX_MODEL_SOURCE=huggingface
unset HF_HUB_OFFLINE TRANSFORMERS_OFFLINE

echo "== PaddleX models -> $PADDLE_PDX_CACHE_HOME"
"$PY" - <<'EOF'
from paddleocr import LayoutDetection, DocImgOrientationClassification, TextImageUnwarping, TextRecognition
for cls, names in [(LayoutDetection, ["PP-DocLayout_plus-L"]),
                   (DocImgOrientationClassification, ["PP-LCNet_x1_0_doc_ori"]),
                   (TextImageUnwarping, ["UVDoc"]),
                   (TextRecognition, ["arabic_PP-OCRv5_mobile_rec", "en_PP-OCRv5_mobile_rec"])]:
    for n in names:
        cls(model_name=n, device="cpu", enable_mkldnn=False)
        print("ok", n)
EOF

echo "== Tesseract tessdata_best (ara, eng, osd) -> $MODELS_DIR/tessdata_best"
mkdir -p "$MODELS_DIR/tessdata_best"
for l in ara eng osd; do
  f="$MODELS_DIR/tessdata_best/$l.traineddata"
  [[ -s "$f" ]] || curl -fL --retry 3 -o "$f" "https://github.com/tesseract-ocr/tessdata_best/raw/main/$l.traineddata"
done

case "$VLM" in
  none) ;;
  ollama-2b)
    command -v ollama >/dev/null || { echo "ollama not on PATH (see README)"; exit 1; }
    ollama pull qwen3-vl:2b-instruct-q4_K_M ;;
  hf-2b|hf-4b|hf-8b)
    size="${VLM#hf-}"; size="${size^^}"
    "$PY" -c "from huggingface_hub import snapshot_download as s; print(s('Qwen/Qwen3-VL-${size}-Instruct', local_dir='$MODELS_DIR/Qwen3-VL-${size}-Instruct'))" ;;
  *) echo "unknown --vlm $VLM"; exit 2 ;;
esac

echo "done. Offline from now on: models in $MODELS_DIR"
