"""Tests for PDF text extraction."""

from pathlib import Path

from ingestion.extractor import PDFExtractor


class TestPDFExtractor:
    """Verify PyMuPDF extraction returns correct pages and metadata."""

    def test_extract_returns_two_pages(self, sample_pdf: Path):
        extractor = PDFExtractor()
        pages = extractor.extract(sample_pdf)

        assert len(pages) == 2
        assert pages[0].page_number == 1
        assert pages[1].page_number == 2

    def test_page_text_contains_expected_content(self, sample_pdf: Path):
        extractor = PDFExtractor()
        pages = extractor.extract(sample_pdf)

        assert "transformer" in pages[0].text.lower()
        assert "attention" in pages[0].text.lower()
        assert "retrieval" in pages[1].text.lower()

    def test_page_metadata_populated(self, sample_pdf: Path):
        extractor = PDFExtractor()
        pages = extractor.extract(sample_pdf)

        for page in pages:
            assert page.metadata["source"] == "test_paper.pdf"
            assert page.metadata["char_count"] > 0
            assert page.metadata["word_count"] > 0

    def test_extract_text_returns_combined_string(self, sample_pdf: Path):
        extractor = PDFExtractor()
        full_text = extractor.extract_text(sample_pdf)

        assert isinstance(full_text, str)
        assert "transformer" in full_text.lower()
        assert "retrieval" in full_text.lower()
