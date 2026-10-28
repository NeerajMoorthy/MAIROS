"""Query router — the Chat tab's endpoint.

A question is answered by the orchestrator's ``answer`` flow: the retriever
agent finds the passages, the synthesis agent answers from them only, and the
citation agent formats the sources. ``/retrieve`` stays a plain retrieval call
for debugging the index.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import get_chroma_store
from app.store import metadata_store
from schemas import RetrievalResponse, RetrievalResult
from services.retrieval.hybrid import HybridRetriever

from .tasks import answer_through_agents

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    """Router-local request model: adds ``use_graph`` to the shared schema.

    The response models come from ``packages/shared-types`` rather than being
    redeclared here — one definition of the API contract, so the backend and
    the typed frontend client cannot drift apart.
    """

    question: str = Field(..., min_length=1, description="The research question")
    top_k: int = Field(5, ge=1, le=50, description="Passages to retrieve")
    use_graph: bool = Field(True, description="Blend in knowledge-graph context")


def answer_response(question: str, task_id: str, ctx, use_graph: bool = True) -> RetrievalResponse:
    """The chat answer, built from the context the ``answer`` flow finished with."""
    return RetrievalResponse(
        question=question,
        answer=ctx.intermediate_results.get("final_answer", ""),
        results=[
            RetrievalResult(
                chunk_id=c["chunk_id"],
                document_id=c["document_id"],
                document_name=c.get("document_name") or "Unknown document",
                page=c.get("page"),
                text=c["text"],
                score=c.get("score", 0.0),
                graph_hit=bool(c.get("graph_hit")),
            )
            for c in ctx.retrieved_chunks
        ],
        graph_context=list(ctx.graph_results[:20]) if use_graph else [],
        task_id=task_id,
    )


@router.post("/projects/{project_id}/query", response_model=RetrievalResponse)
async def query_project(project_id: str, req: QueryRequest) -> RetrievalResponse:
    """Answer a question grounded in this project's indexed documents.

    The question runs through the orchestrator's ``answer`` flow — retriever,
    synthesis and citation agents — as a recorded task, so it shows in Agent
    Activity like every workflow.
    """
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    task_id, ctx = await answer_through_agents(project_id, req.question, top_k=req.top_k)
    if ctx is None:
        task = metadata_store.get_task(task_id)
        raise HTTPException(
            status_code=500,
            detail=f"The answer run failed: {task.error if task else 'unknown error'}",
        )
    return answer_response(req.question, task_id, ctx, use_graph=req.use_graph)


@router.post("/projects/{project_id}/retrieve", response_model=RetrievalResponse)
async def retrieve_only(project_id: str, req: QueryRequest) -> RetrievalResponse:
    """Retrieval without generation — useful for debugging the vector store."""
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    chunks, graph_results = HybridRetriever(vector=get_chroma_store()).retrieve(
        req.question, project_id=project_id, top_k=req.top_k
    )

    return RetrievalResponse(
        question=req.question,
        answer="",
        results=[
            RetrievalResult(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                document_name=c.document_name or "Unknown document",
                page=c.page,
                text=c.text,
                score=c.score,
                graph_hit=bool(c.metadata.get("graph_hit")),
            )
            for c in chunks
        ],
        graph_context=[
            {
                "entity": g.entity,
                "relation": g.relation,
                "related_entity": g.related_entity,
            }
            for g in graph_results[:20]
        ],
    )
