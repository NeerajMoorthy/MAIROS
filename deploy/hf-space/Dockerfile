# MAIROS API — container image for a Hugging Face Space (Docker SDK).
#
# The Space is built from a bundle assembled by scripts/build_hf_space.py:
# this Dockerfile at the root, with apps/api, services and packages beside it.
# It differs from apps/api/Dockerfile (Fly.io) only where Spaces require:
# the container runs as UID 1000 and serves on port 7860.
#
# GROQ_API_KEY is not set here. Add it as a secret in the Space's
# Settings -> Variables and secrets; without it the API runs on the offline
# fallback model.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf-cache \
    DATA_DIR=/data \
    DEFAULT_LLM=openai/gpt-oss-120b \
    FAST_LLM=openai/gpt-oss-20b

WORKDIR /app

# CPU-only PyTorch first. sentence-transformers would otherwise pull the CUDA
# build — several gigabytes a CPU Space can never use.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install -r apps/api/requirements.txt

# Bake the embedding model into the image so a cold start does not depend on
# downloading it.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY services services
COPY packages packages
COPY apps/api apps/api

# Spaces run the container as UID 1000. /data holds projects, uploads, the
# vector index and graphs; on the free tier it is wiped when the Space restarts.
RUN useradd --create-home --uid 1000 user \
    && mkdir -p /data \
    && chown -R user:user /data /opt/hf-cache
USER user

WORKDIR /app/apps/api
EXPOSE 7860

# One worker on purpose: agent runs are in-process threads and the rate
# limiter is per process (see app/middleware.py).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]
