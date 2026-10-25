"""Integration tests for the ingestion pipeline + ChromaDB retrieval."""

from pathlib import Path

from ingestion.pipeline import IngestionPipeline
from retrieval.vector_store import ChromaStore


class TestIngestionPipeline:
    """End-to-end: PDF → chunk → ChromaDB → query."""

    def test_ingest_creates_chunks_in_chroma(
        self, sample_pdf: Path, chroma_store: ChromaStore
    ):
        pipeline = IngestionPipeline(
            chunk_size=200,
            chunk_overlap=30,
            chroma_store=chroma_store,
        )

        result = pipeline.ingest(
            pdf_path=sample_pdf,
            project_id="proj-1",
            document_name="test_paper.pdf",
        )

        assert result["num_pages"] == 2
        assert result["num_chunks"] > 0
        assert result["num_indexed"] == result["num_chunks"]
        assert chroma_store.count() == result["num_chunks"]

    def test_query_returns_relevant_chunks(
        self, sample_pdf: Path, chroma_store: ChromaStore
    ):
        pipeline = IngestionPipeline(
            chunk_size=200,
            chunk_overlap=30,
            chroma_store=chroma_store,
        )
        pipeline.ingest(
            pdf_path=sample_pdf,
            project_id="proj-1",
            document_name="test_paper.pdf",
        )

        # Query for transformer content
        results = chroma_store.query("What is self-attention?", top_k=3)

        assert len(results) > 0
        assert any("attention" in r.text.lower() for r in results)

    def test_query_includes_document_name_and_page(
        self, sample_pdf: Path, chroma_store: ChromaStore
    ):
        pipeline = IngestionPipeline(
            chunk_size=200,
            chunk_overlap=30,
            chroma_store=chroma_store,
        )
        pipeline.ingest(
            pdf_path=sample_pdf,
            project_id="proj-1",
            document_name="test_paper.pdf",
        )

        results = chroma_store.query("retrieval augmented generation", top_k=5)

        for r in results:
            assert r.document_name == "test_paper.pdf"
            assert r.page is not None
            assert r.page >= 1
            assert r.chunk_id  # not empty

    def test_project_filter_isolates_results(
        self, sample_pdf: Path, chroma_store: ChromaStore
    ):
        pipeline = IngestionPipeline(
            chunk_size=200,
            chunk_overlap=30,
            chroma_store=chroma_store,
        )

        # Ingest into two different projects
        pipeline.ingest(
            pdf_path=sample_pdf,
            project_id="proj-A",
            document_name="paper_a.pdf",
        )
        pipeline.ingest(
            pdf_path=sample_pdf,
            project_id="proj-B",
            document_name="paper_b.pdf",
        )

        results_a = chroma_store.query(
            "attention", top_k=5, where={"project_id": "proj-A"}
        )
        results_b = chroma_store.query(
            "attention", top_k=5, where={"project_id": "proj-B"}
        )

        for r in results_a:
            assert r.document_name == "paper_a.pdf"
        for r in results_b:
            assert r.document_name == "paper_b.pdf"

    def test_ingest_without_chroma_still_returns_summary(
        self, sample_pdf: Path
    ):
        """Pipeline works even without a ChromaStore (dry run)."""
        pipeline = IngestionPipeline(chunk_size=200, chunk_overlap=30)
        result = pipeline.ingest(
            pdf_path=sample_pdf,
            project_id="proj-dry",
        )

        assert result["num_pages"] == 2
        assert result["num_chunks"] > 0
        assert result["num_indexed"] == 0
