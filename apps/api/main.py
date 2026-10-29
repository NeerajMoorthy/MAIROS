"""MAIROS — FastAPI backend entry point.

Run from ``mairos/apps/api``::

    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

# Must come first: puts services/ and packages/ on sys.path.
from app import bootstrap  # noqa: F401

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import authorize
from app.config import settings
from app.errors import OutageMiddleware, install_error_handlers
from app.middleware import (
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    RequestSizeLimitMiddleware,
    configure_logging,
)
from app.routers import (
    chat,
    evaluation,
    graph,
    ingest,
    patents,
    projects,
    query,
    tasks,
    workspace,
)
from app.store import metadata_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create storage directories and restore persisted state."""
    configure_logging(settings.log_level)
    settings.ensure_dirs()
    metadata_store.load()
    try:
        from app.dependencies import get_chroma_store
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(get_chroma_store)
    except Exception:
        pass
    yield
    metadata_store.save()


app = FastAPI(
    title="MAIROS API",
    description=(
        "Multi-Agent Intelligent Research & Orchestration System — "
        "RAG over ChromaDB, a NetworkX knowledge graph, and a multi-agent "
        "orchestrator."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# Middleware order matters, and Starlette runs the LAST one added first. The
# intended order on the way in is:
#
#   CORS -> logging -> outage handling -> size cap -> rate limit -> the route
#
# CORS is outermost so that EVERY response carries its headers, including the
# 413s, 429s, 503s and 500s produced by the middleware below it. With CORS
# innermost those rejections reached the browser with no
# `Access-Control-Allow-Origin`, so the frontend could not read a single one of
# their messages — they all surfaced as `TypeError: Failed to fetch`. Logging
# comes next so a rejected request still gets a request id, and the outage
# handler sits above the size and rate checks so their responses are returned
# as written rather than being caught and relabelled.
#
# They are added in the reverse of that order.
if settings.rate_limit_enabled:
    app.add_middleware(
        RateLimitMiddleware,
        read_limit=settings.rate_limit_reads,
        write_limit=settings.rate_limit_writes,
        window_seconds=settings.rate_limit_window_seconds,
    )

app.add_middleware(
    RequestSizeLimitMiddleware,
    max_json_bytes=settings.max_request_bytes,
    max_upload_bytes=settings.max_upload_bytes,
)

app.add_middleware(OutageMiddleware)
app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    # Explicit origins from configuration — never "*", and credentials are off
    # because MAIROS has no auth and sets no cookies.
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
    expose_headers=["X-Request-ID", "Retry-After"],
)

install_error_handlers(app)

# `authorize` guards every API route: a no-op in local mode, and with auth
# enabled it verifies the caller and checks project ownership from the path —
# the one place isolation is enforced (see app/auth.py). The health probes
# below are deliberately outside it.
for router in (projects, ingest, query, graph, chat, tasks, evaluation, patents, workspace):
    app.include_router(router.router, prefix="/api", dependencies=[Depends(authorize)])


def _health() -> dict:
    from services.generation.provider import describe_provider

    try:
        llm = describe_provider()
    except Exception as exc:
        llm = {"provider": "unavailable", "error": str(exc), "live": False}

    payload = {
        "status": "ok",
        "version": app.version,
        "llm": llm,
        "vector_store": "chromadb (embedded)",
        "knowledge_graph": "networkx (file-backed)",
        "metadata_store": "postgres" if settings.uses_postgres else "sqlite",
        "auth": "enabled" if settings.auth_enabled else "local single-user mode",
    }
    # The probe is unauthenticated, so with auth on it must not reveal how
    # many projects other people have.
    if not settings.auth_enabled:
        payload["projects"] = len(metadata_store.list_projects())
    return payload


@app.get("/health")
async def health_check() -> dict:
    """Liveness probe — also reports which LLM provider is active."""
    return _health()


@app.get("/api/health")
async def api_health_check() -> dict:
    """Same probe under the /api prefix the frontend proxies."""
    return _health()
