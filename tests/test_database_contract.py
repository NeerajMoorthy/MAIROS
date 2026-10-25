"""One contract, two backends: SQLite (local) and Postgres (Supabase).

``MetadataStore`` must not be able to tell which database it holds, so the
same assertions run against both. SQLite always runs. Postgres runs when
``MAIROS_TEST_DATABASE_URL`` points at a disposable database — the suite stays
offline by default, and CI without a database simply skips that half.

    MAIROS_TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/mairos_test
"""

from __future__ import annotations

import os
import threading

import pytest

from app.db import Database, PostgresDatabase, open_database
from app.store import MetadataStore
from schemas import QueryResponse

PG_URL = os.environ.get("MAIROS_TEST_DATABASE_URL", "")


@pytest.fixture(params=["sqlite", "postgres"])
def database(request, tmp_path):
    if request.param == "sqlite":
        db = Database(tmp_path / "contract.db")
    else:
        if not PG_URL:
            pytest.skip("MAIROS_TEST_DATABASE_URL not set — Postgres contract not exercised")
        db = PostgresDatabase(PG_URL)
        db.clear()
    yield db
    db.clear()
    db.close()


class TestDatabaseContract:
    def test_upsert_load_and_replace(self, database):
        database.upsert("projects", "p1", {"id": "p1", "name": "A"}, None, "2025-01-01")
        database.upsert("projects", "p1", {"id": "p1", "name": "B"}, None, "2025-01-01")
        assert database.load_all("projects") == [{"id": "p1", "name": "B"}]
        assert database.count("projects") == 1

    def test_load_all_is_oldest_first(self, database):
        database.upsert("tasks", "late", {"id": "late"}, "p", "2025-02-01")
        database.upsert("tasks", "early", {"id": "early"}, "p", "2025-01-01")
        assert [row["id"] for row in database.load_all("tasks")] == ["early", "late"]

    def test_upsert_many_and_delete_by_project(self, database):
        rows = [(f"d{i}", {"id": f"d{i}"}, "p1" if i % 2 else "p2", f"2025-01-0{i + 1}") for i in range(4)]
        assert database.upsert_many("documents", rows) == 4
        assert database.delete_by_project("documents", "p1") == 2
        assert {row["id"] for row in database.load_all("documents")} == {"d0", "d2"}

    def test_delete_one(self, database):
        database.upsert("patents", "x", {"id": "x"}, "p", None)
        assert database.delete("patents", "x") is True
        assert database.delete("patents", "x") is False

    def test_meta_and_emptiness(self, database):
        assert database.is_empty()
        assert database.get_meta("k") is None
        database.set_meta("k", "v1")
        database.set_meta("k", "v2")
        assert database.get_meta("k") == "v2"

    def test_unknown_tables_are_refused(self, database):
        with pytest.raises(ValueError):
            database.upsert("users; DROP TABLE projects", "x", {}, None, None)

    def test_nested_payloads_round_trip(self, database):
        payload = {"id": "t", "events": [{"message": "ü — ok", "n": 1}], "result": None}
        database.upsert("tasks", "t", payload, "p", "2025-01-01")
        assert database.load_all("tasks") == [payload]

    def test_concurrent_writes_from_many_threads(self, database):
        def write(index: int) -> None:
            database.upsert("papers", f"paper-{index}", {"id": f"paper-{index}"}, "p", None)

        threads = [threading.Thread(target=write, args=(i,)) for i in range(24)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert database.count("papers") == 24


class TestStoreOverEitherBackend:
    def test_store_round_trip(self, database, tmp_path):
        store = MetadataStore(state_file=tmp_path / "none.json")
        store._db = database  # the store is backend-agnostic by construction
        store.load()

        project = store.create_project("Contract", owner_id="user-1")
        store.add_patent(project.id, title="P", text="Claims\n1. A thing.", cpc_codes=["G06F 16/33"])
        task = store.create_task(project.id, "q?", flow="answer")
        store.update_task_result(task.id, QueryResponse(answer="A."))

        fresh = MetadataStore(state_file=tmp_path / "none.json")
        fresh._db = database
        fresh.load()
        assert fresh.get_project(project.id).owner_id == "user-1"
        assert fresh.list_patents(project.id)[0].cpc_codes == ["G06F 16/33"]
        assert fresh.get_task(task.id).result.answer == "A."


class TestBackendSelection:
    def test_a_file_path_means_sqlite(self, tmp_path):
        db = open_database(tmp_path / "x.db", "")
        assert isinstance(db, Database)
        db.close()

    def test_a_postgres_url_means_postgres(self, monkeypatch):
        opened = {}

        class Recorder:
            def __init__(self, url):
                opened["url"] = url

        monkeypatch.setattr("app.db.PostgresDatabase", Recorder)
        open_database(None, "postgresql://u:p@host:6543/postgres")
        assert opened["url"] == "postgresql://u:p@host:6543/postgres"

    def test_an_explicit_file_is_never_redirected_to_postgres(self, tmp_path, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "database_url", "postgresql://u:p@host/db")
        store = MetadataStore(state_file=tmp_path / "s.json", database_file=tmp_path / "local.db")
        assert isinstance(store.db, Database)
        store.db.close()

    def test_data_dir_relocates_every_storage_path(self, tmp_path):
        from app.config import Settings

        relocated = Settings(data_dir=tmp_path / "volume")
        assert relocated.upload_dir == tmp_path / "volume" / "uploads"
        assert relocated.chroma_persist_dir == tmp_path / "volume" / "chroma"
        assert relocated.database_file == tmp_path / "volume" / "mairos.db"

        pinned = Settings(data_dir=tmp_path / "volume", graph_dir=tmp_path / "elsewhere")
        assert pinned.graph_dir == tmp_path / "elsewhere"
