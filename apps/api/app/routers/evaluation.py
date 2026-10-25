"""Evaluation router — retrieval quality metrics over the curated golden set.

Three endpoints:

* ``GET  /evaluation/status``            — what can be measured right now.
* ``GET  /evaluation/golden-set``        — the curated cases, so a reviewer can
  read exactly what is being asked before trusting any number.
* ``POST /projects/{id}/evaluation/run`` — score this project's retriever.

Everything reported here is computed. Retrieval metrics (Recall@k, MRR,
Precision@k, nDCG@k) need no LLM and always run; RAGAS answer-quality metrics
need an optional dependency and are reported as unavailable — never as a
placeholder score — when it is missing.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.dependencies import get_chroma_store, get_generation_service
from app.store import metadata_store
from services.evaluation.golden_set import GoldenSet
from services.evaluation.ragas_runner import llm_is_live, unavailable_report
from services.evaluation.runner import RAGAS_METRICS, RetrievalEvaluator, ragas_available
from services.retrieval.hybrid import HybridRetriever

router = APIRouter(tags=["evaluation"])


class EvaluationRunRequest(BaseModel):
    """Options for one evaluation run."""

    k: int = Field(5, ge=1, le=20, description="Cut-off for Recall@k / Precision@k / nDCG@k")
    answer_quality: bool = Field(
        False,
        description=(
            "Also score answers with RAGAS. Requires the optional `ragas` package "
            "and a live LLM; generates an answer per golden-set case, so it is "
            "slower and costs model calls. Off by default."
        ),
    )


@router.get("/evaluation/status")
async def evaluation_status() -> dict:
    """What the harness can measure in this environment, and what it cannot."""
    golden = GoldenSet()
    has_ragas = ragas_available()
    answer_quality = unavailable_report()

    return {
        "status": "ready" if len(golden) else "no_golden_set",
        "retrieval_metrics_available": len(golden) > 0,
        "retrieval_metrics": ["recall_at_k", "precision_at_k", "mrr", "ndcg_at_k"],
        # Two conditions, not one: the package AND a live model to judge with.
        "answer_metrics_available": answer_quality.available,
        "answer_metrics_reason": answer_quality.reason,
        "answer_metrics_note": answer_quality.note,
        "ragas_installed": has_ragas,
        "llm_live": llm_is_live(),
        "metrics": RAGAS_METRICS,
        "golden_set_configured": len(golden) > 0,
        "golden_set_size": len(golden),
        "golden_set_name": golden.metadata.get("name", ""),
        "relevance_policy": golden.metadata.get("relevance_policy", "term_match"),
        "note": (
            "Retrieval metrics are computed live against a project's indexed "
            "chunks and need no LLM. " + answer_quality.note
        ),
    }


@router.get("/evaluation/golden-set")
async def get_golden_set() -> dict:
    """The curated test cases, with the relevance rule each one uses."""
    golden = GoldenSet()
    return {
        "metadata": golden.metadata,
        "size": len(golden),
        "cases": [
            {
                "id": case.id,
                "question": case.question,
                "expected_answer": case.expected_answer,
                "required_entities": case.required_entities,
                "source_documents": case.source_documents,
                "difficulty": case.difficulty,
                "tags": case.tags,
                "policy": case.policy,
            }
            for case in golden
        ],
    }


@router.post("/projects/{project_id}/evaluation/run")
async def run_evaluation(project_id: str, request: EvaluationRunRequest) -> dict:
    """Score this project's retrieval against every curated case."""
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    store = get_chroma_store()
    retriever = HybridRetriever(vector=store)

    def retrieve(question: str, k: int) -> list[dict]:
        chunks, _ = retriever.retrieve(question, project_id=project_id, top_k=k)
        return [
            {
                "chunk_id": chunk.chunk_id,
                "document_name": chunk.document_name,
                "page": chunk.page,
                "text": chunk.text,
                "score": chunk.score,
            }
            for chunk in chunks
        ]

    def corpus() -> list[dict]:
        return store.all_chunks(project_id=project_id)

    def answer(question: str) -> tuple[str, list[str]]:
        """The real RAG path, so RAGAS judges what the system would have said.

        Called from the worker thread below, where ``asyncio.run`` is safe —
        driving the coroutine on the request's own loop would deadlock, since
        that loop is what is waiting for this function to return.
        """
        chunks, _ = retriever.retrieve(question, project_id=project_id, top_k=request.k)
        if not chunks:
            return "", []
        generated = asyncio.run(get_generation_service().generate(question, chunks))
        return generated, [chunk.text for chunk in chunks]

    evaluator = RetrievalEvaluator(
        retrieve_fn=retrieve,
        corpus_fn=corpus,
        k=request.k,
        answer_fn=answer if request.answer_quality else None,
    )

    # Retrieval, RAGAS and the embedding model are all blocking; running them
    # on the event loop would stall every other request for the duration.
    report = await run_in_threadpool(evaluator.run)

    payload = report.to_dict()
    payload["project_id"] = project_id
    # The latest report is kept so the project export can include it.
    metadata_store.save_evaluation(project_id, payload)
    return payload
