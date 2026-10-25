"""SQLite persistence for the metadata store.

**Why a document table rather than a normalised schema.** Every read in MAIROS
goes through the store's in-memory cache — nothing queries metadata
relationally, and the only filters are "by project" and "newest first". A
normalised schema would therefore buy nothing and cost a migration every time a
Pydantic model gains a field. Each row keeps its model as JSON with the two
columns anything actually filters on (``project_id``, ``created_at``) lifted out
and indexed.

**What this replaces.** The previous snapshot rewrote the entire state file on
every mutation, which meant a crash mid-write could truncate everything and two
concurrent writers could lose each other's changes. Here each mutation is one
transaction against one row, with WAL enabled so a reader never blocks a writer.

The connection is per-thread: FastAPI runs blocking work in a threadpool, and
sharing one SQLite connection across threads is exactly the pattern that raises
``ProgrammingError: SQLite objects created in a thread can only be used in that
same thread``.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Iterable

# One table per entity; all share the same shape. Both backends create any
# missing table on open (CREATE TABLE IF NOT EXISTS), which is the whole
# migration path when one is added — `evaluations` was, for the export.
TABLES = ("projects", "documents", "papers", "patents", "tasks", "evaluations")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    id          TEXT PRIMARY KEY,
    project_id  TEXT,
    created_at  TEXT,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{table}_project ON {table} (project_id);
CREATE INDEX IF NOT EXISTS idx_{table}_created ON {table} (created_at);
"""

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    """A tiny document store over SQLite.

    Args:
        path: Database file. Parent directories are created on demand.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        # A separate lock: `connection` is called from inside `_write_lock` by
        # every mutating method, and `threading.Lock` is not reentrant, so
        # reusing the write lock here would deadlock the first write on a new
        # thread.
        self._registry_lock = threading.Lock()
        # Every connection ever opened, so `close()` can actually close them.
        # Closing only the calling thread's left one open file descriptor per
        # threadpool thread, and `use_database` then drops the Database object,
        # making them unreachable and leaking for the life of each thread.
        self._connections: list[sqlite3.Connection] = []
        self._initialise()

    # ------------------------------------------------------------------
    @property
    def connection(self) -> sqlite3.Connection:
        """The calling thread's connection, opened on first use."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
            conn.row_factory = sqlite3.Row
            # WAL lets readers proceed during a write; NORMAL is the usual
            # durability/speed trade-off to pair with it.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
            with self._registry_lock:
                self._connections.append(conn)
        return conn

    def _initialise(self) -> None:
        conn = self.connection
        with self._write_lock:
            conn.executescript(
                _META_SCHEMA + "".join(_SCHEMA.format(table=t) for t in TABLES)
            )

    # ------------------------------------------------------------------
    def upsert(
        self,
        table: str,
        record_id: str,
        payload: dict,
        project_id: str | None = None,
        created_at: str | None = None,
    ) -> None:
        """Insert or replace one record."""
        if table not in TABLES:
            raise ValueError(f"unknown table: {table}")

        with self._write_lock:
            self.connection.execute(
                f"INSERT INTO {table} (id, project_id, created_at, payload) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "project_id=excluded.project_id, "
                "created_at=excluded.created_at, "
                "payload=excluded.payload",
                (record_id, project_id, created_at, json.dumps(payload)),
            )

    def upsert_many(self, table: str, rows: Iterable[tuple[str, dict, str | None, str | None]]) -> int:
        """Insert or replace many records in one transaction."""
        if table not in TABLES:
            raise ValueError(f"unknown table: {table}")

        prepared = [
            (record_id, project_id, created_at, json.dumps(payload))
            for record_id, payload, project_id, created_at in rows
        ]
        if not prepared:
            return 0

        with self._write_lock:
            conn = self.connection
            conn.execute("BEGIN")
            try:
                conn.executemany(
                    f"INSERT INTO {table} (id, project_id, created_at, payload) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "project_id=excluded.project_id, "
                    "created_at=excluded.created_at, "
                    "payload=excluded.payload",
                    prepared,
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return len(prepared)

    def delete(self, table: str, record_id: str) -> bool:
        if table not in TABLES:
            raise ValueError(f"unknown table: {table}")
        with self._write_lock:
            cursor = self.connection.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
        return cursor.rowcount > 0

    def delete_by_project(self, table: str, project_id: str) -> int:
        if table not in TABLES:
            raise ValueError(f"unknown table: {table}")
        with self._write_lock:
            cursor = self.connection.execute(
                f"DELETE FROM {table} WHERE project_id = ?", (project_id,)
            )
        return cursor.rowcount

    def load_all(self, table: str) -> list[dict]:
        """Every payload in *table*, oldest first."""
        if table not in TABLES:
            raise ValueError(f"unknown table: {table}")
        rows = self.connection.execute(
            f"SELECT payload FROM {table} ORDER BY created_at"
        ).fetchall()

        out: list[dict] = []
        for row in rows:
            try:
                out.append(json.loads(row["payload"]))
            except json.JSONDecodeError:
                continue  # one unreadable row must not lose the rest
        return out

    def count(self, table: str) -> int:
        if table not in TABLES:
            raise ValueError(f"unknown table: {table}")
        return int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def is_empty(self) -> bool:
        return all(self.count(table) == 0 for table in TABLES)

    # ------------------------------------------------------------------
    def get_meta(self, key: str) -> str | None:
        row = self.connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._write_lock:
            self.connection.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    # ------------------------------------------------------------------
    def clear(self) -> None:
        """Drop every record (tests and demo resets)."""
        with self._write_lock:
            conn = self.connection
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")

    def close(self) -> None:
        """Close every connection this database opened, on any thread."""
        with self._registry_lock:
            connections, self._connections = self._connections, []
        for conn in connections:
            try:
                conn.close()
            except sqlite3.Error:
                pass  # already closed, or closed from its own thread
        self._local.conn = None


# ---------------------------------------------------------------------------
# Postgres (Supabase)
# ---------------------------------------------------------------------------
# Tables live in their own schema. Supabase publishes the `public` schema
# through its Data API, so a table created there without row-level security is
# readable with the project's public anon key. A separate schema is not exposed
# unless someone adds it, and RLS is enabled on every table as well, with no
# policies: the API's own connection role owns the tables and is unaffected,
# while every Data API role is refused outright.
PG_SCHEMA = "mairos"

_PG_SCHEMA_SQL = f"""
CREATE SCHEMA IF NOT EXISTS {PG_SCHEMA};
CREATE TABLE IF NOT EXISTS {PG_SCHEMA}.meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
ALTER TABLE {PG_SCHEMA}.meta ENABLE ROW LEVEL SECURITY;
"""

_PG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {schema}.{table} (
    id          TEXT PRIMARY KEY,
    project_id  TEXT,
    created_at  TEXT,
    payload     JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{table}_project ON {schema}.{table} (project_id);
CREATE INDEX IF NOT EXISTS idx_{table}_created ON {schema}.{table} (created_at);
ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;
"""


class PostgresDatabase:
    """The same document store as :class:`Database`, over Postgres.

    Selected when ``DATABASE_URL`` is a ``postgres://`` URL — in production, a
    Supabase connection string. The method surface matches :class:`Database`
    exactly, so ``MetadataStore`` does not know which one it holds; the shared
    contract tests in ``tests/test_database_contract.py`` run against both.

    One connection per thread, in autocommit mode, for the same reason as the
    SQLite version. Prepared statements are disabled because Supabase's
    transaction pooler (port 6543) does not support them.
    """

    def __init__(self, url: str):
        import psycopg  # optional dependency, only needed for Postgres

        self._psycopg = psycopg
        self.url = url
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._registry_lock = threading.Lock()
        self._connections: list = []
        self._initialise()

    @property
    def connection(self):
        conn = getattr(self._local, "conn", None)
        if conn is None or conn.closed:
            conn = self._psycopg.connect(self.url, autocommit=True, prepare_threshold=None)
            self._local.conn = conn
            with self._registry_lock:
                self._connections.append(conn)
        return conn

    def _initialise(self) -> None:
        with self._write_lock:
            conn = self.connection
            with conn.transaction():
                conn.execute(_PG_SCHEMA_SQL)
                for table in TABLES:
                    conn.execute(_PG_TABLE_SQL.format(schema=PG_SCHEMA, table=table))

    @staticmethod
    def _check(table: str) -> str:
        if table not in TABLES:
            raise ValueError(f"unknown table: {table}")
        return f"{PG_SCHEMA}.{table}"

    def _upsert_sql(self, qualified: str) -> str:
        return (
            f"INSERT INTO {qualified} (id, project_id, created_at, payload) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET "
            "project_id = EXCLUDED.project_id, "
            "created_at = EXCLUDED.created_at, "
            "payload = EXCLUDED.payload"
        )

    def upsert(
        self,
        table: str,
        record_id: str,
        payload: dict,
        project_id: str | None = None,
        created_at: str | None = None,
    ) -> None:
        from psycopg.types.json import Jsonb

        qualified = self._check(table)
        with self._write_lock:
            self.connection.execute(
                self._upsert_sql(qualified), (record_id, project_id, created_at, Jsonb(payload))
            )

    def upsert_many(self, table: str, rows: Iterable[tuple[str, dict, str | None, str | None]]) -> int:
        from psycopg.types.json import Jsonb

        qualified = self._check(table)
        prepared = [
            (record_id, project_id, created_at, Jsonb(payload))
            for record_id, payload, project_id, created_at in rows
        ]
        if not prepared:
            return 0
        with self._write_lock:
            conn = self.connection
            with conn.transaction(), conn.cursor() as cursor:
                cursor.executemany(self._upsert_sql(qualified), prepared)
        return len(prepared)

    def delete(self, table: str, record_id: str) -> bool:
        qualified = self._check(table)
        with self._write_lock:
            cursor = self.connection.execute(f"DELETE FROM {qualified} WHERE id = %s", (record_id,))
        return cursor.rowcount > 0

    def delete_by_project(self, table: str, project_id: str) -> int:
        qualified = self._check(table)
        with self._write_lock:
            cursor = self.connection.execute(
                f"DELETE FROM {qualified} WHERE project_id = %s", (project_id,)
            )
        return cursor.rowcount

    def load_all(self, table: str) -> list[dict]:
        qualified = self._check(table)
        rows = self.connection.execute(
            f"SELECT payload FROM {qualified} ORDER BY created_at"
        ).fetchall()
        out: list[dict] = []
        for (payload,) in rows:
            if isinstance(payload, str):  # a driver configured without JSON loading
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    continue
            if isinstance(payload, dict):
                out.append(payload)
        return out

    def count(self, table: str) -> int:
        qualified = self._check(table)
        return int(self.connection.execute(f"SELECT COUNT(*) FROM {qualified}").fetchone()[0])

    def is_empty(self) -> bool:
        return all(self.count(table) == 0 for table in TABLES)

    def get_meta(self, key: str) -> str | None:
        row = self.connection.execute(
            f"SELECT value FROM {PG_SCHEMA}.meta WHERE key = %s", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._write_lock:
            self.connection.execute(
                f"INSERT INTO {PG_SCHEMA}.meta (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (key, value),
            )

    def clear(self) -> None:
        with self._write_lock:
            conn = self.connection
            with conn.transaction():
                for table in TABLES:
                    conn.execute(f"DELETE FROM {PG_SCHEMA}.{table}")

    def close(self) -> None:
        with self._registry_lock:
            connections, self._connections = self._connections, []
        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass
        self._local.conn = None


def open_database(path: str | Path | None, url: str = ""):
    """The store of record: Postgres when *url* is a postgres URL, else SQLite."""
    if url and url.strip().lower().startswith(("postgres://", "postgresql://")):
        return PostgresDatabase(url.strip())
    if path is None:
        raise ValueError("a database file path is required when no Postgres URL is configured")
    return Database(path)
