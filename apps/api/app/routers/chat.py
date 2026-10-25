"""Chat router — streaming grounded answers over Server-Sent Events."""

from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.dependencies import get_chroma_store, get_generation_service
from app.store import metadata_store
from services.retrieval.hybrid import HybridRetriever

router = APIRouter(prefix="/projects/{project_id}/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)


def _sse(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("")
async def stream_chat(project_id: str, request: ChatRequest) -> StreamingResponse:
    """Stream a grounded answer, preceded by the sources that ground it.

    Event sequence: ``sources`` → many ``token`` → ``done``.
    """
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    chunks, _ = HybridRetriever(vector=get_chroma_store()).retrieve(
        request.question, project_id=project_id, top_k=request.top_k
    )

    async def generator() -> AsyncGenerator[str, None]:
        yield _sse(
            "sources",
            {
                "sources": [
                    {
                        "chunk_id": c.chunk_id,
                        "document_name": c.document_name,
                        "page": c.page,
                        "score": c.score,
                        "text": c.text[:400],
                    }
                    for c in chunks
                ]
            },
        )

        try:
            async for token in get_generation_service().generate_stream(
                request.question, chunks
            ):
                yield _sse("token", {"token": token})
        except Exception as exc:
            yield _sse("error", {"message": f"{type(exc).__name__}: {exc}"})

        yield _sse("done", {"ok": True})

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
