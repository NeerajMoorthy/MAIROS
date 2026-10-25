"""Turning backend outages into answers a user can act on.

Two services MAIROS depends on can be down independently of MAIROS itself: the
vector store (ChromaDB, including the embedding model it loads on first use)
and the LLM provider. Before this module, either one failing surfaced as a bare
500 with a stack trace in the logs and nothing useful in the UI.

The handling here is deliberately narrow. A dependency being unreachable is a
503 with a sentence naming which dependency and what the user can do; anything
else stays a 500, because dressing up an unknown bug as a temporary outage
would be a lie that costs someone an afternoon of retrying.
"""

from __future__ import annotations

import logging
import socket

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("mairos.http")


class ServiceUnavailable(Exception):
    """A dependency MAIROS needs is not reachable right now.

    Args:
        service: Human-readable name of the dependency.
        detail: What the user can do about it.
    """

    def __init__(self, service: str, detail: str):
        self.service = service
        self.detail = detail
        super().__init__(f"{service}: {detail}")


# Exception types that mean a service is unreachable.
#
# Narrow on purpose. An earlier version used ``isinstance(exc, OSError)``,
# which is true of ``FileNotFoundError``, ``PermissionError`` and
# ``IsADirectoryError`` — none of which is an outage, all of which are ordinary
# bugs. Reporting a bug as a temporary outage with retry advice is worse than
# reporting nothing, because it sends the reader off to retry for an afternoon.
_STDLIB_OUTAGES: tuple[type[BaseException], ...] = (
    ConnectionError,  # refused / reset / aborted / broken pipe
    TimeoutError,
    socket.gaierror,  # DNS failure
    socket.timeout,
)

# Third-party exceptions that do not derive from the above. Matched by name so
# a library renaming a class degrades to a 500 rather than breaking the import.
# ``HTTPError`` is deliberately absent: requests raises it for a 401, and a bad
# API key is a configuration problem, not an outage.
_OUTAGE_NAMES = frozenset(
    {
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "PoolTimeout",
        "TimeoutException",
        "ProxyError",
        "NetworkError",
        "ChromaConnectionError",
    }
)

# Markers that identify which dependency failed, so the advice is about the
# right one. Checked against the whole exception chain's text.
_LLM_MARKERS = ("groq", "api.groq.com", "openai", "chat model", "completion")
_VECTOR_MARKERS = ("chroma", "huggingface", "sentence-transformers", "embedding", "onnx")


def _chain(exc: BaseException) -> list[BaseException]:
    """The exception and its explicit ``__cause__`` chain, outermost first.

    ``__context__`` is deliberately not followed. Python sets it implicitly for
    *any* exception raised inside *any* ``except`` block, so a handled
    ``FileNotFoundError`` from an optional-file lookup would attach itself to
    every later exception in the same handler and turn a ``KeyError`` into a
    503. ``__cause__`` is only ever set by an explicit ``raise ... from``,
    which is a real statement about causation.
    """
    seen: set[int] = set()
    out: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        out.append(current)
        current = current.__cause__
    return out


def looks_like_an_outage(exc: BaseException) -> bool:
    """Whether *exc*, or something it explicitly wraps, means a service is down."""
    return any(
        isinstance(item, _STDLIB_OUTAGES) or type(item).__name__ in _OUTAGE_NAMES
        for item in _chain(exc)
    )


def failing_service(exc: BaseException) -> str:
    """Which dependency the outage is about: ``"llm"`` or ``"vector-store"``.

    The vector store is the default because it is the dependency every request
    touches; the LLM is only reached once retrieval has already succeeded.
    """
    text = " ".join(f"{type(item).__name__} {item}" for item in _chain(exc)).lower()
    if any(marker in text for marker in _LLM_MARKERS) and not any(
        marker in text for marker in _VECTOR_MARKERS
    ):
        return "llm"
    return "vector-store"


VECTOR_STORE_ADVICE = (
    "The vector store is not reachable. If this is a fresh install it may still "
    "be downloading the embedding model; otherwise check that the data directory "
    "is writable and that the machine has network access."
)

LLM_ADVICE = (
    "The language model provider is not reachable. MAIROS falls back to its "
    "offline model for generation, but this request needed a live one. Check "
    "GROQ_API_KEY and network access, then retry."
)

ADVICE = {"vector-store": VECTOR_STORE_ADVICE, "llm": LLM_ADVICE}


def install_error_handlers(app: FastAPI) -> None:
    """Register the outage handlers on *app*."""

    @app.exception_handler(ServiceUnavailable)
    async def _service_unavailable(request: Request, exc: ServiceUnavailable):
        request_id = getattr(request.state, "request_id", None)
        logger.warning(
            "service unavailable: %s (%s) request_id=%s",
            exc.service,
            request.url.path,
            request_id,
        )
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "30"},
            content={
                "detail": exc.detail,
                "service": exc.service,
                "request_id": request_id,
            },
        )


class OutageMiddleware(BaseHTTPMiddleware):
    """Convert an unhandled exception into a 503 or a 500, as middleware.

    Middleware rather than ``@app.exception_handler(Exception)`` because of
    where Starlette puts the two. The generic exception handler lives in
    ``ServerErrorMiddleware``, which wraps *everything* — including
    ``CORSMiddleware``. A response produced there therefore never gets an
    ``Access-Control-Allow-Origin`` header, so the browser refuses to let the
    frontend read it and every carefully worded outage message arrives as an
    opaque ``TypeError: Failed to fetch``. Catching here, inside CORS, means
    the message actually reaches the person it was written for.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            request_id = getattr(request.state, "request_id", None)

            if looks_like_an_outage(exc):
                service = failing_service(exc)
                logger.warning(
                    "dependency outage (%s) on %s: %s request_id=%s",
                    service,
                    request.url.path,
                    exc,
                    request_id,
                )
                return JSONResponse(
                    status_code=503,
                    headers={"Retry-After": "30"},
                    content={
                        "detail": ADVICE[service],
                        "service": service,
                        "request_id": request_id,
                    },
                )

            # A genuine bug. Log it in full, but do not hand the stack trace to
            # the caller — it names internal paths and library versions.
            logger.exception(
                "unhandled error on %s request_id=%s", request.url.path, request_id
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": (
                        "Something went wrong handling this request. The failure has "
                        "been logged; quote the request id if you report it."
                    ),
                    "request_id": request_id,
                },
            )


__all__ = [
    "ADVICE",
    "OutageMiddleware",
    "LLM_ADVICE",
    "VECTOR_STORE_ADVICE",
    "ServiceUnavailable",
    "failing_service",
    "install_error_handlers",
    "looks_like_an_outage",
]
