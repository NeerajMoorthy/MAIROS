"""Text chunking strategies for document ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TextChunk:
    """A chunk of text with provenance metadata."""

    text: str
    index: int
    page: int | None = None
    document_id: str = ""
    document_name: str = ""
    metadata: dict = field(default_factory=dict)


class RecursiveChunker:
    """Recursive character-based splitter.

    Splits on paragraph boundaries first, then lines, sentences, and finally
    words — so a chunk boundary lands at the most semantically natural place
    available at the target size.

    Args:
        chunk_size: Target characters per chunk.
        chunk_overlap: Characters carried into the next chunk for continuity.
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = max(64, chunk_size)
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size // 2))
        self._separators = ["\n\n", "\n", ". ", " "]

    def chunk(
        self,
        text: str,
        page: int | None = None,
        document_id: str = "",
        document_name: str = "",
    ) -> list[TextChunk]:
        """Split *text* into overlapping chunks."""
        if not text or not text.strip():
            return []

        chunks: list[TextChunk] = []
        parts = self._split_recursive(text, self._separators)

        def flush(buffer: str) -> None:
            stripped = buffer.strip()
            if stripped:
                chunks.append(
                    TextChunk(
                        text=stripped,
                        index=len(chunks),
                        page=page,
                        document_id=document_id,
                        document_name=document_name,
                    )
                )

        current = ""
        for part in parts:
            if len(current) + len(part) > self.chunk_size and current:
                flush(current)
                current = current[-self.chunk_overlap :] + part
            else:
                current += part

        flush(current)
        return chunks

    # ------------------------------------------------------------------
    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        if not separators:
            return [text]

        sep = separators[0]
        result: list[str] = []
        for part in text.split(sep):
            if len(part) > self.chunk_size and len(separators) > 1:
                result.extend(self._split_recursive(part, separators[1:]))
            else:
                result.append(part + sep)
        return result


class SemanticChunker:
    """Embedding-based chunking (planned for the final review).

    Groups consecutive sentences whose embeddings stay above a similarity
    threshold. Currently delegates to :class:`RecursiveChunker` so it is safe
    to reference in ablation experiments today.
    """

    def __init__(self, similarity_threshold: float = 0.75):
        self.similarity_threshold = similarity_threshold

    def chunk(self, text: str, page: int | None = None, **kwargs) -> list[TextChunk]:
        return RecursiveChunker().chunk(text, page=page, **kwargs)
