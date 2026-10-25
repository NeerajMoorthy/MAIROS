"""Baseline HTTP hardening: size caps, rate limiting, CORS, logging, outages.

These assert the middleware's behaviour directly rather than through the shared
``client`` fixture, because that fixture resets the rate limiter on purpose —
every other test in the suite would otherwise start failing on 429s once the
session's write budget ran out.
"""

from __future__ import annotations

import io
import json
import logging
import socket

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.errors import (
    OutageMiddleware,
    ServiceUnavailable,
    failing_service,
    install_error_handlers,
    looks_like_an_outage,
)
from app.middleware import (
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    RequestSizeLimitMiddleware,
)


def tiny_app() -> FastAPI:
    """A minimal app so each test exercises one middleware in isolation."""
    app = FastAPI()

    @app.get("/api/thing")
    async def read() -> dict:
        return {"ok": True}

    @app.post("/api/projects/p1/tasks")
    async def start_task() -> dict:
        return {"started": True}

    @app.post("/api/projects/p1/documents")
    async def upload() -> dict:
        return {"uploaded": True}

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


# ---------------------------------------------------------------------------
# Request size
# ---------------------------------------------------------------------------
class TestRequestSizeCap:
    def test_an_oversized_json_body_is_rejected_with_413(self):
        app = tiny_app()
        app.add_middleware(RequestSizeLimitMiddleware, max_json_bytes=1024)
        client = TestClient(app)

        response = client.post("/api/projects/p1/tasks", content=b"x" * 4096)

        assert response.status_code == 413
        assert "over the" in response.json()["detail"]

    def test_the_body_is_refused_from_the_header_not_after_reading_it(self):
        """The point of the cap is to refuse before anything buffers the body."""
        app = tiny_app()
        reads: list[int] = []

        @app.post("/api/echo")
        async def echo(payload: dict) -> dict:  # pragma: no cover - must not run
            reads.append(len(str(payload)))
            return {}

        app.add_middleware(RequestSizeLimitMiddleware, max_json_bytes=64)
        client = TestClient(app)

        response = client.post("/api/echo", content=b"y" * 5000)

        assert response.status_code == 413
        assert reads == [], "the handler must never have been reached"

    def test_uploads_get_the_larger_cap(self):
        app = tiny_app()
        app.add_middleware(
            RequestSizeLimitMiddleware, max_json_bytes=1024, max_upload_bytes=1024 * 1024
        )
        client = TestClient(app)

        # Over the JSON cap, under the upload cap.
        response = client.post(
            "/api/projects/p1/documents",
            files={"file": ("p.pdf", io.BytesIO(b"z" * 40_000), "application/pdf")},
        )
        assert response.status_code == 200

    def test_a_body_within_the_cap_passes_through(self):
        app = tiny_app()
        app.add_middleware(RequestSizeLimitMiddleware, max_json_bytes=4096)
        client = TestClient(app)

        assert client.post("/api/projects/p1/tasks", content=b"x" * 100).status_code == 200

    def test_a_malformed_content_length_is_a_400_not_a_crash(self):
        middleware = RequestSizeLimitMiddleware(tiny_app(), max_json_bytes=1024)
        assert middleware.limit_for("/api/projects/p1/documents") == 40 * 1024 * 1024
        assert middleware.limit_for("/api/projects/p1/tasks") == 1024


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
class TestRateLimiting:
    def test_the_expensive_budget_is_enforced_and_reports_retry_after(self):
        app = tiny_app()
        app.add_middleware(RateLimitMiddleware, read_limit=100, write_limit=3)
        client = TestClient(app)

        codes = [client.post("/api/projects/p1/tasks").status_code for _ in range(5)]

        assert codes == [200, 200, 200, 429, 429]
        blocked = client.post("/api/projects/p1/tasks")
        assert int(blocked.headers["Retry-After"]) >= 1
        assert "Too many requests" in blocked.json()["detail"]

    def test_reads_are_not_charged_to_the_expensive_budget(self):
        """A user browsing results must not be locked out by their own reads."""
        app = tiny_app()
        app.add_middleware(RateLimitMiddleware, read_limit=50, write_limit=2)
        client = TestClient(app)

        for _ in range(20):
            assert client.get("/api/thing").status_code == 200

        assert client.post("/api/projects/p1/tasks").status_code == 200

    def test_exhausting_the_write_budget_leaves_reads_working(self):
        app = tiny_app()
        app.add_middleware(RateLimitMiddleware, read_limit=50, write_limit=1)
        client = TestClient(app)

        assert client.post("/api/projects/p1/tasks").status_code == 200
        assert client.post("/api/projects/p1/tasks").status_code == 429
        # The UI polls task status while a run is in flight; if a 429 on the
        # start also blocked polling, the user would lose sight of the run.
        assert client.get("/api/thing").status_code == 200

    def test_health_is_never_rate_limited(self):
        """A liveness probe being throttled would look like an outage."""
        app = tiny_app()
        app.add_middleware(RateLimitMiddleware, read_limit=2, write_limit=1)
        client = TestClient(app)

        for _ in range(10):
            assert client.get("/api/health").status_code == 200

    def test_the_window_slides_so_a_client_is_not_locked_out_forever(self):
        limiter = RateLimitMiddleware(tiny_app(), read_limit=2, write_limit=2, window_seconds=10)

        assert limiter._take(("a", "read"), 2, now=100.0) == (True, 0.0)
        assert limiter._take(("a", "read"), 2, now=100.5)[0] is True
        assert limiter._take(("a", "read"), 2, now=101.0)[0] is False

        # Once the first hit ages out of the window, capacity returns.
        assert limiter._take(("a", "read"), 2, now=111.0)[0] is True

    def test_clients_are_counted_separately(self):
        limiter = RateLimitMiddleware(tiny_app(), window_seconds=10)

        assert limiter._take(("a", "expensive"), 1, now=0.0)[0] is True
        assert limiter._take(("a", "expensive"), 1, now=0.1)[0] is False
        assert limiter._take(("b", "expensive"), 1, now=0.2)[0] is True

    def test_reset_clears_the_counters(self):
        limiter = RateLimitMiddleware(tiny_app(), window_seconds=10)
        limiter._take(("a", "read"), 1, now=0.0)
        assert limiter._take(("a", "read"), 1, now=0.1)[0] is False

        limiter.reset()
        assert limiter._take(("a", "read"), 1, now=0.2)[0] is True


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
class TestRequestLogging:
    def test_every_response_carries_a_request_id(self):
        app = tiny_app()
        app.add_middleware(RequestLoggingMiddleware)
        client = TestClient(app)

        response = client.get("/api/thing")
        assert response.headers["X-Request-ID"]

    def test_a_supplied_request_id_is_echoed_back(self):
        app = tiny_app()
        app.add_middleware(RequestLoggingMiddleware)
        client = TestClient(app)

        response = client.get("/api/thing", headers={"X-Request-ID": "run-42"})
        assert response.headers["X-Request-ID"] == "run-42"

    def test_a_hostile_request_id_is_sanitised_before_it_reaches_the_log(self):
        """The id is written to log output, so it must not carry a payload."""
        app = tiny_app()
        app.add_middleware(RequestLoggingMiddleware)
        client = TestClient(app)

        response = client.get(
            "/api/thing",
            headers={"X-Request-ID": "abc\ndef INJECTED LOG LINE " + "x" * 500},
        )
        returned = response.headers["X-Request-ID"]

        assert "\n" not in returned
        assert " " not in returned
        assert len(returned) <= RequestLoggingMiddleware.MAX_ID_LENGTH

    def test_the_log_line_is_parseable_json_with_the_facts_worth_having(self):
        """Captured with a handler attached directly to the app's logger.

        ``configure_logging`` sets ``propagate = False`` on the ``mairos``
        logger so that our lines and uvicorn's access lines do not both appear
        for every request. pytest's ``caplog`` listens on the root logger, so
        it sees nothing once the real app's lifespan has run — which happens
        as soon as any other test in the session builds a TestClient.
        """
        records: list[logging.LogRecord] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        app = tiny_app()
        app.add_middleware(RequestLoggingMiddleware)
        client = TestClient(app)

        http_logger = logging.getLogger("mairos.http")
        handler = Capture()
        previous_level = http_logger.level
        http_logger.addHandler(handler)
        http_logger.setLevel(logging.INFO)
        try:
            client.get("/api/thing", headers={"X-Request-ID": "trace1"})
        finally:
            http_logger.removeHandler(handler)
            http_logger.setLevel(previous_level)

        entries = [
            json.loads(record.getMessage())
            for record in records
            if record.getMessage().startswith("{")
        ]
        entry = next(e for e in entries if e.get("event") == "request")

        assert entry["request_id"] == "trace1"
        assert entry["method"] == "GET"
        assert entry["path"] == "/api/thing"
        assert entry["status"] == 200
        assert entry["duration_ms"] >= 0


# ---------------------------------------------------------------------------
# Outage handling
# ---------------------------------------------------------------------------
class TestOutageHandling:
    @pytest.mark.parametrize(
        "exc",
        [
            ConnectionError("refused"),
            ConnectionRefusedError("nothing listening"),
            ConnectionResetError("peer reset"),
            TimeoutError("slow"),
            socket.gaierror("name resolution failed"),
        ],
    )
    def test_connection_failures_are_recognised(self, exc):
        assert looks_like_an_outage(exc) is True

    @pytest.mark.parametrize(
        "exc",
        [
            OSError("no route"),
            FileNotFoundError("cache.json"),
            PermissionError("data dir"),
            IsADirectoryError("path"),
        ],
    )
    def test_filesystem_errors_are_not_treated_as_outages(self, exc):
        """`isinstance(exc, OSError)` was too wide and caught all of these.

        A missing optional file or an unwritable directory is a bug or a
        misconfiguration, not a service that will be back shortly. Answering
        503 with `Retry-After` sends the reporter off to retry for an afternoon.
        """
        assert isinstance(exc, OSError)
        assert looks_like_an_outage(exc) is False

    def test_a_handled_file_error_does_not_poison_later_exceptions(self):
        """The implicit `__context__` chain made any later bug a 503.

        Python sets `__context__` for *any* exception raised inside *any*
        `except` block, so one `try/except FileNotFoundError` around an
        optional-file lookup upstream turned every subsequent exception in that
        handler into a dependency outage.
        """
        try:
            try:
                raise FileNotFoundError("optional cache missing")
            except FileNotFoundError:
                raise KeyError("document_name")  # the actual bug
        except KeyError as exc:
            assert exc.__context__ is not None, "the implicit chain is present"
            assert looks_like_an_outage(exc) is False

    def test_a_third_party_client_error_is_recognised_by_name(self):
        """httpx and Chroma exceptions do not derive from the stdlib types."""

        class ConnectTimeout(Exception):  # mirrors httpx.ConnectTimeout
            pass

        class ChromaConnectionError(Exception):
            pass

        assert looks_like_an_outage(ConnectTimeout("no response")) is True
        assert looks_like_an_outage(ChromaConnectionError("down")) is True

    def test_an_http_error_is_not_an_outage(self):
        """requests raises HTTPError for a 401 — a bad key, not a dead service."""

        class HTTPError(Exception):
            pass

        assert looks_like_an_outage(HTTPError("401 Unauthorized")) is False

    def test_the_failing_service_is_named_from_the_exception(self):
        """Sending someone to check their disk over a bad API key wastes a day."""

        class ConnectError(Exception):
            pass

        assert failing_service(ConnectError("connection to api.groq.com failed")) == "llm"
        assert failing_service(ConnectError("chroma collection unavailable")) == "vector-store"
        # Unattributable failures default to the dependency every request touches.
        assert failing_service(ConnectionError("connection refused")) == "vector-store"

    def test_an_llm_outage_gets_llm_advice_not_disk_advice(self):
        app = tiny_app()

        class ConnectError(Exception):
            pass

        @app.get("/api/llm-down")
        async def llm_down():
            raise ConnectError("All connection attempts to api.groq.com failed")

        app.add_middleware(OutageMiddleware)
        app.add_middleware(RequestLoggingMiddleware)
        client = TestClient(app, raise_server_exceptions=False)

        body = client.get("/api/llm-down").json()
        assert body["service"] == "llm"
        assert "GROQ_API_KEY" in body["detail"]
        assert "data directory" not in body["detail"]

    def test_an_ordinary_bug_is_not_mistaken_for_an_outage(self):
        """Dressing a KeyError up as a 503 would send users into retry loops."""
        assert looks_like_an_outage(KeyError("chunk_id")) is False
        assert looks_like_an_outage(ValueError("bad flow")) is False

    def test_a_cyclic_exception_chain_terminates(self):
        first, second = RuntimeError("a"), RuntimeError("b")
        first.__cause__ = second
        second.__cause__ = first
        assert looks_like_an_outage(first) is False

    def test_a_dependency_outage_becomes_a_503_with_advice(self):
        app = tiny_app()

        @app.get("/api/boom")
        async def boom():
            raise ConnectionError("chroma refused the connection")

        app.add_middleware(OutageMiddleware)
        app.add_middleware(RequestLoggingMiddleware)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/api/boom")

        assert response.status_code == 503
        assert response.headers["Retry-After"] == "30"
        body = response.json()
        assert body["service"] == "vector-store"
        assert "not reachable" in body["detail"]
        assert body["request_id"]

    def test_an_explicit_service_unavailable_names_the_service(self):
        app = tiny_app()

        @app.get("/api/llm")
        async def needs_llm():
            raise ServiceUnavailable("llm", "Set GROQ_API_KEY and retry.")

        app.add_middleware(RequestLoggingMiddleware)
        install_error_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/api/llm")
        assert response.status_code == 503
        assert response.json()["service"] == "llm"
        assert response.json()["detail"] == "Set GROQ_API_KEY and retry."

    def test_a_real_bug_stays_a_500_and_does_not_leak_the_stack(self):
        app = tiny_app()

        @app.get("/api/bug")
        async def bug():
            raise KeyError("document_name")

        app.add_middleware(OutageMiddleware)
        app.add_middleware(RequestLoggingMiddleware)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/api/bug")
        body = response.json()

        assert response.status_code == 500
        assert "document_name" not in json.dumps(body)
        assert "Traceback" not in json.dumps(body)
        assert body["request_id"]


# ---------------------------------------------------------------------------
# CORS and configuration, on the real app
# ---------------------------------------------------------------------------
class TestConfiguredCors:
    def test_origins_are_an_explicit_list_never_a_wildcard(self):
        from app.config import settings

        assert settings.cors_origins, "an empty origin list would block the frontend"
        assert "*" not in settings.cors_origins

    def test_credentials_are_off_because_there_is_no_auth(self):
        from app.config import settings

        assert settings.cors_allow_credentials is False

    def test_methods_and_headers_are_enumerated_rather_than_wildcarded(self):
        from app.config import settings

        assert "*" not in settings.cors_allow_methods
        assert "*" not in settings.cors_allow_headers
        assert "GET" in settings.cors_allow_methods

    def test_a_configured_origin_is_allowed(self, client):
        response = client.get(
            "/api/health", headers={"Origin": "http://localhost:3000"}
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_an_unknown_origin_gets_no_allow_header(self):
        """The browser blocks the response when the header is absent."""
        from main import app

        with TestClient(app) as client:
            response = client.get(
                "/api/health", headers={"Origin": "https://evil.example.com"}
            )

        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers

    def test_a_preflight_from_an_unknown_origin_is_refused(self):
        from main import app

        with TestClient(app) as client:
            response = client.options(
                "/api/projects",
                headers={
                    "Origin": "https://evil.example.com",
                    "Access-Control-Request-Method": "POST",
                },
            )

        assert "access-control-allow-origin" not in response.headers


class TestTheRealAppIsWiredUp:
    def test_the_live_app_stamps_a_request_id(self, client):
        assert client.get("/api/health").headers["X-Request-ID"]

    def test_the_live_app_caps_request_bodies(self, client):
        from app.config import settings

        response = client.post(
            "/api/projects",
            content=b"x" * (settings.max_request_bytes + 1024),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413

    def test_the_live_app_rate_limits_task_creation(self, client):
        from app.config import settings

        project_id = client.post("/api/projects", json={"name": "Limits"}).json()["id"]

        codes = [
            client.post(
                f"/api/projects/{project_id}/tasks",
                json={"question": f"question {index}", "flow": "answer"},
            ).status_code
            for index in range(settings.rate_limit_writes + 3)
        ]

        assert 429 in codes, "the write budget must actually bite"
        assert codes[0] == 201, "the first request must not be limited"

    def test_every_middleware_is_registered_on_the_real_app(self):
        from main import app

        registered = {middleware.cls.__name__ for middleware in app.user_middleware}
        assert {
            "RequestLoggingMiddleware",
            "RequestSizeLimitMiddleware",
            "RateLimitMiddleware",
            "CORSMiddleware",
        } <= registered

    def test_the_middleware_order_is_the_one_the_comment_claims(self):
        from main import app

        names = [middleware.cls.__name__ for middleware in app.user_middleware]
        # Starlette stores middleware most-recently-added first and runs that
        # one outermost, so this list is already outermost-first.
        assert names == [
            "CORSMiddleware",          # outermost: every response gets ACAO
            "RequestLoggingMiddleware",  # every request gets an id, even rejected ones
            "OutageMiddleware",        # catches what the route raises
            "RequestSizeLimitMiddleware",
            "RateLimitMiddleware",
        ], names


# ---------------------------------------------------------------------------
# The two regressions the reorder and the stream metering exist to prevent
# ---------------------------------------------------------------------------
class TestRejectionsReachTheBrowser:
    """Every rejection must carry CORS headers, or the frontend cannot read it.

    With `CORSMiddleware` added first (innermost), a 413/429/503/500 produced
    above it had no `Access-Control-Allow-Origin`, so the browser blocked the
    response and the UI showed `TypeError: Failed to fetch` instead of the
    message. The messages are the whole point of writing them carefully.
    """

    ORIGIN = "http://localhost:3000"

    def _app_response(self, path: str, **kwargs):
        from main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            from app.middleware import RateLimitMiddleware

            RateLimitMiddleware.reset_all()
            headers = {"Origin": self.ORIGIN, **kwargs.pop("headers", {})}
            return client.post(path, headers=headers, **kwargs)

    def test_a_413_carries_the_cors_header(self):
        from app.config import settings

        response = self._app_response(
            "/api/projects",
            content=b"x" * (settings.max_request_bytes + 2048),
            headers={"Origin": self.ORIGIN, "Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert response.headers.get("access-control-allow-origin") == self.ORIGIN

    def test_a_429_carries_the_cors_header_and_its_retry_hint(self, client):
        from app.config import settings
        from main import app

        project_id = client.post("/api/projects", json={"name": "CORS limits"}).json()["id"]

        last = None
        for index in range(settings.rate_limit_writes + 3):
            last = client.post(
                f"/api/projects/{project_id}/tasks",
                headers={"Origin": self.ORIGIN},
                json={"question": f"q{index}", "flow": "answer"},
            )
            if last.status_code == 429:
                break

        assert last is not None and last.status_code == 429
        assert last.headers.get("access-control-allow-origin") == self.ORIGIN
        assert last.headers.get("Retry-After")

    def test_retry_after_is_exposed_to_the_browser(self):
        from main import app

        with TestClient(app) as client:
            response = client.get("/api/health", headers={"Origin": self.ORIGIN})

        exposed = response.headers.get("access-control-expose-headers", "")
        assert "X-Request-ID" in exposed
        assert "Retry-After" in exposed


class TestChunkedBodiesCannotBypassTheCap:
    """`Content-Length` is absent on a chunked request, and uvicorn accepts it.

    A header-only check let a chunked body straight through to the very
    `await file.read()` the middleware was written to get in front of.
    """

    @staticmethod
    def _chunked(limit: int, body: bytes):
        """Drive the ASGI app directly with a body and no Content-Length."""
        import anyio

        app = tiny_app()

        @app.post("/api/echo")
        async def echo(request: Request) -> dict:
            data = await request.body()
            return {"read": len(data)}

        wrapped = RequestSizeLimitMiddleware(app, max_json_bytes=limit)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/echo",
            "raw_path": b"/api/echo",
            "query_string": b"",
            "root_path": "",
            "scheme": "http",
            "headers": [(b"host", b"testserver"), (b"transfer-encoding", b"chunked")],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }

        chunks = [body[i : i + 8192] for i in range(0, len(body), 8192)] or [b""]
        pending = [
            {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
            for index, chunk in enumerate(chunks)
        ]
        sent: list[dict] = []

        async def receive():
            return pending.pop(0) if pending else {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        anyio.run(wrapped, scope, receive, send)
        start = next(m for m in sent if m["type"] == "http.response.start")
        return start["status"]

    def test_a_chunked_body_over_the_cap_is_still_refused(self):
        assert self._chunked(limit=1024, body=b"x" * 500_000) == 413

    def test_a_chunked_body_under_the_cap_still_works(self):
        assert self._chunked(limit=1024 * 1024, body=b"y" * 5_000) == 200

    def test_a_lying_content_length_does_not_get_past_the_meter(self):
        """Declaring 10 bytes and sending 500 KB is metered on the way in."""
        import anyio

        app = tiny_app()

        @app.post("/api/echo")
        async def echo(request: Request) -> dict:
            return {"read": len(await request.body())}

        wrapped = RequestSizeLimitMiddleware(app, max_json_bytes=1024)
        body = b"z" * 500_000
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/echo",
            "raw_path": b"/api/echo",
            "query_string": b"",
            "root_path": "",
            "scheme": "http",
            "headers": [(b"host", b"testserver"), (b"content-length", b"10")],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }
        pending = [{"type": "http.request", "body": body, "more_body": False}]
        sent: list[dict] = []

        async def receive():
            return pending.pop(0) if pending else {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        anyio.run(wrapped, scope, receive, send)
        status = next(m for m in sent if m["type"] == "http.response.start")["status"]
        assert status == 413

    def test_a_negative_content_length_is_rejected(self):
        app = tiny_app()
        app.add_middleware(RequestSizeLimitMiddleware, max_json_bytes=1024)
        client = TestClient(app)

        response = client.post(
            "/api/projects/p1/tasks",
            content=b"x" * 10,
            headers={"Content-Length": "-5"},
        )
        assert response.status_code == 400


class TestRateLimitBudgetGaps:
    def test_retrieve_draws_on_the_expensive_budget(self):
        """It runs a full embedding pass — the cost the write budget exists for."""
        app = tiny_app()

        @app.post("/api/projects/p1/retrieve")
        async def retrieve() -> dict:
            return {"ok": True}

        app.add_middleware(RateLimitMiddleware, read_limit=100, write_limit=2)
        client = TestClient(app)

        codes = [client.post("/api/projects/p1/retrieve").status_code for _ in range(4)]
        assert codes == [200, 200, 429, 429]

    def test_delete_draws_on_the_expensive_budget(self):
        """Deleting a project cascades across five tables and the vector store."""
        app = tiny_app()

        @app.delete("/api/projects/p1")
        async def remove() -> dict:
            return {"deleted": True}

        app.add_middleware(RateLimitMiddleware, read_limit=100, write_limit=1)
        client = TestClient(app)

        assert client.delete("/api/projects/p1").status_code == 200
        assert client.delete("/api/projects/p1").status_code == 429

    def test_only_the_real_health_paths_are_exempt(self):
        """A suffix match exempted `/anything/health`, including unrouted paths."""
        app = tiny_app()

        @app.get("/api/projects/p1/health")
        async def fake_health() -> dict:
            return {"status": "ok"}

        app.add_middleware(RateLimitMiddleware, read_limit=3, write_limit=1)
        client = TestClient(app)

        # The real probe is never limited...
        assert all(client.get("/api/health").status_code == 200 for _ in range(10))

        # ...but a path that merely ends in /health is.
        codes = [client.get("/api/projects/p1/health").status_code for _ in range(6)]
        assert 429 in codes

        # Including one that does not route at all, which would otherwise be a
        # free unlimited endpoint for anyone who noticed.
        app2 = tiny_app()
        app2.add_middleware(RateLimitMiddleware, read_limit=2, write_limit=1)
        client2 = TestClient(app2)
        codes = [client2.get("/zzz/health").status_code for _ in range(5)]
        assert 429 in codes

    def test_idle_clients_are_evicted_so_the_counter_table_cannot_grow_forever(self):
        limiter = RateLimitMiddleware(tiny_app(), window_seconds=10)

        for index in range(limiter.EVICT_ABOVE + 50):
            limiter._take((f"client-{index}", "read"), 100, now=0.0)
        assert len(limiter._hits) > limiter.EVICT_ABOVE

        # One request much later sweeps everything that has gone quiet.
        limiter._take(("still-here", "read"), 100, now=1000.0)
        assert len(limiter._hits) == 1
