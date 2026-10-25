"""Baseline HTTP hardening: size caps, rate limiting, structured logging.

Authentication is optional (``app/auth.py``) and no caller is ever "trusted"
enough to be exempt. What these middlewares protect against is the failure
mode that applies either way: one client, script, or runaway frontend loop
exhausting the box. The expensive endpoints here are genuinely
expensive (a task run embeds, retrieves, and calls an LLM several times), so
the limits are deliberately per-endpoint-class rather than one global number.

Three pieces, in the order they matter:

1. :class:`RequestSizeLimitMiddleware` rejects an oversized body from its
   ``Content-Length`` *before* anything reads it. The upload route already had
   a 40 MB check, but it ran after ``await file.read()`` had pulled the whole
   body into memory — which is exactly the request you most want to refuse
   early. JSON routes get a much smaller cap, because none of them has any
   business receiving a megabyte.

2. :class:`RateLimitMiddleware` applies a fixed-window counter per client, with
   a tighter budget for the routes that start agent work. It is in-process and
   therefore per-worker: correct for this deployment (one uvicorn process), and
   the docstring says so rather than implying a distributed guarantee it does
   not provide.

3. :class:`RequestLoggingMiddleware` emits one structured line per request with
   a correlation id that is also returned to the caller, so a user reporting
   "the run failed" can be matched to a log line.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("mairos.http")


# ---------------------------------------------------------------------------
# Request size
# ---------------------------------------------------------------------------
class RequestSizeLimitMiddleware:
    """Reject bodies larger than the cap for their route class.

    Pure ASGI rather than ``BaseHTTPMiddleware`` because the header alone is
    not enough. ``Content-Length`` is absent on an HTTP/1.1 chunked request,
    and uvicorn accepts those — so a header-only check let a chunked 40 MB body
    straight through to the very ``await file.read()`` this class exists to get
    in front of. The declared length is still checked first (it is free, and it
    refuses before a single byte arrives), and the body is then metered as it
    streams so a request that lies about or omits its length is cut off at the
    same limit.

    Args:
        app: The ASGI app.
        max_json_bytes: Cap for ordinary requests.
        max_upload_bytes: Cap for the multipart document upload route.
        upload_suffixes: Path suffixes that get the larger cap.
    """

    def __init__(
        self,
        app,
        max_json_bytes: int = 1 * 1024 * 1024,
        max_upload_bytes: int = 40 * 1024 * 1024,
        upload_suffixes: tuple[str, ...] = ("/documents",),
    ):
        self.app = app
        self.max_json_bytes = max_json_bytes
        self.max_upload_bytes = max_upload_bytes
        self.upload_suffixes = upload_suffixes

    def limit_for(self, path: str) -> int:
        return (
            self.max_upload_bytes
            if any(path.endswith(suffix) for suffix in self.upload_suffixes)
            else self.max_json_bytes
        )

    @staticmethod
    def _too_large(limit: int, size: int | None) -> JSONResponse:
        megabytes = limit / (1024 * 1024)
        measured = (
            f"Request body is {size / (1024 * 1024):.1f} MB, over the "
            if size is not None
            else "Request body is over the "
        )
        return JSONResponse(
            status_code=413,
            content={"detail": f"{measured}{megabytes:.0f} MB limit for this endpoint."},
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self.limit_for(scope.get("path", ""))
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        declared = headers.get("content-length")

        if declared is not None:
            try:
                size = int(declared)
            except ValueError:
                await JSONResponse(
                    status_code=400, content={"detail": "Malformed Content-Length header"}
                )(scope, receive, send)
                return
            # A negative or absurd length is a malformed request, not a small one.
            if size < 0:
                await JSONResponse(
                    status_code=400, content={"detail": "Malformed Content-Length header"}
                )(scope, receive, send)
                return
            if size > limit:
                await self._too_large(limit, size)(scope, receive, send)
                return

        # Meter the stream. `received` is closed over by the wrapper so the
        # running total survives across body chunks.
        state = {"received": 0, "exceeded": False}

        async def metered_receive():
            message = await receive()
            if message["type"] == "http.request":
                state["received"] += len(message.get("body", b""))
                if state["received"] > limit:
                    state["exceeded"] = True
                    # Tell the app the body ended. It will see a short body and
                    # fail its own validation, but we answer 413 below either
                    # way, so what it does with the truncated body is moot.
                    return {"type": "http.disconnect"}
            return message

        sent_response = {"started": False}

        async def guarded_send(message):
            if state["exceeded"] and not sent_response["started"]:
                return  # swallow the app's response; ours is sent instead
            if message["type"] == "http.response.start":
                sent_response["started"] = True
            await send(message)

        try:
            await self.app(scope, metered_receive, guarded_send)
        except Exception:
            # Cutting the body short makes Starlette raise ClientDisconnect (or
            # the app's own parse error). That is this middleware's doing, so it
            # answers for it rather than letting a 500 escape; anything raised
            # for another reason is re-raised untouched.
            if not state["exceeded"]:
                raise

        if state["exceeded"] and not sent_response["started"]:
            await self._too_large(limit, None)(scope, receive, send)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window request limiting per client address.

    **Scope.** The counters live in this process's memory, so the limit is per
    worker. MAIROS runs as a single uvicorn process, which makes that exact
    here; behind several workers or replicas it would need a shared store, and
    this class does not pretend otherwise.

    Two budgets apply. Anything that starts agent work — creating a task,
    uploading a document, running an evaluation — costs an LLM round trip and
    an embedding pass, so it gets the smaller one. Reads get the larger.

    Args:
        app: The ASGI app.
        read_limit: Requests per window for ordinary endpoints.
        write_limit: Requests per window for expensive endpoints.
        window_seconds: Length of the window.
        expensive_suffixes: Path suffixes that draw on the write budget.
    """

    _instances: "list[RateLimitMiddleware]" = []

    # Only sweep once the table is big enough for the scan to be worth it.
    EVICT_ABOVE = 512

    def __init__(
        self,
        app,
        read_limit: int = 240,
        write_limit: int = 20,
        window_seconds: float = 60.0,
        expensive_suffixes: tuple[str, ...] = (
            "/tasks",
            "/documents",
            "/evaluation/run",
            "/query",
            # `/retrieve` runs a full embedding pass plus vector and graph
            # retrieval — the same cost that justifies the write budget in the
            # first place. Leaving it out gave it 12x the intended throughput.
            "/retrieve",
            "/chat",
            "/search",
        ),
        # Paths exempt from limiting, matched exactly. A suffix match would
        # exempt `/anything/health`, including unrouted paths, which is a free
        # hole in the limiter for the cost of one path segment.
        exempt_paths: tuple[str, ...] = ("/health", "/api/health"),
    ):
        super().__init__(app)
        self.read_limit = read_limit
        self.write_limit = write_limit
        self.window_seconds = window_seconds
        self.expensive_suffixes = expensive_suffixes
        self.exempt_paths = exempt_paths
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()
        # Starlette builds middleware instances lazily inside the ASGI stack,
        # so there is no handle to the live object from outside. Registering
        # here gives tests (and a developer at a REPL) one, without exporting
        # the whole stack or reaching into Starlette internals.
        RateLimitMiddleware._instances.append(self)

    # ------------------------------------------------------------------
    def _client(self, request: Request) -> str:
        """The budget holder: the signed-in user if there is one, else the address.

        Behind the Cloudflare frontend every browser's request reaches the API
        from the proxy's address, so keying on the address alone would make all
        users share one budget. The token's subject is read *unverified* here
        — only to pick a bucket. That is safe because the token is fully
        verified before any route runs: a forged subject buys a separate bucket
        whose requests all end at a 401, which costs nothing to serve.
        """
        header = request.headers.get("authorization", "")
        if header[:7].lower() == "bearer ":
            try:
                import jwt

                subject = jwt.decode(header[7:].strip(), options={"verify_signature": False}).get("sub")
                if subject:
                    return f"user:{str(subject)[:64]}"
            except Exception:
                pass  # malformed tokens fall back to the address
        return request.client.host if request.client else "unknown"

    def _bucket(self, request: Request) -> tuple[str, int]:
        """Which budget this request draws on, and how large it is."""
        path = request.url.path
        # DELETE is always expensive here: deleting a project cascades across
        # five tables and the vector store, so it is not a read by any measure.
        if request.method == "DELETE":
            return "expensive", self.write_limit
        # Exports read the whole index (and possibly every uploaded PDF), so a
        # GET to one costs far more than an ordinary read.
        if path.endswith("/export"):
            return "expensive", self.write_limit
        if request.method in ("POST", "PUT", "PATCH") and any(
            path.endswith(suffix) for suffix in self.expensive_suffixes
        ):
            return "expensive", self.write_limit
        return "read", self.read_limit

    def _evict_idle(self, now: float) -> None:
        """Drop counters for clients that have gone quiet.

        Without this, every distinct client address that ever hit the process
        keeps a deque forever — a slow leak that a scanner sweeping source
        addresses turns into a fast one. Called under the lock.
        """
        if len(self._hits) < self.EVICT_ABOVE:
            return
        cutoff = now - self.window_seconds
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]

    def _take(self, key: tuple[str, str], limit: int, now: float) -> tuple[bool, float]:
        """Record a hit. Returns (allowed, seconds until the window frees up)."""
        with self._lock:
            self._evict_idle(now)
            hits = self._hits.setdefault(key, deque())
            cutoff = now - self.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= limit:
                return False, max(0.0, hits[0] + self.window_seconds - now)

            hits.append(now)
            return True, 0.0

    # ------------------------------------------------------------------
    async def dispatch(self, request: Request, call_next):
        # A liveness probe must never be the thing that trips the limiter.
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        bucket, limit = self._bucket(request)
        allowed, retry_after = self._take(
            (self._client(request), bucket), limit, time.monotonic()
        )

        if not allowed:
            logger.warning(
                json.dumps(
                    {
                        "event": "rate_limited",
                        "client": self._client(request),
                        "path": request.url.path,
                        "bucket": bucket,
                        "limit": limit,
                    }
                )
            )
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(int(retry_after) + 1)},
                content={
                    "detail": (
                        f"Too many requests: the limit is {limit} per "
                        f"{int(self.window_seconds)}s for this kind of endpoint. "
                        f"Try again in {int(retry_after) + 1}s."
                    )
                },
            )

        return await call_next(request)

    def reset(self) -> None:
        """Clear every counter (tests, and a manual reset in development)."""
        with self._lock:
            self._hits.clear()

    @classmethod
    def reset_all(cls) -> None:
        """Clear the counters of every limiter built in this process."""
        for instance in cls._instances:
            instance.reset()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """One structured JSON line per request, with a correlation id.

    The id is echoed back as ``X-Request-ID`` so a failure a user reports can
    be found in the log without guessing from timestamps. A client-supplied
    ``X-Request-ID`` is honoured — but truncated, because it ends up in log
    output and must not be able to carry an arbitrarily long payload there.
    """

    MAX_ID_LENGTH = 64

    async def dispatch(self, request: Request, call_next):
        supplied = request.headers.get("x-request-id", "")
        request_id = (
            "".join(ch for ch in supplied if ch.isalnum() or ch in "-_")[: self.MAX_ID_LENGTH]
            or uuid.uuid4().hex[:12]
        )
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            logger.exception(
                json.dumps(
                    {
                        "event": "request_failed",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "error": f"{type(exc).__name__}: {exc}",
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                )
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-ID"] = request_id

        logger.info(
            json.dumps(
                {
                    "event": "request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "client": request.client.host if request.client else "unknown",
                }
            )
        )
        return response


def configure_logging(level: str = "INFO") -> None:
    """Send this app's logs to stdout as one line each.

    Kept deliberately small: no file handlers, no rotation, no third-party
    logging framework. Whatever runs the process (uvicorn in development, a
    supervisor elsewhere) is what should own log destinations.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    app_logger = logging.getLogger("mairos")
    app_logger.handlers = [handler]
    app_logger.setLevel(level.upper())
    # Uvicorn already logs access lines; ours carry the correlation id and the
    # duration, so leaving both on would double every request in the output.
    app_logger.propagate = False


__all__ = [
    "RateLimitMiddleware",
    "RequestLoggingMiddleware",
    "RequestSizeLimitMiddleware",
    "configure_logging",
]
