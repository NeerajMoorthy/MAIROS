"""Projects router — research workspaces."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.auth import CurrentUser, authorize, owner_filter
from app.config import settings
from app.dependencies import get_chroma_store
from app.export import build_json, build_zip
from app.store import metadata_store
from schemas import Paper
from services.knowledge_graph.networkx_store import kg_store

router = APIRouter(tags=["projects"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Project name")
    description: str = Field("", description="Optional summary of the research topic")


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    created_at: str
    document_ids: list[str] = []
    paper_ids: list[str] = []
    num_documents: int = 0
    num_papers: int = 0


class DocumentSummary(BaseModel):
    id: str
    filename: str
    title: str | None = None
    num_pages: int
    num_chunks: int
    ingested_at: str


class ProjectDetailResponse(ProjectResponse):
    documents: list[DocumentSummary] = []


def _to_response(project, *, detail: bool = False):
    docs = metadata_store.list_documents(project.id)
    payload = {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": (
            project.created_at.isoformat()
            if hasattr(project.created_at, "isoformat")
            else str(project.created_at)
        ),
        "document_ids": project.document_ids,
        "paper_ids": project.paper_ids,
        "num_documents": len(docs),
        "num_papers": len(project.paper_ids),
    }
    if not detail:
        return ProjectResponse(**payload)

    return ProjectDetailResponse(
        **payload,
        documents=[
            DocumentSummary(
                id=d.id,
                filename=d.filename,
                title=d.title,
                num_pages=d.num_pages,
                num_chunks=d.num_chunks,
                ingested_at=(
                    d.ingested_at.isoformat()
                    if hasattr(d.ingested_at, "isoformat")
                    else str(d.ingested_at)
                ),
            )
            for d in docs
        ],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    req: CreateProjectRequest, user: CurrentUser = Depends(authorize)
) -> ProjectResponse:
    """Create a research workspace, owned by the caller when auth is on."""
    project = metadata_store.create_project(req.name, req.description, owner_id=user.id)
    return _to_response(project)


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(user: CurrentUser = Depends(authorize)) -> list[ProjectResponse]:
    """The caller's projects (all of them in local mode), newest first."""
    return [_to_response(p) for p in metadata_store.list_projects(owner_id=owner_filter(user))]


@router.get("/projects/{project_id}", response_model=ProjectDetailResponse)
async def get_project(project_id: str) -> ProjectDetailResponse:
    """One project with its document list."""
    project = metadata_store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return _to_response(project, detail=True)


@router.get("/projects/{project_id}/papers", response_model=list[Paper])
async def list_papers(project_id: str) -> list[Paper]:
    """Papers discovered by the Literature agent for this project."""
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return metadata_store.list_papers(project_id)


@router.get("/projects/{project_id}/stats")
async def project_stats(project_id: str) -> dict:
    """Counts shown on the workspace header."""
    project = metadata_store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tasks = metadata_store.list_tasks(project_id, limit=1000)
    task_counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
    for t in tasks:
        task_counts[t.status.value] = task_counts.get(t.status.value, 0) + 1

    return {
        "documents": metadata_store.count_documents(project_id),
        "papers": len(metadata_store.list_papers(project_id)),
        # Scoped to this project — an unscoped count reports every project's
        # chunks on every project's dashboard.
        "chunks": get_chroma_store().count(project_id=project_id),
        "graph": kg_store.for_project(project_id).stats(),
        "tasks": len(tasks),
        "task_counts": task_counts,
    }


@router.get("/projects/{project_id}/export")
async def export_project(
    project_id: str,
    format: str = Query("zip", pattern="^(zip|json)$"),
    include_originals: bool = Query(False, description="Add the uploaded PDFs (ZIP only)"),
) -> Response:
    """Download everything this project holds — see ``app/export.py``.

    ZIP: README, manifest, project, chunks (JSONL + CSV), graph, tasks, the
    latest evaluation, patent records, and optionally the original PDFs.
    JSON: the same data as one document, without originals.
    """
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    if format == "json" and include_originals:
        raise HTTPException(
            status_code=400,
            detail="Original PDFs can only be included in a ZIP export.",
        )

    # Reading the whole index (and possibly every upload) is blocking work.
    if format == "json":
        body, filename = await run_in_threadpool(build_json, project_id)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    spool, size, filename = await run_in_threadpool(build_zip, project_id, include_originals)

    def stream():
        try:
            for block in iter(lambda: spool.read(1024 * 1024), b""):
                yield block
        finally:
            spool.close()

    return StreamingResponse(
        stream(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(size),
        },
    )


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str) -> None:
    """Remove a project and its persisted metadata, index, graph, and files."""
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    upload_root = Path(settings.upload_dir).resolve()
    project_uploads = (upload_root / project_id).resolve()
    if upload_root not in project_uploads.parents:
        raise HTTPException(status_code=400, detail="Invalid project storage path")

    try:
        # Clean external stores before deleting the metadata row. If a store is
        # unavailable, keep the project visible so the user can retry cleanup.
        get_chroma_store().delete_project(project_id)
        if project_uploads.exists():
            shutil.rmtree(project_uploads)
        kg_store.delete_project(project_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Project data could not be fully removed. The project is still "
                "available; retry after storage is available."
            ),
        ) from exc

    if not metadata_store.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
