# GPU image for the img2docx pipeline (layout/OCR/orchestration + optional FastAPI).
# The VLM is served by a separate vLLM container (see docker-compose.yml) that runs
# Qwen/Qwen3-VL-8B-Instruct. Models are baked in at build time (online), so the
# runtime needs no internet.
#
#   docker build -t img2docx:gpu .
#   docker run --gpus all -v $PWD/in:/in -v $PWD/out:/out img2docx:gpu /in/photo.jpg -o /out/photo.docx --profile gpu-server
ARG CUDA_IMAGE=nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04
FROM ${CUDA_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PADDLE_PDX_CACHE_HOME=/models/paddlex PADDLE_PDX_MODEL_SOURCE=huggingface \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip curl ca-certificates \
        tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng \
        libgl1 libglib2.0-0 libgomp1 fonts-noto-core fonts-hosny-amiri \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY pyproject.toml README.md ./
COPY img2docx ./img2docx
COPY scripts ./scripts
COPY config.example.yaml ./
# GPU wheel of PaddlePaddle (CUDA 12.6 index). For CPU-only images use paddlepaddle==3.3.1 from PyPI.
RUN pip install "paddlepaddle-gpu==3.3.1" -i https://www.paddlepaddle.org.cn/packages/stable/cu126/ \
 && pip install "paddleocr==3.7.0" && pip install ".[api]"

# Bake models (online at build time only)
RUN bash scripts/download_models.sh --vlm none --models-dir /models

ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
EXPOSE 8080
ENTRYPOINT ["img2docx"]
CMD ["--help"]
