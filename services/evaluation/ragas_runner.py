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
from dataclasses import dataclass, field
from typing import Callable, Sequence

METRIC_NAMES = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
]


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
            'measured. Install with `pip install "ragas>=0.2,<1"`.'
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


def score_samples(samples: Sequence[dict]) -> AnswerQualityReport:
    """Run RAGAS over prepared samples.

    Returns an unavailable report — never a fabricated one — when the
    dependency is missing, no model is live, there is nothing to score, or the
    evaluation itself fails.
    """
    report = unavailable_report()
    if not report.available:
        return report

    if not samples:
        return AnswerQualityReport(
            available=False,
            scores=None,
            reason="no_samples",
            note="No golden-set case produced an answer to judge.",
        )

    try:
        from datasets import Dataset  # provided by ragas' own dependencies
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        result = evaluate(
            Dataset.from_list(list(samples)),
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        )

        scores: dict[str, float] = {}
        for name in METRIC_NAMES:
            value = result.get(name) if hasattr(result, "get") else None
            if value is None:
                continue
            try:
                scores[name] = round(float(value), 4)
            except (TypeError, ValueError):
                continue

        if not scores:
            return AnswerQualityReport(
                available=False,
                scores=None,
                reason="no_scores_returned",
                note="RAGAS ran but returned no usable scores, so none are shown.",
            )

        from services.generation.provider import describe_provider

        return AnswerQualityReport(
            available=True,
            scores=scores,
            per_case=[],
            judged_by=describe_provider().get("model"),
            reason="ok",
            note=(
                "Model-judged scores over the golden set. These are one model's "
                "assessment of another model's answers, not a computed quantity."
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
    "ragas_installed",
    "score_samples",
    "unavailable_report",
]
