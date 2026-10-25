"""Standalone embedding helper.

ChromaDB embeds documents internally during ``add``/``query``, so the
ingestion path does not use this class. It exists for evaluation scripts and
ablation experiments that need vectors directly.
"""

from __future__ import annotations


class Embedder:
    """Generate dense embeddings with sentence-transformers.

    Args:
        model_name: HuggingFace model identifier.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        """Lazy-load the model (first call downloads ~90 MB)."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""
        if not texts:
            return []
        return [e.tolist() for e in self.model.encode(texts, show_progress_bar=False)]

    def embed_single(self, text: str) -> list[float]:
        """Embed one string."""
        return self.embed([text])[0]

    @property
    def dimension(self) -> int:
        """Embedding dimensionality."""
        return self.model.get_sentence_embedding_dimension()
