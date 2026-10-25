"""Tests for PDF extraction, chunking, and the ingestion → retrieval pipeline."""

from __future__ import annotations

from pathlib import Path

from services.ingestion.chunker import RecursiveChunker
from services.ingestion.extractor import PDFExtractor
from services.ingestion.pipeline import IngestionPipeline
from services.retrieval.vector_store import ChromaStore


class TestChunker:
    def test_short_text_is_one_chunk(self):
        chunks = RecursiveChunker(chunk_size=500, chunk_overlap=50).chunk(
            "Hello world, this is a test."
        )
        assert len(chunks) == 1
        assert "Hello world" in chunks[0].text

    def test_long_text_splits(self):
        chunks = RecursiveChunker(chunk_size=100, chunk_overlap=20).chunk("Word " * 200)
        assert len(chunks) > 1

    def test_consecutive_chunks_overlap(self):
        text = "Sentence one. Sentence two. Sentence three. Sentence four. " * 10
        chunks = RecursiveChunker(chunk_size=80, chunk_overlap=20).chunk(text)

        assert len(chunks) >= 2
        tail = chunks[0].text[-20:]
        assert any(tail[i:] in chunks[1].text for i in range(len(tail)))

    def test_page_and_document_metadata_survive(self):
        chunks = RecursiveChunker(chunk_size=500).chunk(
            "Some text", page=3, document_id="doc-1", document_name="paper.pdf"
        )
        assert chunks[0].page == 3
        assert chunks[0].document_id == "doc-1"
        assert chunks[0].document_name == "paper.pdf"

    def test_empty_text_yields_nothing(self):
        chunker = RecursiveChunker()
        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []

    def test_indices_are_sequential(self):
        chunks = RecursiveChunker(chunk_size=100, chunk_overlap=10).chunk("Word " * 200)
        assert [c.index for c in chunks] == list(range(len(chunks)))

    def test_overlap_is_clamped_below_chunk_size(self):
        """An overlap >= chunk_size would loop forever without the clamp."""
        chunker = RecursiveChunker(chunk_size=100, chunk_overlap=500)
        assert chunker.chunk_overlap < chunker.chunk_size
        assert chunker.chunk("Word " * 200)


class TestExtractor:
    def test_extracts_every_page(self, sample_pdf: Path):
        pages = PDFExtractor().extract(sample_pdf)
        assert len(pages) == 2
        assert [p.page_number for p in pages] == [1, 2]

    def test_page_text_content(self, sample_pdf: Path):
        pages = PDFExtractor().extract(sample_pdf)
        assert "transformer" in pages[0].text.lower()
        assert "retrieval" in pages[1].text.lower()

    def test_metadata_populated(self, sample_pdf: Path):
        for page in PDFExtractor().extract(sample_pdf):
            assert page.metadata["source"] == "test_paper.pdf"
            assert page.metadata["char_count"] > 0

    def test_full_text_join(self, sample_pdf: Path):
        text = PDFExtractor().extract_text(sample_pdf)
        assert "transformer" in text.lower() and "retrieval" in text.lower()

    def test_title_guess_uses_first_real_line(self, sample_pdf: Path):
        extractor = PDFExtractor()
        title = extractor.guess_title(extractor.extract(sample_pdf), fallback="fallback.pdf")
        assert "Transformers" in title


class TestPipeline:
    def _pipeline(self, store: ChromaStore) -> IngestionPipeline:
        return IngestionPipeline(chunk_size=200, chunk_overlap=30, chroma_store=store)

    def test_ingest_indexes_all_chunks(self, sample_pdf: Path, chroma_store: ChromaStore):
        result = self._pipeline(chroma_store).ingest(
            pdf_path=sample_pdf, project_id="proj-1", document_name="test_paper.pdf"
        )

        assert result["num_pages"] == 2
        assert result["num_chunks"] > 0
        assert result["num_indexed"] == result["num_chunks"]
        assert chroma_store.count() == result["num_chunks"]
        assert result["title"]

    def test_query_finds_relevant_chunks(self, sample_pdf: Path, chroma_store: ChromaStore):
        self._pipeline(chroma_store).ingest(
            pdf_path=sample_pdf, project_id="proj-1", document_name="test_paper.pdf"
        )

        results = chroma_store.query("self-attention transformers parallel", top_k=3)
        assert results
        assert any("attention" in r.text.lower() for r in results)

    def test_results_carry_document_and_page(self, sample_pdf: Path, chroma_store: ChromaStore):
        self._pipeline(chroma_store).ingest(
            pdf_path=sample_pdf, project_id="proj-1", document_name="test_paper.pdf"
        )

        for result in chroma_store.query("retrieval augmented generation", top_k=5):
            assert result.document_name == "test_paper.pdf"
            assert result.page is not None and result.page >= 1
            assert result.chunk_id

    def test_project_filter_isolates_results(self, sample_pdf: Path, chroma_store: ChromaStore):
        pipeline = self._pipeline(chroma_store)
        pipeline.ingest(pdf_path=sample_pdf, project_id="proj-A", document_name="paper_a.pdf")
        pipeline.ingest(pdf_path=sample_pdf, project_id="proj-B", document_name="paper_b.pdf")

        results_a = chroma_store.query("attention", top_k=5, where={"project_id": "proj-A"})
        results_b = chroma_store.query("attention", top_k=5, where={"project_id": "proj-B"})

        assert results_a and results_b
        assert all(r.document_name == "paper_a.pdf" for r in results_a)
        assert all(r.document_name == "paper_b.pdf" for r in results_b)

    def test_get_document_text_returns_ordered_chunks(
        self, sample_pdf: Path, chroma_store: ChromaStore
    ):
        result = self._pipeline(chroma_store).ingest(
            pdf_path=sample_pdf, project_id="proj-1", document_name="test_paper.pdf"
        )

        rows = chroma_store.get_document_text(result["document_id"])
        assert len(rows) == result["num_chunks"]
        assert [r["chunk_index"] for r in rows] == sorted(r["chunk_index"] for r in rows)

    def test_dry_run_without_store(self, sample_pdf: Path):
        result = IngestionPipeline(chunk_size=200, chunk_overlap=30).ingest(
            pdf_path=sample_pdf, project_id="proj-dry"
        )
        assert result["num_chunks"] > 0
        assert result["num_indexed"] == 0
