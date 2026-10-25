"""Retrieval quality metrics — pure functions, no LLM, no network.

These are the metrics the Evaluation dashboard reports. They are deliberately
dependency-free so they can be unit-tested against hand-worked examples: a
metric you cannot verify by hand is a metric you cannot defend in a review.

Relevance is binary throughout (a chunk either answers the question or it does
not). Definitions follow the standard IR formulations:

* **Recall@k**    ``|relevant ∩ top-k| / |relevant|``
* **Precision@k** ``|relevant ∩ top-k| / k`` — divided by *k*, not by the number
  actually returned, so returning fewer than *k* results is penalised.
* **RR**          ``1 / rank`` of the first relevant hit (0 when there is none);
  MRR is the mean of RR over the evaluated cases.
* **nDCG@k**      ``DCG@k / IDCG@k`` with binary gains and ``log2(i + 1)``
  discounting, where the ideal ranking puts ``min(|relevant|, k)`` relevant
  items first.
"""

from __future__ import annotations

from math import log2
from typing import Iterable, Sequence


def _top_k(ranked_ids: Sequence[str], k: int) -> list[str]:
    if k <= 0:
        return []
    return list(ranked_ids[:k])


def hits_at_k(ranked_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> int:
    """Number of relevant items inside the top *k*."""
    relevant = set(relevant_ids)
    return sum(1 for cid in _top_k(ranked_ids, k) if cid in relevant)


def recall_at_k(ranked_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> float:
    """Fraction of all relevant items that appear in the top *k*."""
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    return hits_at_k(ranked_ids, relevant, k) / len(relevant)


def precision_at_k(ranked_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> float:
    """Fraction of the top *k* slots filled by a relevant item."""
    if k <= 0:
        return 0.0
    return hits_at_k(ranked_ids, relevant_ids, k) / k


def reciprocal_rank(ranked_ids: Sequence[str], relevant_ids: Iterable[str]) -> float:
    """``1 / rank`` of the first relevant hit; 0.0 when none is retrieved."""
    relevant = set(relevant_ids)
    for index, chunk_id in enumerate(ranked_ids, start=1):
        if chunk_id in relevant:
            return 1.0 / index
    return 0.0


def dcg_at_k(ranked_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> float:
    """Discounted cumulative gain with binary relevance."""
    relevant = set(relevant_ids)
    return sum(
        1.0 / log2(index + 1)
        for index, chunk_id in enumerate(_top_k(ranked_ids, k), start=1)
        if chunk_id in relevant
    )


def ideal_dcg_at_k(relevant_count: int, k: int) -> float:
    """DCG of the best possible ranking for *relevant_count* relevant items."""
    return sum(1.0 / log2(index + 1) for index in range(1, min(relevant_count, k) + 1))


def ndcg_at_k(ranked_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> float:
    """Normalised DCG — 1.0 when every relevant item is ranked first."""
    relevant = set(relevant_ids)
    ideal = ideal_dcg_at_k(len(relevant), k)
    if ideal <= 0:
        return 0.0
    return dcg_at_k(ranked_ids, relevant, k) / ideal


def evaluate_ranking(
    ranked_ids: Sequence[str], relevant_ids: Iterable[str], k: int = 5
) -> dict[str, float]:
    """All four metrics for a single ranked result list."""
    relevant = set(relevant_ids)
    return {
        f"recall_at_{k}": round(recall_at_k(ranked_ids, relevant, k), 4),
        f"precision_at_{k}": round(precision_at_k(ranked_ids, relevant, k), 4),
        "reciprocal_rank": round(reciprocal_rank(ranked_ids, relevant), 4),
        f"ndcg_at_{k}": round(ndcg_at_k(ranked_ids, relevant, k), 4),
    }


def aggregate(per_case: Sequence[dict[str, float]], k: int = 5) -> dict[str, float]:
    """Mean of each metric across cases; MRR is the mean reciprocal rank.

    An empty input returns zeros rather than raising, so a project with no
    evaluable cases still renders a dashboard instead of an error.
    """
    if not per_case:
        return {
            f"recall_at_{k}": 0.0,
            f"precision_at_{k}": 0.0,
            "mrr": 0.0,
            f"ndcg_at_{k}": 0.0,
            "cases_evaluated": 0,
        }

    def mean(key: str) -> float:
        return round(sum(case.get(key, 0.0) for case in per_case) / len(per_case), 4)

    return {
        f"recall_at_{k}": mean(f"recall_at_{k}"),
        f"precision_at_{k}": mean(f"precision_at_{k}"),
        "mrr": mean("reciprocal_rank"),
        f"ndcg_at_{k}": mean(f"ndcg_at_{k}"),
        "cases_evaluated": len(per_case),
    }


__all__ = [
    "aggregate",
    "dcg_at_k",
    "evaluate_ranking",
    "hits_at_k",
    "ideal_dcg_at_k",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
]
