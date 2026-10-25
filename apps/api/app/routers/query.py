"""Query router — the RAG endpoint.

Retrieves the top-k passages for a question and asks the LLM to answer using
only those passages, citing each source. This is the synchronous path used by
the Chat tab; the Task path in ``tasks.py`` wraps the same machinery in the
full agent pipeline.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import get_chroma_store, get_generation_service
from app.store import metadata_store
from schemas import RetrievalResponse, RetrievalResult
from services.retrieval.hybrid import HybridRetriever

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


@router.post("/projects/{project_id}/query", response_model=RetrievalResponse)
async def query_project(project_id: str, req: QueryRequest) -> RetrievalResponse:
    """Answer a question grounded in this project's indexed documents."""
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    chroma = get_chroma_store()
    retriever = HybridRetriever(vector=chroma)

    chunks, graph_results = retriever.retrieve(
        req.question, project_id=project_id, top_k=req.top_k
    )

    results = [
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
    ]

    if not chunks:
        return RetrievalResponse(
            question=req.question,
            answer=(
                "I cannot answer this based on the provided documents — this "
                "project has no matching indexed content yet. Upload a PDF or run "
                "a topic search first."
            ),
            results=[],
            graph_context=[],
        )

    answer = await get_generation_service().generate(req.question, chunks)

    graph_context = (
        [
            {
                "entity": g.entity,
                "relation": g.relation,
                "related_entity": g.related_entity,
            }
            for g in graph_results[:20]
        ]
        if req.use_graph
        else []
    )

    return RetrievalResponse(
        question=req.question,
        answer=answer,
        results=results,
        graph_context=graph_context,
    )


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
