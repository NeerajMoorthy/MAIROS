"""Workspace router — Settings: load the example workspace, clear everything.

*Load example data* creates the "RailGuard Lite (example)" project from
``services/samples/railguard.py``: its three sample papers are indexed (each
followed by the usual analysis run), and the fictional patent is stored, so
every workflow, chat, the graph, Tasks and Patents have something to work on
straight away. Loading again replaces the previous example project rather
than adding a second one.

*Clear workspace* deletes every project the caller can see, with everything
each one holds. It is irreversible, so the request must say so explicitly.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.auth import CurrentUser, authorize, owner_filter
from app.store import metadata_store
from services.samples import railguard

from .ingest import index_pdf
from .projects import remove_project
from .tasks import dispatch_pipelines_in_order

router = APIRouter(tags=["workspace"])

# What the caller must send to clear the workspace; anything else is refused.
CLEAR_CONFIRMATION = "delete-everything"


class SampleFile(BaseModel):
    name: str
    description: str


class GuideStep(BaseModel):
    feature: str
    where: str
    flow: str | None = None
    input: str = ""
    expect: str


class ExampleWorkspaceInfo(BaseModel):
    name: str
    description: str
    files: list[SampleFile]
    guide: list[GuideStep]


class ExampleDocument(BaseModel):
    document_id: str
    filename: str
    num_pages: int
    num_chunks: int
    task_id: str


class ExampleWorkspaceResponse(BaseModel):
    project_id: str
    name: str
    documents: list[ExampleDocument]
    patent_id: str
    # Example projects that loading this one replaced.
    replaced: int = 0


class ClearWorkspaceResponse(BaseModel):
    deleted: int


def _example_projects(user: CurrentUser) -> list[str]:
    return [
        project.id
        for project in metadata_store.list_projects(owner_id=owner_filter(user))
        if project.name == railguard.EXAMPLE_PROJECT_NAME
    ]


@router.get("/workspace/example", response_model=ExampleWorkspaceInfo)
async def describe_example_workspace() -> ExampleWorkspaceInfo:
    """What the example holds: its name, downloadable files, and what to try."""
    return ExampleWorkspaceInfo(
        name=railguard.EXAMPLE_PROJECT_NAME,
        description=railguard.EXAMPLE_PROJECT_DESCRIPTION,
        files=[SampleFile(name=name, description=text) for name, _, text in railguard.SAMPLE_FILES],
        guide=[GuideStep(**step) for step in railguard.EXAMPLE_GUIDE],
    )


@router.get("/workspace/example/files/{name}")
async def download_sample_file(name: str) -> Response:
    """One sample file. Only the files listed by GET /workspace/example exist."""
    media = {file: media_type for file, media_type, _ in railguard.SAMPLE_FILES}
    if name not in media:
        raise HTTPException(status_code=404, detail="No such sample file")
    content = await run_in_threadpool(railguard.sample_file, name)
    return Response(
        content=content,
        media_type=media[name],
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/workspace/example", response_model=ExampleWorkspaceResponse, status_code=201)
async def load_example_workspace(
    background_tasks: BackgroundTasks, user: CurrentUser = Depends(authorize)
) -> ExampleWorkspaceResponse:
    """Create the example project: three indexed papers, their analysis runs, a patent."""
    replaced = _example_projects(user)
    for project_id in replaced:
        remove_project(project_id)

    project = metadata_store.create_project(
        railguard.EXAMPLE_PROJECT_NAME,
        railguard.EXAMPLE_PROJECT_DESCRIPTION,
        owner_id=user.id,
    )

    try:
        papers = await run_in_threadpool(railguard.paper_files)
        indexed = []
        for filename, content in papers:
            result = await run_in_threadpool(index_pdf, project.id, filename, content)
            indexed.append((filename, result))
    except Exception as exc:
        # A half-built example would only confuse; take it away again.
        try:
            remove_project(project.id)
        except HTTPException:
            pass
        raise HTTPException(
            status_code=500, detail=f"The example papers could not be indexed: {exc}"
        ) from exc

    patent = metadata_store.add_patent(
        project_id=project.id,
        title=railguard.PATENT_TITLE,
        text=railguard.PATENT_TEXT,
        source="manual entry",
    )

    documents: list[ExampleDocument] = []
    runs = []
    for filename, result in indexed:
        task = metadata_store.create_task(
            project_id=project.id,
            request=f"Analyse uploaded document: {filename}",
            flow="analyze",
            document_id=result["document_id"],
        )
        runs.append((
            task.id,
            f"Analyse the paper '{filename}': key contributions, methodology, summary.",
            project.id,
            "analyze",
            result["document_id"],
        ))
        documents.append(ExampleDocument(
            document_id=result["document_id"],
            filename=filename,
            num_pages=result["num_pages"],
            num_chunks=result["num_chunks"],
            task_id=task.id,
        ))
    dispatch_pipelines_in_order(background_tasks, runs)

    return ExampleWorkspaceResponse(
        project_id=project.id,
        name=project.name,
        documents=documents,
        patent_id=patent.id,
        replaced=len(replaced),
    )


@router.delete("/workspace", response_model=ClearWorkspaceResponse)
async def clear_workspace(
    confirm: str = Query("", description=f"Must be '{CLEAR_CONFIRMATION}'"),
    user: CurrentUser = Depends(authorize),
) -> ClearWorkspaceResponse:
    """Delete every project the caller can see, with all of its data."""
    if confirm != CLEAR_CONFIRMATION:
        raise HTTPException(
            status_code=400,
            detail=f"Clearing the workspace deletes every project. Send confirm={CLEAR_CONFIRMATION} to proceed.",
        )
    projects = metadata_store.list_projects(owner_id=owner_filter(user))
    for project in projects:
        await run_in_threadpool(remove_project, project.id)
    return ClearWorkspaceResponse(deleted=len(projects))
