"""Shared Pydantic schemas — the API contract between backend and frontend."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp (``datetime.utcnow`` is deprecated)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------
class Project(BaseModel):
    """A research workspace that groups documents, graph, and tasks."""

    id: str
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    document_ids: list[str] = Field(default_factory=list)
    paper_ids: list[str] = Field(default_factory=list)
    # Who may see this project when authentication is enabled. Empty means a
    # project created in local single-user mode (or before auth existed); see
    # ``app/auth.py`` for how those are treated.
    owner_id: str = ""


# ---------------------------------------------------------------------------
# Document, Paper & Chunk
# ---------------------------------------------------------------------------
class Document(BaseModel):
    """An uploaded source document (a PDF paper)."""

    id: str
    project_id: str
    filename: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    num_pages: int = 0
    num_chunks: int = 0
    ingested_at: datetime = Field(default_factory=utcnow)
    metadata: dict = Field(default_factory=dict)


class Paper(BaseModel):
    """A paper discovered by the Literature agent (arXiv, OpenAlex, Semantic Scholar)."""

    id: str
    project_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    year: str = ""
    published: str = ""
    url: str = ""
    pdf_url: str = ""
    source: str = "arXiv"
    # Every source that returned this paper, after de-duplication.
    sources: list[str] = Field(default_factory=list)
    doi: str = ""
    venue: str = ""
    citation_count: int | None = None
    reference: str = ""
    added_at: datetime = Field(default_factory=utcnow)


class Patent(BaseModel):
    """A patent reference entered by hand or linked to a public registry.

    MAIROS never fetches patent documents: ``text`` is what the user pasted and
    ``url`` is only a reference for a human to open. See
    ``services/patents/sources.py``.

    Every bibliographic field below ``source`` was added with the dedicated
    Patents page. They all default to empty, which is the migration path:
    records stored before they existed load unchanged, with blank metadata,
    rather than being dropped (see ``tests/test_patents.py``).
    """

    id: str
    project_id: str
    title: str
    # Publication number. Kept under its original name so stored records and
    # older clients still line up.
    number: str = ""
    url: str = ""
    assignee: str = ""
    text: str = ""
    source: str = "manual entry"
    added_at: datetime = Field(default_factory=utcnow)

    # Bibliographic metadata — entered by hand, never fetched.
    application_number: str = ""
    family_id: str = ""
    cpc_codes: list[str] = Field(default_factory=list)
    ipc_codes: list[str] = Field(default_factory=list)
    inventors: list[str] = Field(default_factory=list)
    priority_date: date | None = None
    filing_date: date | None = None
    publication_date: date | None = None
    updated_at: datetime | None = None


class EvaluationRecord(BaseModel):
    """The most recent evaluation report of one project.

    Keyed by project id, so a new run replaces the last one. Kept so the
    project export can include it — before this, a report existed only in the
    HTTP response that produced it.
    """

    id: str  # == project_id
    project_id: str
    created_at: datetime = Field(default_factory=utcnow)
    report: dict = Field(default_factory=dict)


class Chunk(BaseModel):
    """A text chunk derived from a document."""

    id: str
    document_id: str
    document_name: str = ""
    text: str
    page: int | None = None
    index: int = 0
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------
class Entity(BaseModel):
    """A named entity extracted from text."""

    id: str
    name: str
    type: str = "Concept"
    description: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    """A typed relation between two entities."""

    type: str
    properties: dict = Field(default_factory=dict)


class Triple(BaseModel):
    """A subject–relation–object triple."""

    subject: Entity
    relation: Relation
    object: Entity
    source_chunk_id: str | None = None
    confidence: float = 1.0


class GraphNode(BaseModel):
    id: str
    name: str
    group: str = "Concept"
    description: str = ""
    mentions: int = 1
    val: float = 2


class GraphLink(BaseModel):
    source: str
    target: str
    label: str = "RELATED_TO"
    confidence: float = 1.0


class GraphResponse(BaseModel):
    """Knowledge graph in react-force-graph shape."""

    nodes: list[GraphNode] = Field(default_factory=list)
    links: list[GraphLink] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Query / Response
# ---------------------------------------------------------------------------
class Citation(BaseModel):
    """Chunk-level provenance for a claim in an answer."""

    document_id: str = ""
    chunk_id: str = ""
    document_name: str = ""
    text: str = ""
    page: int | None = None
    score: float | None = None


class RetrievalResult(BaseModel):
    """A single retrieved chunk."""

    chunk_id: str
    document_id: str = ""
    document_name: str
    page: int | None = None
    text: str
    score: float
    graph_hit: bool = False


class QueryRequest(BaseModel):
    """Incoming research question."""

    question: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    session_id: str | None = None


class RetrievalResponse(BaseModel):
    """Answer plus the passages that grounded it."""

    question: str
    answer: str = ""
    results: list[RetrievalResult] = Field(default_factory=list)
    graph_context: list[dict] = Field(default_factory=list)


class QueryResponse(BaseModel):
    """Structured multi-agent answer.

    Fields below ``agent_trace`` are produced by the research workflows added
    after the mid-review; each is ``None`` unless the flow that produces it
    ran, so older clients are unaffected.
    """

    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    papers: list[dict] = Field(default_factory=list)
    analysis: dict | None = None
    routing: dict | None = None
    graph_stats: dict | None = None
    agent_trace: list[str] = Field(default_factory=list)

    # Research workflows
    comparison: dict | None = None
    gaps: dict | None = None
    hypotheses: dict | None = None
    experiments: dict | None = None
    patent_awareness: dict | None = None
    novelty: dict | None = None
    # What a literature search looked at: sources, queries, counts, warnings.
    literature_coverage: dict | None = None
    # A pasted project description, read into problem/methods/contributions.
    project_brief: dict | None = None


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    LITERATURE = "literature"
    ANALYSIS = "analysis"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    CITATION = "citation"
    SYNTHESIS = "synthesis"
    RETRIEVER = "retriever"
    INDEXER = "indexer"
    LOADER = "loader"
    PLANNER = "planner"
    COMPARISON = "comparison"


class AgentMessage(BaseModel):
    role: AgentRole
    content: str
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
class TaskStage(str, Enum):
    QUEUED = "queued"
    UPLOADING = "uploading"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    ORCHESTRATING = "orchestrating"
    RETRIEVING = "retrieving"
    ANALYZING = "analyzing"
    BUILDING_GRAPH = "building_graph"
    GENERATING_CITATIONS = "generating_citations"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskEvent(BaseModel):
    """One entry in the live Agent Activity log."""

    task_id: str
    timestamp: datetime = Field(default_factory=utcnow)
    agent_name: str
    stage: TaskStage = TaskStage.ORCHESTRATING
    status: TaskStatus = TaskStatus.RUNNING
    message: str = ""
    metadata: dict = Field(default_factory=dict)


class Task(BaseModel):
    """A multi-agent run, tracked end to end for the UI."""

    id: str
    project_id: str
    request: str
    flow: str | None = None
    document_id: str | None = None
    status: TaskStatus = TaskStatus.QUEUED
    current_stage: TaskStage = TaskStage.QUEUED
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    events: list[TaskEvent] = Field(default_factory=list)
    result: QueryResponse | None = None
    error: str | None = None
