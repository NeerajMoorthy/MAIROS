"""End-to-end ingestion: PDF → pages → chunks → ChromaDB."""

from __future__ import annotations

import uuid
from pathlib import Path

from .chunker import RecursiveChunker, TextChunk
from .extractor import PDFExtractor


class IngestionPipeline:
    """Extract, chunk, and index a PDF.

    Page numbers survive the whole way through, which is what makes the
    ``[paper.pdf, p. 4]`` citations in generated answers verifiable.

    Args:
        chunk_size: Target characters per chunk.
        chunk_overlap: Characters shared between neighbouring chunks.
        chroma_store: Vector store to index into (``None`` for a dry run).
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        chroma_store=None,
    ):
        self.extractor = PDFExtractor()
        self.chunker = RecursiveChunker(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        self.chroma_store = chroma_store

    def ingest(
        self,
        pdf_path: str | Path,
        project_id: str,
        document_name: str | None = None,
    ) -> dict:
        """Run the full pipeline on one PDF.

        Returns:
            Summary with ``document_id``, ``title``, ``num_pages``,
            ``num_chunks``, and ``num_indexed``.
        """
        pdf_path = Path(pdf_path)
        document_id = str(uuid.uuid4())
        doc_name = document_name or pdf_path.name

        # 1. Extract, preserving page numbers.
        pages = self.extractor.extract(pdf_path)
        title = self.extractor.guess_title(pages, fallback=doc_name)

        # 2. Chunk each page.
        all_chunks: list[TextChunk] = []
        for page in pages:
            if not page.text:
                continue
            all_chunks.extend(
                self.chunker.chunk(
                    page.text,
                    page=page.page_number,
                    document_id=document_id,
                    document_name=doc_name,
                )
            )

        # Re-index globally so IDs stay unique across pages.
        for global_idx, chunk in enumerate(all_chunks):
            chunk.index = global_idx

        # 3. Embed and index.
        num_indexed = 0
        if self.chroma_store and all_chunks:
            num_indexed = self.chroma_store.add_chunks(
                ids=[f"{document_id}_{c.index}" for c in all_chunks],
                documents=[c.text for c in all_chunks],
                metadatas=[
                    {
                        "document_id": document_id,
                        "document_name": doc_name,
                        "title": title,
                        "project_id": project_id,
                        "page": c.page if c.page is not None else -1,
                        "chunk_index": c.index,
                        "source": "upload",
                    }
                    for c in all_chunks
                ],
            )

        return {
            "document_id": document_id,
            "filename": pdf_path.name,
            "document_name": doc_name,
            "title": title,
            "project_id": project_id,
            "num_pages": len(pages),
            "num_chunks": len(all_chunks),
            "num_indexed": num_indexed,
        }
