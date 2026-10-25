"""Tasks router — run the multi-agent pipeline and stream its progress.

Every agent run in MAIROS is a Task. The frontend creates one, then polls
``/tasks/{id}`` for the live activity log and the final answer.
"""

from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import CurrentUser, authorize, visible_project_ids
from app.config import settings
from app.dependencies import get_orchestrator
from app.store import metadata_store
from schemas import (
    Citation,
    QueryResponse,
    Task,
    TaskEvent,
    TaskStage,
    TaskStatus,
)

router = APIRouter(tags=["tasks"])


class CreateTaskRequest(BaseModel):
    """Submit a request to the multi-agent system."""

    question: str = Field(..., min_length=1)
    # Omit to let the Orchestrator's Router decide.
    flow: str | None = Field(
        None, description="Force a flow: 'search' | 'analyze' | 'answer'"
    )
    document_id: str | None = None


# ---------------------------------------------------------------------------
# Background execution
# ---------------------------------------------------------------------------
def _emit_event(
    task_id: str, agent_name: str, stage: str, status: str, message: str
) -> None:
    """Translate an agent log line into a persisted TaskEvent."""
    valid_stages = {s.value for s in TaskStage}
    valid_statuses = {s.value for s in TaskStatus}

    metadata_store.add_task_event(
        TaskEvent(
            task_id=task_id,
            agent_name=agent_name,
            stage=TaskStage(stage) if stage in valid_stages else TaskStage.ORCHESTRATING,
            status=(
                TaskStatus(status) if status in valid_statuses else TaskStatus.RUNNING
            ),
            message=message,
        )
    )


async def run_pipeline(
    task_id: str,
    question: str,
    project_id: str,
    flow: str | None = None,
    document_id: str | None = None,
) -> None:
    """Execute the orchestrator and record the result on the task."""
    if not metadata_store.get_task(task_id):
        return

    try:
        _emit_event(
            task_id, "orchestrator", "orchestrating", "running", "Task accepted"
        )

        orchestrator = get_orchestrator()
        ctx = await orchestrator.run(
            question=question,
            project_id=project_id,
            document_id=document_id,
            task_id=task_id,
            emit_event=_emit_event,
            flow_type=flow,
            doc_count=metadata_store.count_documents(project_id),
        )

        results = ctx.intermediate_results
        papers = results.get("retrieved_papers", [])
        references = results.get("references", [])

        # Persist discovered papers so the Papers list survives the task.
        for index, paper in enumerate(papers):
            metadata_store.add_paper(
                project_id,
                paper,
                reference=references[index] if index < len(references) else "",
            )

        metadata_store.update_task_result(
            task_id,
            QueryResponse(
                answer=results.get("final_answer", ""),
                citations=[
                    Citation(**c) for c in results.get("citations", []) if isinstance(c, dict)
                ],
                references=[str(r) for r in references],
                papers=papers,
                analysis=results.get("analysis"),
                routing=results.get("routing"),
                graph_stats=results.get("graph_stats"),
                agent_trace=ctx.trace,
                comparison=results.get("comparison"),
                gaps=results.get("gaps"),
                hypotheses=results.get("hypotheses"),
                experiments=results.get("experiments"),
                patent_awareness=results.get("patent_awareness"),
                novelty=results.get("novelty"),
                literature_coverage=results.get("literature_coverage"),
                project_brief=results.get("project_brief"),
            ),
        )

    except Exception as exc:  # a crash must still surface in the UI
        _emit_event(task_id, "orchestrator", "failed", "failed", str(exc))
        metadata_store.update_task_error(task_id, f"{type(exc).__name__}: {exc}")


def dispatch_pipeline(
    background_tasks: BackgroundTasks,
    task_id: str,
    question: str,
    project_id: str,
    flow: str | None = None,
    document_id: str | None = None,
) -> None:
    """Start :func:`run_pipeline` without holding up the HTTP response.

    In normal operation the run gets its own thread and event loop: agent work
    embeds, retrieves and calls the LLM synchronously in places, and on the
    server's loop that would stall every other request until the run finished.

    With ``run_tasks_inline`` it is a FastAPI background task instead, which
    the test client drives to completion before returning — so a test can
    create a task and read its finished result on the next line. This replaced
    a ``"pytest" in sys.modules`` check duplicated in two routers: production
    behaviour should be chosen by configuration, not by which modules happen to
    be imported.
    """
    args = (task_id, question, project_id, flow, document_id)
    if settings.run_tasks_inline:
        background_tasks.add_task(run_pipeline, *args)
        return

    threading.Thread(
        target=lambda: asyncio.run(run_pipeline(*args)),
        name=f"mairos-task-{task_id[:8]}",
        daemon=True,
    ).start()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/projects/{project_id}/tasks", response_model=Task, status_code=201)
async def create_task(
    project_id: str,
    request: CreateTaskRequest,
    background_tasks: BackgroundTasks,
) -> Task:
    """Start a multi-agent run and return the task immediately."""
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate against the live registry so a new flow is accepted the moment
    # it is registered in router.FLOWS — no second list to keep in sync.
    from services.agents.router import FLOWS

    if request.flow and request.flow not in FLOWS:
        raise HTTPException(
            status_code=400,
            detail="flow must be one of: " + ", ".join(sorted(FLOWS)),
        )

    task = metadata_store.create_task(
        project_id=project_id,
        request=request.question,
        flow=request.flow,
        document_id=request.document_id,
    )
    dispatch_pipeline(
        background_tasks,
        task.id,
        request.question,
        project_id,
        request.flow,
        request.document_id,
    )
    return task


@router.get("/flows")
async def list_flows() -> dict:
    """The registered agent flows and the pipeline each one runs.

    Read straight from ``router.FLOWS``, so the UI's workflow list can never
    drift from what the orchestrator will actually execute.
    """
    from services.agents.router import FLOW_DESCRIPTIONS, FLOWS

    return {
        "flows": [
            {
                "name": name,
                "agents": agents,
                "description": FLOW_DESCRIPTIONS.get(name, ""),
            }
            for name, agents in FLOWS.items()
        ]
    }


@router.get("/tasks", response_model=list[Task])
async def list_all_tasks(limit: int = 50, user: CurrentUser = Depends(authorize)) -> list[Task]:
    """Tasks across every project the caller can see, newest first."""
    return metadata_store.list_tasks(limit=limit, project_ids=visible_project_ids(user))


@router.get("/projects/{project_id}/tasks", response_model=list[Task])
async def list_project_tasks(project_id: str, limit: int = 50) -> list[Task]:
    """Tasks belonging to one project."""
    return metadata_store.list_tasks(project_id, limit=limit)


@router.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: str) -> Task:
    """Full task state — status, activity log, and result."""
    task = metadata_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks/{task_id}/events", response_model=list[TaskEvent])
async def get_task_events(task_id: str) -> list[TaskEvent]:
    """Just the agent activity log for a task."""
    task = metadata_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.events
