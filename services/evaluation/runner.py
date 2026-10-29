"""Evaluation runner — scores real retrieval against the golden set.

The runner is deliberately decoupled from FastAPI and from ChromaDB: it takes
a ``retrieve_fn`` and a ``corpus_fn`` and knows nothing else, so the whole
harness runs in a unit test with two list comprehensions standing in for the
vector store.

**Why the corpus scan matters.** Recall@k needs a denominator — how many
relevant passages exist *at all*. Guessing it (say, assuming every case has
exactly one) would make the number meaningless, so the runner scans the
project's indexed chunks with the case's own relevance rule and uses the true
count. A case with no relevant passage in the corpus is marked unsupported and
excluded from the aggregates instead of being scored as a zero the retriever
never had a chance to earn.

**RAGAS.** Faithfulness and answer relevancy need an LLM judge and the
optional ``ragas`` dependency. When it is not installed the report says so and
still returns every retrieval metric — the dashboard degrades to what can
honestly be measured rather than showing nothing or, worse, a placeholder
number.
"""

from __future__ import annotations

import importlib.util
from dataclasses import asdict, dataclass, field
from typing import Callable, Sequence

from .golden_set import GoldenSet, TestCase
from .metrics import aggregate, evaluate_ranking
from .ragas_runner import METRIC_NAMES as RAGAS_METRICS
from .ragas_runner import (
    AnswerQualityReport,
    build_samples,
    score_samples,
    unavailable_report,
)

RetrieveFn = Callable[[str, int], Sequence[dict]]
CorpusFn = Callable[[], Sequence[dict]]
AnswerFn = Callable[[str], tuple[str, list[str]]]


def ragas_available() -> bool:
    """Is the optional RAGAS dependency importable in this environment?"""
    return importlib.util.find_spec("ragas") is not None


@dataclass
class RetrievedItem:
    """One retrieved chunk, with the verdict that produced the metrics."""

    chunk_id: str
    document_name: str
    page: int | None
    score: float
    relevant: bool
    snippet: str


@dataclass
class CaseResult:
    """Per-question outcome — the row behind every aggregate number."""

    id: str
    question: str
    difficulty: str
    tags: list[str] = field(default_factory=list)
    policy: str = "term_match"
    supported: bool = True
    note: str = ""
    relevant_in_corpus: int = 0
    retrieved: list[RetrievedItem] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "retrieved": [asdict(item) for item in self.retrieved],
        }


@dataclass
class EvalReport:
    """Everything the Evaluation dashboard renders."""

    k: int = 5
    cases: list[CaseResult] = field(default_factory=list)
    aggregates: dict = field(default_factory=dict)
    ragas: dict = field(default_factory=dict)
    corpus_chunks: int = 0
    golden_set: dict = field(default_factory=dict)

    @property
    def supported_cases(self) -> list[CaseResult]:
        return [case for case in self.cases if case.supported]

    def to_dict(self) -> dict:
        return {
            "k": self.k,
            "corpus_chunks": self.corpus_chunks,
            "golden_set": self.golden_set,
            "aggregates": self.aggregates,
            "ragas": self.ragas,
            "cases": [case.to_dict() for case in self.cases],
            "cases_total": len(self.cases),
            "cases_evaluated": len(self.supported_cases),
            "cases_unsupported": len(self.cases) - len(self.supported_cases),
        }


class RetrievalEvaluator:
    """Run the golden set through a retriever and score the rankings.

    Args:
        retrieve_fn: ``(question, k) -> [chunk dicts]``, ranked best-first.
            Each chunk needs ``chunk_id`` and ``text``; ``document_name``,
            ``page`` and ``score`` are used for display when present.
        corpus_fn: ``() -> [chunk dicts]`` — every chunk the project has
            indexed, used to count how many relevant passages exist.
        golden_set: Defaults to the curated set shipped with MAIROS.
        k: Cut-off for Recall@k / Precision@k / nDCG@k.
    """

    def __init__(
        self,
        retrieve_fn: RetrieveFn,
        corpus_fn: CorpusFn,
        golden_set: GoldenSet | None = None,
        k: int = 5,
        answer_fn: AnswerFn | None = None,
        judge_embeddings=None,
    ):
        self.retrieve_fn = retrieve_fn
        self.corpus_fn = corpus_fn
        self.golden_set = golden_set or GoldenSet()
        self.k = max(1, int(k))
        # Supplying answer_fn opts into RAGAS answer-quality scoring; without
        # it (or without ragas and a live model) the report says so and shows
        # no number, which is the default.
        self.answer_fn = answer_fn
        # ``texts -> vectors`` for RAGAS; the vector store's embedder is reused
        # so the model is not loaded twice.
        self.judge_embeddings = judge_embeddings

    # ------------------------------------------------------------------
    def _relevant_ids(self, case: TestCase, corpus: Sequence[dict]) -> set[str]:
        return {
            str(chunk.get("chunk_id"))
            for chunk in corpus
            if chunk.get("chunk_id") and case.is_relevant(chunk)
        }

    def _score_case(self, case: TestCase, corpus: Sequence[dict]) -> CaseResult:
        relevant_ids = self._relevant_ids(case, corpus)
        retrieved = list(self.retrieve_fn(case.question, self.k) or [])
        ranked_ids = [str(chunk.get("chunk_id", "")) for chunk in retrieved]

        items = [
            RetrievedItem(
                chunk_id=str(chunk.get("chunk_id", "")),
                document_name=str(chunk.get("document_name", "")),
                page=chunk.get("page"),
                score=float(chunk.get("score") or 0.0),
                relevant=str(chunk.get("chunk_id", "")) in relevant_ids,
                snippet=" ".join(str(chunk.get("text", "")).split())[:240],
            )
            for chunk in retrieved
        ]

        result = CaseResult(
            id=case.id,
            question=case.question,
            difficulty=case.difficulty,
            tags=list(case.tags),
            policy=case.policy,
            relevant_in_corpus=len(relevant_ids),
            retrieved=items,
        )

        if not relevant_ids:
            result.supported = False
            result.note = (
                "No passage in this project satisfies the case's relevance rule, "
                "so the retriever could not have found one. Excluded from the "
                "aggregates."
            )
            return result

        result.metrics = evaluate_ranking(ranked_ids, relevant_ids, self.k)
        return result

    # ------------------------------------------------------------------
    def _answer_quality(self) -> AnswerQualityReport:
        """Model-judged scores, when both RAGAS and a live model are present."""
        if self.answer_fn is None:
            report = unavailable_report()
            if report.available:
                # Everything is installed, the caller just did not opt in.
                report.available = False
                report.reason = "no_answer_function"
                report.note = (
                    "RAGAS and a live model are available, but this run was started "
                    "without answer generation, so there are no answers to judge."
                )
            return report

        report = unavailable_report()
        if not report.available:
            return report

        return score_samples(
            build_samples(list(self.golden_set), self.answer_fn),
            embeddings=self.judge_embeddings,
        )

    # ------------------------------------------------------------------
    def run(self) -> EvalReport:
        """Score every case and aggregate the supported ones."""
        corpus = list(self.corpus_fn() or [])

        cases = [self._score_case(case, corpus) for case in self.golden_set]
        supported = [case.metrics for case in cases if case.supported]

        answer_quality = self._answer_quality()
        return EvalReport(
            k=self.k,
            cases=cases,
            corpus_chunks=len(corpus),
            aggregates=aggregate(supported, self.k),
            golden_set={
                "size": len(self.golden_set),
                "path": str(self.golden_set.path),
                **{
                    key: self.golden_set.metadata.get(key)
                    for key in ("name", "version", "relevance_policy", "notes")
                    if self.golden_set.metadata.get(key) is not None
                },
            },
            ragas=answer_quality.to_dict(),
        )


__all__ = [
    "CaseResult",
    "EvalReport",
    "RAGAS_METRICS",
    "RetrievalEvaluator",
    "RetrievedItem",
    "ragas_available",
]
