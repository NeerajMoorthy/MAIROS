# MAIROS API — container image for Fly.io.
#
# Build from the repository root (mairos/), because the API imports the
# monorepo's `services/` and `packages/` directories:
#
#   docker build -f apps/api/Dockerfile -t mairos-api .
#
# `fly deploy` does this for you using fly.toml at the repository root.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf-cache \
    DATA_DIR=/data

WORKDIR /app

# CPU-only PyTorch first. sentence-transformers would otherwise pull the CUDA
# build — several gigabytes the Fly.io machine can never use.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install -r apps/api/requirements.txt

# Bake the embedding model into the image so a cold start does not depend on
# huggingface.co being reachable (or fast).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY services services
COPY packages packages
COPY apps/api apps/api

# Run as an unprivileged user; /data is the mounted volume.
RUN useradd --create-home --uid 10001 mairos \
    && mkdir -p /data \
    && chown -R mairos:mairos /data /opt/hf-cache
USER mairos

WORKDIR /app/apps/api
EXPOSE 8000

# One worker on purpose: agent runs are in-process threads and the rate
# limiter is per process (see app/middleware.py). Scale with machine size,
# not worker count.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
