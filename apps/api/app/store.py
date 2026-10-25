"""Metadata store for projects, documents, papers, patents, and tasks.

Reads are served from memory; durability is SQLite (``app/db.py``). Each
mutation writes one row in one transaction, which replaced an earlier design
that rewrote a whole JSON snapshot on every change — that lost data if two
writers raced and could truncate everything if the process died mid-write.

A legacy ``state.json`` left over from that design is imported once, the first
time an empty database is opened, so an existing demo keeps its history.

The method surface is deliberately unchanged from the snapshot version: every
call site still sees the same signatures and the same Pydantic objects.
"""

from __future__ import annotations

import json
import threading
import uuid

from pathlib import Path

from app.db import Database, open_database
from schemas import (
    Document,
    EvaluationRecord,
    Paper,
    Patent,
    Project,
    QueryResponse,
    Task,
    TaskEvent,
    TaskStage,
    TaskStatus,
    utcnow,
)

# Kept for the legacy importer only: the old snapshot capped how many task runs
# it wrote. SQLite has no such limit, so nothing new is truncated.
MAX_PERSISTED_TASKS = 40

_MIGRATION_KEY = "imported_state_json"


class MetadataStore:
    """Manage projects, documents, papers, patents, and task runs."""

    def __init__(self, state_file: str | Path | None = None, database_file: str | Path | None = None):
        self._projects: dict[str, Project] = {}
        self._documents: dict[str, Document] = {}
        self._papers: dict[str, Paper] = {}
        self._patents: dict[str, Patent] = {}
        self._tasks: dict[str, Task] = {}
        self._evaluations: dict[str, EvaluationRecord] = {}
        self._lock = threading.Lock()
        self._state_file = Path(state_file) if state_file else None
        self._database_file = Path(database_file) if database_file else None
        self._db: Database | None = None
        self._loaded = False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    @property
    def state_file(self) -> Path:
        """The legacy JSON snapshot — read once for migration, never written."""
        if self._state_file is None:
            from app.config import settings

            self._state_file = Path(settings.state_file)
        return self._state_file

    @property
    def database_file(self) -> Path:
        if self._database_file is None:
            from app.config import settings

            self._database_file = Path(settings.database_file)
        return self._database_file

    @property
    def db(self) -> Database:
        """SQLite at ``database_file``, or Postgres when ``DATABASE_URL`` says so.

        An explicitly chosen file (tests, ``use_database``) always means SQLite,
        so pointing the store at a file can never silently write to a remote
        database instead.
        """
        if self._db is None:
            url = ""
            if self._database_file is None:
                from app.config import settings

                url = settings.database_url
            self._db = open_database(self.database_file, url)
        return self._db

    # ------------------------------------------------------------------
    def _persist(self, table: str, record) -> None:
        """Write one record through to SQLite (best effort — never raises)."""
        try:
            payload = record.model_dump(mode="json")
            created = payload.get("created_at") or payload.get("added_at") or payload.get("ingested_at")
            self.db.upsert(
                table,
                record_id=payload["id"],
                payload=payload,
                project_id=payload.get("project_id"),
                created_at=created,
            )
        except Exception as exc:
            print(f"[store] persist to {table} failed: {exc}")

    def _forget(self, table: str, record_id: str) -> None:
        try:
            self.db.delete(table, record_id)
        except Exception as exc:
            print(f"[store] delete from {table} failed: {exc}")

    def load(self) -> None:
        """Restore state from SQLite. Safe to call more than once."""
        if self._loaded:
            return

        try:
            db = self.db
        except Exception as exc:
            # The flag is set only once the database is open. Setting it first
            # meant a transient open failure — a directory not created yet, a
            # lock held by another process — poisoned the store for the life of
            # the process, and nothing reset it.
            print(f"[store] could not open the database: {exc}")
            return

        self._loaded = True

        try:
            if db.is_empty() and not db.get_meta(_MIGRATION_KEY):
                self._import_legacy_snapshot()

            def rebuild(table: str, model):
                records = {}
                for payload in db.load_all(table):
                    try:
                        record = model(**payload)
                    except Exception as exc:  # one bad row must not lose the rest
                        print(f"[store] skipping unreadable {table} row: {exc}")
                        continue
                    records[record.id] = record
                return records

            with self._lock:
                self._projects = rebuild("projects", Project)
                self._documents = rebuild("documents", Document)
                self._papers = rebuild("papers", Paper)
                self._patents = rebuild("patents", Patent)
                self._tasks = rebuild("tasks", Task)
                self._evaluations = rebuild("evaluations", EvaluationRecord)
        except Exception as exc:
            print(f"[store] load failed, starting empty: {exc}")

    def _import_legacy_snapshot(self) -> int:
        """One-time import of a pre-SQLite ``state.json``.

        The snapshot is left on disk untouched: if the import turns out to have
        gone wrong, the original is still there to inspect.
        """
        path = self.state_file
        if not path.exists():
            self.db.set_meta(_MIGRATION_KEY, "no snapshot found")
            return 0

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[store] legacy snapshot unreadable, skipping import: {exc}")
            self.db.set_meta(_MIGRATION_KEY, f"unreadable: {exc}")
            return 0

        imported = 0
        for table, key in (
            ("projects", "projects"),
            ("documents", "documents"),
            ("papers", "papers"),
            ("patents", "patents"),
            ("tasks", "tasks"),
        ):
            rows = []
            for payload in data.get(key, []) or []:
                if not isinstance(payload, dict) or not payload.get("id"):
                    continue
                created = (
                    payload.get("created_at")
                    or payload.get("added_at")
                    or payload.get("ingested_at")
                )
                rows.append((payload["id"], payload, payload.get("project_id"), created))
            imported += self.db.upsert_many(table, rows)

        self.db.set_meta(_MIGRATION_KEY, f"imported {imported} records from {path.name}")
        print(f"[store] migrated {imported} records from {path}")
        return imported

    def save(self) -> None:
        """Flush every in-memory record to SQLite.

        Mutations already persist themselves row by row, so this is a
        belt-and-braces full write kept because call sites (and the shutdown
        hook) still invoke it.
        """
        try:
            for table, records in (
                ("projects", self._projects),
                ("documents", self._documents),
                ("papers", self._papers),
                ("patents", self._patents),
                ("tasks", self._tasks),
                ("evaluations", self._evaluations),
            ):
                rows = []
                for record in list(records.values()):
                    payload = record.model_dump(mode="json")
                    created = (
                        payload.get("created_at")
                        or payload.get("added_at")
                        or payload.get("ingested_at")
                    )
                    rows.append((payload["id"], payload, payload.get("project_id"), created))
                self.db.upsert_many(table, rows)
        except Exception as exc:
            print(f"[store] save failed: {exc}")

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    def create_project(self, name: str, description: str = "", owner_id: str = "") -> Project:
        project = Project(
            id=str(uuid.uuid4()),
            name=name,
            description=description or "",
            owner_id=owner_id or "",
        )
        with self._lock:
            self._projects[project.id] = project
        self._persist("projects", project)
        return project

    def get_project(self, project_id: str) -> Project | None:
        return self._projects.get(project_id)

    def list_projects(self, owner_id: str | None = None) -> list[Project]:
        """All projects, newest first — or only *owner_id*'s when given."""
        # Snapshot under the lock, then sort outside it. Writers hold the same
        # lock, and FastAPI runs sync endpoints in a threadpool, so a document
        # finishing ingestion while this list is being built is an everyday
        # interleaving — and iterating a dict a writer is mutating raises
        # `RuntimeError: dictionary changed size during iteration`, which the
        # caller sees as a bare 500.
        with self._lock:
            projects = list(self._projects.values())
        if owner_id is not None:
            projects = [p for p in projects if p.owner_id == owner_id]
        return sorted(projects, key=lambda p: p.created_at, reverse=True)

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            if project_id not in self._projects:
                return False
            del self._projects[project_id]
            self._documents = {
                k: v for k, v in self._documents.items() if v.project_id != project_id
            }
            self._papers = {
                k: v for k, v in self._papers.items() if v.project_id != project_id
            }
            self._patents = {
                k: v for k, v in self._patents.items() if v.project_id != project_id
            }
            self._tasks = {
                k: v for k, v in self._tasks.items() if v.project_id != project_id
            }
            self._evaluations.pop(project_id, None)

        # Cascade in the database too, or the next load would resurrect them.
        try:
            self.db.delete("projects", project_id)
            for table in ("documents", "papers", "patents", "tasks", "evaluations"):
                self.db.delete_by_project(table, project_id)
        except Exception as exc:
            print(f"[store] cascade delete failed: {exc}")
        return True

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------
    def add_document(
        self,
        project_id: str,
        document_id: str,
        filename: str,
        num_pages: int = 0,
        num_chunks: int = 0,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> Document:
        doc = Document(
            id=document_id,
            project_id=project_id,
            filename=filename,
            title=title or filename,
            num_pages=num_pages,
            num_chunks=num_chunks,
            metadata=metadata or {},
        )
        with self._lock:
            self._documents[doc.id] = doc
            project = self._projects.get(project_id)
            if project and doc.id not in project.document_ids:
                project.document_ids.append(doc.id)
        self._persist("documents", doc)
        if project:
            self._persist("projects", project)
        return doc

    def get_document(self, document_id: str) -> Document | None:
        return self._documents.get(document_id)

    def list_documents(self, project_id: str) -> list[Document]:
        with self._lock:
            documents = [d for d in self._documents.values() if d.project_id == project_id]
        return sorted(documents, key=lambda d: d.ingested_at, reverse=True)

    def count_documents(self, project_id: str) -> int:
        with self._lock:
            return sum(1 for d in self._documents.values() if d.project_id == project_id)

    # ------------------------------------------------------------------
    # Papers (discovered by the Literature agent)
    # ------------------------------------------------------------------
    def add_paper(
        self, project_id: str, paper: dict, reference: str = "", aliases=()
    ) -> Paper:
        """Store a discovered paper, replacing any copy under one of *aliases*.

        *aliases* are the other ids the same paper may already be stored under
        in this project — an earlier build's id scheme, or another of its
        identifiers — so a repeated search updates the paper instead of
        listing it twice.
        """
        paper_id = f"{project_id}:{paper.get('id') or uuid.uuid4()}"
        stale = {f"{project_id}:{alias}" for alias in aliases if alias} - {paper_id}
        record = Paper(
            id=paper_id,
            project_id=project_id,
            title=paper.get("title", "Untitled"),
            authors=list(paper.get("authors", []))[:20],
            abstract=paper.get("abstract", ""),
            year=str(paper.get("year", "")),
            published=str(paper.get("published", "")),
            url=paper.get("url", ""),
            pdf_url=paper.get("pdf_url", ""),
            source=paper.get("source", "arXiv"),
            sources=list(paper.get("sources") or [paper.get("source", "arXiv")]),
            doi=paper.get("doi", "") or "",
            venue=paper.get("venue", "") or "",
            citation_count=paper.get("citation_count"),
            reference=reference,
        )
        with self._lock:
            removed = [sid for sid in stale if self._papers.pop(sid, None) is not None]
            self._papers[paper_id] = record
            project = self._projects.get(project_id)
            if project:
                project.paper_ids = [pid for pid in project.paper_ids if pid not in stale]
                if paper_id not in project.paper_ids:
                    project.paper_ids.append(paper_id)
        for sid in removed:
            self._forget("papers", sid)
        self._persist("papers", record)
        if project:
            self._persist("projects", project)
        return record

    def list_papers(self, project_id: str) -> list[Paper]:
        with self._lock:
            papers = [p for p in self._papers.values() if p.project_id == project_id]
        return sorted(papers, key=lambda p: p.added_at, reverse=True)

    # ------------------------------------------------------------------
    # Patents (entered by hand; MAIROS never fetches patent documents)
    # ------------------------------------------------------------------
    def add_patent(
        self,
        project_id: str,
        title: str,
        text: str = "",
        number: str = "",
        url: str = "",
        assignee: str = "",
        source: str = "manual entry",
        **metadata,
    ) -> Patent:
        """Store a patent reference. ``metadata`` takes any bibliographic field
        of :class:`Patent` (``cpc_codes``, ``filing_date`` and so on)."""
        record = Patent(
            id=str(uuid.uuid4()),
            project_id=project_id,
            title=title,
            number=number,
            url=url,
            assignee=assignee,
            text=text,
            source=source,
            **metadata,
        )
        with self._lock:
            self._patents[record.id] = record
        self._persist("patents", record)
        return record

    def update_patent(self, patent_id: str, **changes) -> Patent | None:
        """Replace the given fields of a stored patent; ``None`` if it is gone."""
        with self._lock:
            current = self._patents.get(patent_id)
            if current is None:
                return None
            # Revalidate through the model rather than setattr, so an update can
            # never store a value the schema would have rejected on creation.
            updated = Patent(
                **{**current.model_dump(), **changes, "id": current.id,
                   "project_id": current.project_id, "updated_at": utcnow()}
            )
            self._patents[patent_id] = updated
        self._persist("patents", updated)
        return updated

    def get_patent(self, patent_id: str) -> Patent | None:
        return self._patents.get(patent_id)

    def list_patents(self, project_id: str) -> list[Patent]:
        with self._lock:
            patents = [p for p in self._patents.values() if p.project_id == project_id]
        return sorted(patents, key=lambda p: p.added_at, reverse=True)

    def delete_patent(self, patent_id: str) -> bool:
        with self._lock:
            if patent_id not in self._patents:
                return False
            del self._patents[patent_id]
        self._forget("patents", patent_id)
        return True

    # ------------------------------------------------------------------
    # Evaluations (the latest report per project)
    # ------------------------------------------------------------------
    def save_evaluation(self, project_id: str, report: dict) -> EvaluationRecord:
        record = EvaluationRecord(id=project_id, project_id=project_id, report=report)
        with self._lock:
            self._evaluations[project_id] = record
        self._persist("evaluations", record)
        return record

    def get_evaluation(self, project_id: str) -> EvaluationRecord | None:
        return self._evaluations.get(project_id)

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------
    def create_task(
        self,
        project_id: str,
        request: str,
        flow: str | None = None,
        document_id: str | None = None,
    ) -> Task:
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project_id,
            request=request,
            flow=flow,
            document_id=document_id,
            status=TaskStatus.QUEUED,
            current_stage=TaskStage.QUEUED,
        )
        with self._lock:
            self._tasks[task.id] = task
        self._persist("tasks", task)
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_tasks(
        self,
        project_id: str | None = None,
        limit: int = 50,
        project_ids: set[str] | None = None,
    ) -> list[Task]:
        """Newest tasks first, for one project, a set of projects, or all."""
        with self._lock:
            tasks = list(self._tasks.values())
        if project_id:
            tasks = [t for t in tasks if t.project_id == project_id]
        if project_ids is not None:
            tasks = [t for t in tasks if t.project_id in project_ids]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)[:limit]

    def add_task_event(self, event: TaskEvent) -> None:
        """Append an activity event and advance the task's stage."""
        task = self._tasks.get(event.task_id)
        if not task:
            return
        with self._lock:
            task.events.append(event)
            task.current_stage = event.stage
            if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                task.status = (
                    TaskStatus.RUNNING
                    if event.status == TaskStatus.QUEUED
                    else event.status
                )
            task.updated_at = utcnow()
        # Events are the live trace; persisting each one is what makes a run
        # survivable across a restart mid-pipeline.
        self._persist("tasks", task)

    def update_task_result(
        self,
        task_id: str,
        result: QueryResponse,
        status: TaskStatus = TaskStatus.COMPLETED,
    ) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        with self._lock:
            task.result = result
            task.status = status
            task.current_stage = TaskStage.COMPLETED
            task.updated_at = utcnow()
        self._persist("tasks", task)

    def update_task_error(self, task_id: str, error: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        with self._lock:
            task.error = error
            task.status = TaskStatus.FAILED
            task.current_stage = TaskStage.FAILED
            task.updated_at = utcnow()
        self._persist("tasks", task)

    # ------------------------------------------------------------------
    def clear(self, *, wipe_database: bool = False) -> None:
        """Drop in-memory state, and optionally the stored rows too (tests)."""
        with self._lock:
            self._projects.clear()
            self._documents.clear()
            self._papers.clear()
            self._patents.clear()
            self._tasks.clear()
            self._evaluations.clear()

        if wipe_database and self._db is not None:
            try:
                self._db.clear()
            except Exception as exc:
                print(f"[store] database clear failed: {exc}")

    def use_database(self, path: str | Path) -> None:
        """Point the store at a different database file (tests, fresh starts)."""
        if self._db is not None:
            self._db.close()
        self._db = None
        self._database_file = Path(path)
        self._loaded = False


# Singleton shared across the application.
metadata_store = MetadataStore()
