"""Streaming chat — the same agent run as ``/query``, reported as it happens.

Event sequence: one ``step`` per agent event as the orchestrator's ``answer``
flow runs (retriever → synthesis → citation), then ``sources``, the answer as
a ``token``, and ``done`` with the task id. The answer arrives whole: the
synthesis agent writes it from the retrieved passages before anything is
shown, so streaming it word by word would only replay finished text.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.store import metadata_store

from .query import answer_response
from .tasks import answer_through_agents

router = APIRouter(prefix="/projects/{project_id}/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)


def _sse(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("")
async def stream_chat(project_id: str, request: ChatRequest) -> StreamingResponse:
    """Answer through the agents, streaming each agent step as it runs."""
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_event(task_id, agent_name, stage, status, message) -> None:
        # Called from the run's own thread; hand the event to this loop.
        step = {"agent": agent_name, "stage": stage, "status": status, "message": message}
        loop.call_soon_threadsafe(queue.put_nowait, ("step", step))

    async def run() -> None:
        try:
            outcome = await answer_through_agents(
                project_id, request.question, top_k=request.top_k, on_event=on_event
            )
        except Exception as exc:  # reported to the client below
            outcome = (None, exc)
        await queue.put(("finished", outcome))

    async def generator() -> AsyncGenerator[str, None]:
        runner = asyncio.create_task(run())
        while True:
            kind, data = await queue.get()
            if kind == "step":
                yield _sse("step", data)
                continue
            break
        await runner

        task_id, ctx = data
        if not hasattr(ctx, "intermediate_results"):
            task = metadata_store.get_task(task_id) if task_id else None
            reason = task.error if task else f"{type(ctx).__name__}: {ctx}"
            yield _sse("error", {"message": f"The answer run failed: {reason}"})
            yield _sse("done", {"ok": False, "task_id": task_id})
            return

        response = answer_response(request.question, task_id, ctx)
        yield _sse(
            "sources",
            {
                "sources": [
                    {
                        "chunk_id": r.chunk_id,
                        "document_name": r.document_name,
                        "page": r.page,
                        "score": r.score,
                        "text": r.text[:400],
                    }
                    for r in response.results
                ]
            },
        )
        yield _sse("token", {"token": response.answer})
        yield _sse("done", {"ok": True, "task_id": task_id})

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
