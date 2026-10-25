"""Application configuration loaded from environment variables.

All values can be overridden via environment variables or a ``.env`` file
placed at the repository root (``mairos/.env``).  See ``.env.example``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# mairos/apps/api/app/config.py -> parents[3] == mairos/
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "apps" / "api" / "data"


class Settings(BaseSettings):
    """Application configuration and environment variables."""

    # ------------------------------------------------------------------
    # Storage paths (absolute, so behaviour does not depend on cwd)
    # ------------------------------------------------------------------
    # Setting DATA_DIR alone moves everything below it (a Fly.io volume mounted
    # at /data, say); each sub-path can still be overridden on its own.
    data_dir: Path = DATA_DIR
    upload_dir: Path = DATA_DIR / "uploads"
    chroma_persist_dir: Path = DATA_DIR / "chroma"
    graph_dir: Path = DATA_DIR / "graphs"
    # SQLite is the store of record unless DATABASE_URL points at Postgres;
    # state.json is only read once, to migrate data written by the earlier
    # snapshot-based build.
    database_file: Path = DATA_DIR / "mairos.db"
    state_file: Path = DATA_DIR / "state.json"

    # ------------------------------------------------------------------
    # Metadata database
    # ------------------------------------------------------------------
    # Empty: SQLite at `database_file` (local-first default). A postgres://
    # URL — e.g. a Supabase connection string — moves projects, documents,
    # papers, patents and tasks into Postgres behind the same store surface.
    database_url: str = ""

    # ------------------------------------------------------------------
    # Authentication (optional)
    # ------------------------------------------------------------------
    # Empty: single-user local mode, exactly as before — no login, every
    # project visible. Set to the frontend's Better Auth JWKS endpoint
    # (https://<site>/api/auth/jwks) to require a signed bearer token on every
    # API call and scope projects to the user who created them.
    auth_jwks_url: str = ""
    # Better Auth's JWT plugin uses the site's base URL for both by default.
    auth_issuer: str = ""
    auth_audience: str = ""
    auth_jwks_cache_seconds: int = 600

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------
    # False: each agent run gets its own thread so the server stays
    # responsive. True: runs as a FastAPI background task, which the test
    # client completes before returning (the test suite sets this).
    run_tasks_inline: bool = False

    # ------------------------------------------------------------------
    # LLM — Groq (https://console.groq.com)
    # ------------------------------------------------------------------
    # NEVER hardcode a key here. Set GROQ_API_KEY in mairos/.env
    groq_api_key: str = ""
    # Production model IDs: llama-3.3-70b-versatile, llama-3.1-8b-instant,
    # openai/gpt-oss-120b. (llama-3.1-70b-versatile was decommissioned.)
    default_llm: str = "llama-3.3-70b-versatile"
    # Cheaper/faster model used for structured extraction (KG, routing).
    fast_llm: str = "llama-3.1-8b-instant"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1400
    # Knowledge-graph extraction gets its own, larger budget. Its output is a
    # JSON list of up to 12 entities and 12 relations, and a reasoning model
    # (gpt-oss) spends hundreds of hidden tokens before writing any of it: a
    # live run used 1,156 of 1,400 tokens on a 330-character input, and the
    # real 1,600-1,800-character inputs ran out mid-JSON, so every analysis
    # added nothing to the graph.
    llm_extraction_max_tokens: int = 4096
    # Every other agent keeps the smaller default, but a reply that reaches it
    # (finish_reason "length") is retried once with this budget rather than
    # handed on as truncated JSON. See BaseAgent.invoke_llm.
    llm_retry_max_tokens: int = 4096
    # When no key is configured, fall back to a deterministic offline model
    # so the demo degrades gracefully instead of crashing.
    allow_offline_llm: bool = True

    # ------------------------------------------------------------------
    # ChromaDB
    # ------------------------------------------------------------------
    chroma_collection: str = "mairos_chunks"

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # ------------------------------------------------------------------
    # Chunking / retrieval
    # ------------------------------------------------------------------
    chunk_size: int = 512
    chunk_overlap: int = 64
    default_top_k: int = 5

    # ------------------------------------------------------------------
    # Literature retrieval
    # ------------------------------------------------------------------
    # Sources searched, in order. Any of: arxiv, openalex, semantic_scholar.
    literature_sources: str = "arxiv,openalex,semantic_scholar"
    # Papers kept after merging every source and query.
    literature_max_results: int = 8
    # Queries per search, and results requested per query per source.
    literature_query_count: int = 4
    literature_per_query: int = 5
    # Optional: joins OpenAlex's faster "polite pool". An email address.
    openalex_mailto: str = ""
    # Optional: lifts Semantic Scholar's shared public rate limit.
    semantic_scholar_api_key: str = ""
    # Per-request timeout, in seconds, for every source. (Replaces the
    # arXiv-only ARXIV_MAX_RESULTS / ARXIV_TIMEOUT, which are no longer read.)
    literature_timeout: float = 20.0

    @property
    def literature_source_list(self) -> list[str]:
        return [s.strip() for s in self.literature_sources.split(",") if s.strip()]

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    # Explicit origins only — never "*". Override with MAIROS_CORS_ORIGINS
    # (or CORS_ORIGINS) when the frontend is served from somewhere else.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ]
    # MAIROS has no auth and sets no cookies, so the browser never needs to
    # attach credentials. Leaving this on would widen the origin check for no
    # benefit, so it is off and configurable rather than hardcoded on.
    cors_allow_credentials: bool = False
    cors_allow_methods: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    # Authorization carries the Better Auth bearer token when auth is enabled.
    cors_allow_headers: list[str] = ["Content-Type", "X-Request-ID", "Authorization"]

    # ------------------------------------------------------------------
    # HTTP hardening
    # ------------------------------------------------------------------
    # Fixed-window rate limits, per client address, per worker process.
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: float = 60.0
    rate_limit_reads: int = 240
    # Anything that starts agent work costs an LLM round trip and an embedding
    # pass, so it gets a much smaller budget than a read.
    rate_limit_writes: int = 20
    # Request body caps. The upload cap matches the one the ingest route
    # already enforced; the difference is that this one is checked from
    # Content-Length before the body is read into memory.
    max_request_bytes: int = 1 * 1024 * 1024
    max_upload_bytes: int = 40 * 1024 * 1024

    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _derive_storage_paths(self) -> "Settings":
        """Place unset sub-paths under a relocated ``data_dir``."""
        if "data_dir" in self.model_fields_set:
            for name, leaf in (
                ("upload_dir", "uploads"),
                ("chroma_persist_dir", "chroma"),
                ("graph_dir", "graphs"),
                ("database_file", "mairos.db"),
                ("state_file", "state.json"),
            ):
                if name not in self.model_fields_set:
                    setattr(self, name, Path(self.data_dir) / leaf)
        return self

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_jwks_url.strip())

    @property
    def uses_postgres(self) -> bool:
        return self.database_url.strip().lower().startswith(("postgres://", "postgresql://"))

    def ensure_dirs(self) -> None:
        """Create every directory the application writes to."""
        for path in (
            self.data_dir,
            self.upload_dir,
            self.chroma_persist_dir,
            self.graph_dir,
        ):
            Path(path).mkdir(parents=True, exist_ok=True)


settings = Settings()
