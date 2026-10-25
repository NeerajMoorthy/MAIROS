"""Evaluation service — retrieval metrics, curated test cases, optional RAGAS."""

from .golden_set import GoldenSet, TestCase
from .metrics import aggregate, evaluate_ranking
from .runner import RAGAS_METRICS, EvalReport, RetrievalEvaluator, ragas_available

__all__ = [
    "EvalReport",
    "GoldenSet",
    "RAGAS_METRICS",
    "RetrievalEvaluator",
    "TestCase",
    "aggregate",
    "evaluate_ranking",
    "ragas_available",
]
