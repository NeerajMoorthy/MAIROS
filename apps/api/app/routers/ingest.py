"""Ingest router — upload a PDF and kick off the analysis pipeline.

Ingestion is synchronous (extract → chunk → embed) so the caller immediately
knows the document is queryable. The agent work that follows — Analysis,
Knowledge Graph, Citation — runs in the background as a Task so the UI can
show it live.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.dependencies import get_chroma_store
from app.store import metadata_store
from services.ingestion.pipeline import IngestionPipeline

from .tasks import dispatch_pipeline

router = APIRouter(tags=["ingest"])


class IngestResponse(BaseModel):
    """Result of document ingestion."""

    document_id: str
    project_id: str
    filename: str
    num_pages: int
    num_chunks: int
    status: str
    # Follow this to watch the Analysis → KG → Citation agents run.
    task_id: str | None = None


@router.post(
    "/projects/{project_id}/documents",
    response_model=IngestResponse,
    status_code=201,
)
async def ingest_document(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> IngestResponse:
    """Upload a PDF: extract, chunk, embed, then analyse it with the agents."""
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    # The middleware already refuses an oversized body before it is read; this
    # is the same configured cap, kept as a second line of defence.
    max_bytes = settings.max_upload_bytes
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {max_bytes // (1024 * 1024)} MB limit",
        )

    upload_dir = Path(settings.upload_dir) / project_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Stored under a generated name only. The original filename is kept in the
    # document metadata; putting it in the path as well made a long name
    # overflow Windows' 260-character path limit and fail the upload with a
    # bare FileNotFoundError, and carried whatever characters the user's file
    # name happened to contain onto the server's disk.
    file_path = upload_dir / f"{uuid.uuid4().hex}.pdf"
    file_path.write_bytes(content)

    # ---- Synchronous ingestion ---------------------------------------
    # Extraction and embedding are CPU-bound and synchronous. Run on the event
    # loop, they froze every other request — including the task polling the UI
    # does while an upload is in flight — for the whole of the embedding pass.
    try:
        pipeline = IngestionPipeline(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            chroma_store=get_chroma_store(),
        )
        result = await run_in_threadpool(
            pipeline.ingest, pdf_path=file_path, project_id=project_id, document_name=filename
        )
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    if result["num_chunks"] == 0:
        # Nothing was indexed, so keep nothing: an orphaned upload would only
        # be found again by project deletion.
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail=(
                "No text could be extracted from this PDF. It is probably a "
                "scanned image — OCR is not part of the mid-review build."
            ),
        )

    metadata_store.add_document(
        project_id=project_id,
        document_id=result["document_id"],
        filename=filename,
        num_pages=result["num_pages"],
        num_chunks=result["num_chunks"],
        title=result.get("title") or filename,
        # Which file on disk is this document's original, for the export.
        metadata={"stored_file": file_path.name},
    )

    # ---- Background agent run ----------------------------------------
    task = metadata_store.create_task(
        project_id=project_id,
        request=f"Analyse uploaded document: {filename}",
        flow="analyze",
        document_id=result["document_id"],
    )
    dispatch_pipeline(
        background_tasks,
        task.id,
        f"Analyse the paper '{filename}': key contributions, methodology, summary.",
        project_id,
        "analyze",
        result["document_id"],
    )

    return IngestResponse(
        document_id=result["document_id"],
        project_id=project_id,
        filename=filename,
        num_pages=result["num_pages"],
        num_chunks=result["num_chunks"],
        status="completed",
        task_id=task.id,
    )
