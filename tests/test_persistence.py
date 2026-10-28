"""SQLite persistence: durability, migration, and concurrent writes.

These are the tests the JSON snapshot could not have passed. The snapshot
rewrote the whole file on every mutation, so two threads writing at once raced
each other and a crash mid-write could truncate everything.
"""

from __future__ import annotations

import json
import threading

import pytest

from app.db import Database
from app.store import MetadataStore
from schemas import QueryResponse, TaskEvent, TaskStage, TaskStatus


@pytest.fixture()
def store(tmp_path) -> MetadataStore:
    instance = MetadataStore(
        state_file=tmp_path / "state.json", database_file=tmp_path / "mairos.db"
    )
    instance.load()
    return instance


def reopen(store: MetadataStore) -> MetadataStore:
    """Simulate a process restart against the same database file."""
    store.save()
    fresh = MetadataStore(state_file=store.state_file, database_file=store.database_file)
    fresh.load()
    return fresh


# ---------------------------------------------------------------------------
# Durability
# ---------------------------------------------------------------------------
class TestRestartDurability:
    def test_projects_documents_papers_and_patents_survive_a_restart(self, store):
        project = store.create_project("Survivor", "a project")
        store.add_document(project.id, "doc-1", "paper.pdf", num_pages=9, num_chunks=42)
        store.add_paper(project.id, {"id": "arx-1", "title": "A Paper", "authors": ["A B"]})
        store.add_patent(project.id, title="A Patent", text="some claims")

        restarted = reopen(store)

        assert [p.name for p in restarted.list_projects()] == ["Survivor"]
        documents = restarted.list_documents(project.id)
        assert [d.filename for d in documents] == ["paper.pdf"]
        assert documents[0].num_chunks == 42
        assert [p.title for p in restarted.list_papers(project.id)] == ["A Paper"]
        assert [p.title for p in restarted.list_patents(project.id)] == ["A Patent"]

    def test_task_history_including_events_survives_a_restart(self, store):
        project = store.create_project("Tasks")
        task = store.create_task(project.id, "why?", flow="answer")

        store.add_task_event(
            TaskEvent(
                task_id=task.id,
                agent_name="retriever",
                stage=TaskStage.RETRIEVING,
                status=TaskStatus.COMPLETED,
                message="5 chunks retrieved",
            )
        )
        store.update_task_result(task.id, QueryResponse(answer="Because."))

        restarted = reopen(store)
        restored = restarted.get_task(task.id)

        assert restored is not None
        assert restored.status == TaskStatus.COMPLETED
        assert restored.result.answer == "Because."
        assert [e.message for e in restored.events] == ["5 chunks retrieved"]

    def test_a_run_interrupted_mid_pipeline_keeps_its_events(self, store):
        """Events persist as they happen, not only when the run finishes."""
        project = store.create_project("Interrupted")
        task = store.create_task(project.id, "long job")
        store.add_task_event(
            TaskEvent(task_id=task.id, agent_name="orchestrator", message="Task accepted")
        )

        # No update_task_result — the process "dies" here.
        fresh = MetadataStore(state_file=store.state_file, database_file=store.database_file)
        fresh.load()

        restored = fresh.get_task(task.id)
        assert restored is not None
        assert [e.message for e in restored.events] == ["Task accepted"]

    def test_a_step_event_does_not_end_a_run_that_is_still_going(self, store):
        """A degraded agent logs "failed" and the orchestrator logs
        "completed" before the result is saved. Either used to end the task
        mid-run, so a project with runs in progress showed none running."""
        project = store.create_project("Busy")
        task = store.create_task(project.id, "long job")

        for status in (TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.COMPLETED):
            store.add_task_event(
                TaskEvent(task_id=task.id, agent_name="analysis", status=status, message="step")
            )
            assert store.get_task(task.id).status == TaskStatus.RUNNING

        store.update_task_result(task.id, QueryResponse(answer="Done."))
        assert store.get_task(task.id).status == TaskStatus.COMPLETED
        # A late event cannot reopen a finished run.
        store.add_task_event(TaskEvent(task_id=task.id, agent_name="late", message="late"))
        assert store.get_task(task.id).status == TaskStatus.COMPLETED

    def test_a_run_cut_off_by_a_restart_stops_counting_as_running(self, store):
        """A run lives in the process that started it, so after a restart a
        queued or running task can never finish. It used to count as running
        forever on the workspace header."""
        project = store.create_project("Restarted")
        running = store.create_task(project.id, "mid-pipeline")
        store.add_task_event(
            TaskEvent(task_id=running.id, agent_name="orchestrator", message="Task accepted")
        )
        queued = store.create_task(project.id, "never started")
        done = store.create_task(project.id, "finished")
        store.update_task_result(done.id, QueryResponse(answer="Yes."))

        restarted = reopen(store)

        for task_id in (running.id, queued.id):
            task = restarted.get_task(task_id)
            assert task.status == TaskStatus.FAILED
            assert "restarted" in task.error
        assert restarted.get_task(done.id).status == TaskStatus.COMPLETED
        # The change is stored, not only applied in memory.
        assert reopen(restarted).get_task(running.id).status == TaskStatus.FAILED

    def test_task_history_is_not_capped_at_forty(self, store):
        """The old snapshot dropped everything past MAX_PERSISTED_TASKS."""
        project = store.create_project("Many")
        for index in range(45):
            store.create_task(project.id, f"question {index}")

        restarted = reopen(store)
        assert len(restarted.list_tasks(project.id, limit=1000)) == 45

    def test_deleting_a_project_cascades_through_the_database(self, store):
        project = store.create_project("Doomed")
        store.add_document(project.id, "doc-1", "paper.pdf")
        store.add_patent(project.id, title="P", text="t")
        store.create_task(project.id, "q")

        assert store.delete_project(project.id) is True

        restarted = reopen(store)
        assert restarted.list_projects() == []
        assert restarted.list_documents(project.id) == []
        assert restarted.list_patents(project.id) == []
        assert restarted.list_tasks(project.id) == []


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------
class TestLegacyMigration:
    def _snapshot(self, tmp_path) -> None:
        (tmp_path / "state.json").write_text(
            json.dumps(
                {
                    "version": 2,
                    "projects": [
                        {
                            "id": "old-p",
                            "name": "Legacy project",
                            "description": "",
                            "created_at": "2026-01-01T00:00:00Z",
                            "document_ids": ["old-d"],
                            "paper_ids": [],
                        }
                    ],
                    "documents": [
                        {
                            "id": "old-d",
                            "project_id": "old-p",
                            "filename": "legacy.pdf",
                            "num_pages": 3,
                            "num_chunks": 7,
                            "ingested_at": "2026-01-01T00:05:00Z",
                        }
                    ],
                    "papers": [],
                    "patents": [],
                    "tasks": [],
                }
            ),
            encoding="utf-8",
        )

    def test_an_existing_snapshot_is_imported_once(self, tmp_path):
        self._snapshot(tmp_path)

        store = MetadataStore(
            state_file=tmp_path / "state.json", database_file=tmp_path / "mairos.db"
        )
        store.load()

        assert [p.name for p in store.list_projects()] == ["Legacy project"]
        assert [d.filename for d in store.list_documents("old-p")] == ["legacy.pdf"]

    def test_the_snapshot_file_is_left_untouched(self, tmp_path):
        self._snapshot(tmp_path)
        before = (tmp_path / "state.json").read_text()

        MetadataStore(
            state_file=tmp_path / "state.json", database_file=tmp_path / "mairos.db"
        ).load()

        assert (tmp_path / "state.json").read_text() == before

    def test_migration_does_not_repeat_and_cannot_resurrect_deletions(self, tmp_path):
        self._snapshot(tmp_path)

        store = MetadataStore(
            state_file=tmp_path / "state.json", database_file=tmp_path / "mairos.db"
        )
        store.load()
        store.delete_project("old-p")

        # A second start must not re-import the snapshot over the deletion.
        restarted = MetadataStore(
            state_file=tmp_path / "state.json", database_file=tmp_path / "mairos.db"
        )
        restarted.load()
        assert restarted.list_projects() == []

    def test_a_corrupt_snapshot_does_not_prevent_startup(self, tmp_path):
        (tmp_path / "state.json").write_text("{not json", encoding="utf-8")

        store = MetadataStore(
            state_file=tmp_path / "state.json", database_file=tmp_path / "mairos.db"
        )
        store.load()

        assert store.list_projects() == []
        store.create_project("Still works")
        assert len(store.list_projects()) == 1


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------
class TestConcurrentWrites:
    def test_parallel_project_creation_loses_nothing(self, store):
        errors: list[Exception] = []

        def worker(index: int) -> None:
            try:
                store.create_project(f"Project {index}")
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert len(store.list_projects()) == 20
        assert len(reopen(store).list_projects()) == 20

    def test_parallel_event_writes_on_one_task_are_all_kept(self, store):
        project = store.create_project("Busy")
        task = store.create_task(project.id, "concurrent")

        def worker(index: int) -> None:
            store.add_task_event(
                TaskEvent(task_id=task.id, agent_name=f"agent-{index}", message=f"event {index}")
            )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(25)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(store.get_task(task.id).events) == 25
        assert len(reopen(store).get_task(task.id).events) == 25

    def test_writes_from_many_threads_reach_one_database(self, tmp_path):
        """Each thread gets its own connection; the rows land in one file."""
        db = Database(tmp_path / "threads.db")

        def worker(index: int) -> None:
            db.upsert("projects", f"p{index}", {"id": f"p{index}"}, project_id=None, created_at=None)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert db.count("projects") == 30


# ---------------------------------------------------------------------------
# Database primitives
# ---------------------------------------------------------------------------
class TestDatabase:
    def test_upsert_replaces_rather_than_duplicates(self, tmp_path):
        db = Database(tmp_path / "x.db")
        db.upsert("projects", "p1", {"id": "p1", "name": "first"})
        db.upsert("projects", "p1", {"id": "p1", "name": "second"})

        rows = db.load_all("projects")
        assert len(rows) == 1
        assert rows[0]["name"] == "second"

    def test_unknown_table_is_rejected(self, tmp_path):
        db = Database(tmp_path / "x.db")
        with pytest.raises(ValueError):
            db.upsert("robert'); DROP TABLE projects;--", "x", {})

    def test_an_unreadable_row_does_not_lose_the_others(self, tmp_path):
        db = Database(tmp_path / "x.db")
        db.upsert("projects", "good", {"id": "good"})
        db.connection.execute(
            "INSERT INTO projects (id, payload) VALUES ('bad', 'not json')"
        )

        assert [row["id"] for row in db.load_all("projects")] == ["good"]


# ---------------------------------------------------------------------------
# Reads during writes
# ---------------------------------------------------------------------------
class TestConcurrentReadsAndWrites:
    """Readers iterated the live dicts while writers mutated them.

    Writers took `self._lock`; the list and count methods did not, and both
    `sorted(d.values())` and a generator expression over `.values()` iterate
    lazily. FastAPI runs sync endpoints in a threadpool, so "a document
    finishes ingesting while the documents list is being fetched" is an
    ordinary interleaving, and it raised `RuntimeError: dictionary changed
    size during iteration` — surfacing to the user as a bare 500.
    """

    def test_listing_while_writing_does_not_raise(self, store):
        project = store.create_project("Busy")
        errors: list[Exception] = []
        stop = threading.Event()

        def writer(index: int) -> None:
            try:
                for n in range(60):
                    store.add_document(project.id, f"d-{index}-{n}", f"{index}-{n}.pdf")
                    store.add_paper(project.id, {"id": f"p-{index}-{n}", "title": "T"})
                    store.create_task(project.id, f"q{index}-{n}")
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)
            finally:
                stop.set()

        def reader() -> None:
            try:
                while not stop.is_set():
                    store.list_documents(project.id)
                    store.count_documents(project.id)
                    store.list_papers(project.id)
                    store.list_tasks(project.id, limit=1000)
                    store.list_projects()
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert errors == [], f"concurrent read/write raised: {errors[:3]}"
        assert store.count_documents(project.id) == 180

    def test_a_reader_never_deadlocks_against_a_writer(self, store):
        """The lock is not reentrant, so a writer calling a reader would hang."""
        project = store.create_project("Deadlock check")
        finished = threading.Event()

        def work() -> None:
            for index in range(50):
                store.add_document(project.id, f"d{index}", f"{index}.pdf")
                store.list_documents(project.id)
                store.delete_project(project.id) if index == 49 else None
            finished.set()

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        thread.join(timeout=20)

        assert finished.is_set(), "a reader and a writer deadlocked"


class TestConnectionLifecycle:
    def test_close_closes_every_threads_connection(self, tmp_path):
        """`close()` only closed the caller's, leaking one fd per pool thread."""
        db = Database(tmp_path / "threads.db")
        ready = threading.Barrier(5)

        def touch(index: int) -> None:
            db.upsert("projects", f"p{index}", {"id": f"p{index}"})
            ready.wait(timeout=10)

        threads = [threading.Thread(target=touch, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        ready.wait(timeout=10)
        for thread in threads:
            thread.join(timeout=10)

        assert len(db._connections) >= 4
        db.close()
        assert db._connections == []

    def test_a_write_on_a_fresh_thread_does_not_deadlock(self, tmp_path):
        """`connection` is called from inside the write lock by every mutator.

        Registering the new connection under that same non-reentrant lock would
        hang the first write on every new thread — which, in a threadpool, is
        every request until the pool is warm.
        """
        db = Database(tmp_path / "deadlock.db")
        done = threading.Event()

        def writer() -> None:
            db.upsert("tasks", "t1", {"id": "t1"})
            db.upsert_many("papers", [("x1", {"id": "x1"}, None, None)])
            done.set()

        thread = threading.Thread(target=writer, daemon=True)
        thread.start()
        thread.join(timeout=10)

        assert done.is_set(), "a write on a new thread deadlocked"
        assert db.count("tasks") == 1


class TestLoadFailureIsNotPermanent:
    def test_a_failed_open_does_not_poison_the_store_forever(self, tmp_path, monkeypatch):
        """`_loaded` was set before the database opened, so one bad start stuck."""
        store = MetadataStore(
            state_file=tmp_path / "state.json", database_file=tmp_path / "mairos.db"
        )

        broken = {"first": True}
        real_db = MetadataStore.db.fget

        def flaky(self):
            if broken["first"]:
                broken["first"] = False
                raise OSError("data directory not ready")
            return real_db(self)

        monkeypatch.setattr(MetadataStore, "db", property(flaky))

        store.load()  # fails
        assert store.list_projects() == []

        store.load()  # the directory is there now; this must actually load
        store.create_project("Works after a retry")
        assert len(store.list_projects()) == 1
