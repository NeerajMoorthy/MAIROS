"""RAGAS answer-quality scoring — optional, model-judged, never faked.

Retrieval metrics (Recall@k, MRR, nDCG@k) are arithmetic over rankings: they
need no model and they are reproducible. The four metrics here are different in
kind — a language model reads the answer and judges it — so they are kept in a
separate module with a separate availability check, and the dashboard labels
them as model-judged rather than computed.

Two things have to be true before a score exists: ``ragas`` is importable, and
a live LLM is configured. Either one missing means the report says so and shows
no number. There is deliberately no code path that produces a default,
placeholder, or "estimated" score.
"""

from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

METRIC_NAMES = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
]

# The judge writes structured verdicts, and a reasoning model spends part of
# its budget thinking first; the agents' 1400-token cap cut verdicts short.
JUDGE_MAX_TOKENS = 4096
# Groq's free tier allows about 30 requests a minute, so a few judge calls at a
# time, with patient retries, rather than RAGAS's default of 16.
JUDGE_WORKERS = 3


def ragas_installed() -> bool:
    """Is the optional dependency importable?"""
    return importlib.util.find_spec("ragas") is not None


def llm_is_live() -> bool:
    """Is a real model configured, as opposed to the offline stand-in?"""
    try:
        from services.generation.provider import describe_provider

        return bool(describe_provider().get("live"))
    except Exception:
        return False


@dataclass
class AnswerQualityReport:
    """Scores, or a plain statement of why there are none."""

    available: bool = False
    metrics: list[str] = field(default_factory=lambda: list(METRIC_NAMES))
    scores: dict[str, float] | None = None
    per_case: list[dict] = field(default_factory=list)
    judged_by: str | None = None
    reason: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "metrics": self.metrics,
            "scores": self.scores,
            "per_case": self.per_case,
            "judged_by": self.judged_by,
            "reason": self.reason,
            "note": self.note,
            # The dashboard shows this next to the numbers so nobody mistakes a
            # model's opinion for a computed quantity.
            "kind": "model_judged",
        }


def unavailable_report() -> AnswerQualityReport:
    """The honest report for an environment that cannot produce scores."""
    has_ragas = ragas_installed()
    has_llm = llm_is_live()

    if has_ragas and has_llm:
        reason = "ready"
        note = "RAGAS and a live model are both available."
    elif not has_ragas and not has_llm:
        reason = "ragas_not_installed_and_no_live_llm"
        note = (
            "Answer-quality metrics need both the optional `ragas` package and a "
            "live LLM; neither is configured, so no score is shown for them. "
            "Retrieval metrics are computed without either and are unaffected."
        )
    elif not has_ragas:
        reason = "ragas_not_installed"
        note = (
            "RAGAS is not installed, so faithfulness and answer relevancy are not "
            "measured. Install the backend requirements "
            "(`pip install -r apps/api/requirements.txt`) and restart the API."
        )
    else:
        reason = "no_live_llm"
        note = (
            "RAGAS is installed but no live LLM is configured, and these metrics "
            "require a model to judge the answers. Set GROQ_API_KEY to enable them."
        )

    return AnswerQualityReport(
        available=has_ragas and has_llm,
        scores=None,
        reason=reason,
        note=note,
    )


def build_samples(
    cases: Sequence,
    answer_fn: Callable[[str], tuple[str, list[str]]],
) -> list[dict]:
    """Assemble the (question, answer, contexts, ground_truth) rows RAGAS wants.

    Args:
        cases: Golden-set cases with ``question`` and ``expected_answer``.
        answer_fn: ``question -> (answer, contexts)`` — the real RAG path, so
            what is judged is what the system would actually have replied.
    """
    samples: list[dict] = []
    for case in cases:
        question = getattr(case, "question", None) or case.get("question", "")
        expected = getattr(case, "expected_answer", None) or case.get("expected_answer", "")
        if not question:
            continue
        answer, contexts = answer_fn(question)
        samples.append(
            {
                "question": question,
                "answer": answer,
                "contexts": list(contexts),
                "ground_truth": expected,
            }
        )
    return samples


def local_embeddings(embed: Callable[[list[str]], Any]):
    """The project's own sentence-transformers embedder, in LangChain's shape.

    RAGAS needs embeddings for answer relevancy and otherwise reaches for
    OpenAI's, which MAIROS has no key for. Built on call so this module still
    imports where LangChain is missing.
    """
    from langchain_core.embeddings import Embeddings

    class LocalEmbeddings(Embeddings):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[float(x) for x in vector] for vector in embed(list(texts))]

        def embed_query(self, text: str) -> list[float]:
            return self.embed_documents([text])[0]

    return LocalEmbeddings()


def default_judge_llm():
    """The configured live model, set up to judge rather than to chat."""
    from services.generation.provider import get_chat_model

    return get_chat_model(temperature=0.0, max_tokens=JUDGE_MAX_TOKENS)


def default_judge_embeddings():
    """The same local embedder the vector store uses."""
    from services.retrieval.vector_store import ChromaStore

    return ChromaStore(persist_dir=".").embedding_function


def _mean(values) -> float | None:
    """Average of the scores RAGAS managed to produce (failed jobs are NaN)."""
    numbers = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isnan(number):
            numbers.append(number)
    return round(sum(numbers) / len(numbers), 4) if numbers else None


def score_samples(
    samples: Sequence[dict],
    llm=None,
    embeddings: Callable[[list[str]], Any] | None = None,
) -> AnswerQualityReport:
    """Run RAGAS over prepared samples.

    Args:
        samples: Rows from :func:`build_samples`.
        llm: LangChain chat model that judges; defaults to the live model.
        embeddings: ``texts -> vectors``; defaults to the local embedder.

    Returns an unavailable report — never a fabricated one — when the
    dependency is missing, no model is live, there is nothing to score, or the
    evaluation itself fails.
    """
    report = unavailable_report()
    if not report.available:
        return report

    # A case the project has no passages for has nothing to be faithful to;
    # judging an empty answer against empty context only measures noise.
    judgeable = [s for s in samples if s.get("answer") and s.get("contexts")]
    if not judgeable:
        return AnswerQualityReport(
            available=False,
            scores=None,
            reason="no_samples",
            note=(
                "No golden-set case produced an answer from this project's passages, "
                "so there is nothing to judge."
            ),
        )

    try:
        from ragas import EvaluationDataset, RunConfig, evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        dataset = EvaluationDataset.from_list(
            [
                {
                    "user_input": s["question"],
                    "response": s["answer"],
                    "retrieved_contexts": list(s["contexts"]),
                    "reference": s.get("ground_truth") or "",
                }
                for s in judgeable
            ]
        )
        # Without an explicit judge and embedder RAGAS defaults to OpenAI.
        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
            llm=llm if llm is not None else default_judge_llm(),
            embeddings=local_embeddings(embeddings or default_judge_embeddings()),
            run_config=RunConfig(max_workers=JUDGE_WORKERS, timeout=180, max_retries=6, max_wait=60),
            show_progress=False,
        )

        rows = result.to_pandas().to_dict("records")
        scores: dict[str, float] = {}
        for name in METRIC_NAMES:
            value = _mean(row.get(name) for row in rows)
            if value is not None:
                scores[name] = value

        if not scores:
            return AnswerQualityReport(
                available=False,
                scores=None,
                reason="no_scores_returned",
                note=(
                    "RAGAS ran but every judgement failed (often the model's rate "
                    "limit), so no scores are shown."
                ),
            )

        per_case = [
            {"question": sample["question"], **{name: _mean([row.get(name)]) for name in METRIC_NAMES}}
            for sample, row in zip(judgeable, rows)
        ]

        from services.generation.provider import describe_provider

        skipped = len(samples) - len(judgeable)
        return AnswerQualityReport(
            available=True,
            scores=scores,
            per_case=per_case,
            judged_by=describe_provider().get("model"),
            reason="ok",
            note=(
                f"Model-judged scores over {len(judgeable)} golden-set "
                f"case{'s' if len(judgeable) != 1 else ''}"
                + (
                    f" ({skipped} skipped: this project has no passages for them)"
                    if skipped
                    else ""
                )
                + ". These are one model's assessment of another model's answers, "
                "not a computed quantity."
            ),
        )

    except Exception as exc:  # a judge that fails must not invent a verdict
        return AnswerQualityReport(
            available=False,
            scores=None,
            reason="evaluation_failed",
            note=f"RAGAS evaluation failed ({type(exc).__name__}: {exc}); no scores are shown.",
        )


__all__ = [
    "AnswerQualityReport",
    "METRIC_NAMES",
    "build_samples",
    "llm_is_live",
    "local_embeddings",
    "ragas_installed",
    "score_samples",
    "unavailable_report",
]
