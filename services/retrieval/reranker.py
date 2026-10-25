"""Cross-encoder re-ranking for improved retrieval precision.

Off by default at mid-review — it adds a second model download and ~200ms per
query. Enable by passing an instance to ``HybridRetriever(reranker=...)``.
"""

from __future__ import annotations

from .vector_store import RetrievedChunk


class CrossEncoderReranker:
    """Re-rank retrieved chunks with a cross-encoder.

    Args:
        model_name: HuggingFace cross-encoder identifier.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Re-score *chunks* against *query* and return the best ones."""
        if not chunks:
            return []

        try:
            scores = self.model.predict([(query, c.text) for c in chunks])
        except Exception as exc:  # never let re-ranking break a query
            print(f"[reranker] disabled for this query: {exc}")
            return chunks[:top_k] if top_k else chunks

        for chunk, score in zip(chunks, scores):
            chunk.score = float(score)

        ranked = sorted(chunks, key=lambda c: c.score, reverse=True)
        return ranked[:top_k] if top_k else ranked
