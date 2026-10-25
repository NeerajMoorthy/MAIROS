"""Tests for PDF text extraction."""

from pathlib import Path

import pytest

from ingestion.extractor import PDFExtractor, UnreadablePDFError


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


class TestUnreadableFiles:
    """Regression (walkthrough K2): a text file renamed to .pdf gave a bare 500.

    MuPDF kept the file open after rejecting it, so on Windows the upload route
    could not delete it while handling the error. That failure replaced the
    real one, the file stayed behind, and deleting the project failed too.
    """

    def test_a_rejected_file_can_be_deleted_while_the_error_is_in_hand(self, tmp_path: Path):
        path = tmp_path / "notes.pdf"
        path.write_bytes(b"This is a plain text file renamed to .pdf.")

        try:
            PDFExtractor().extract(path)
        except Exception as exc:  # noqa: BLE001 - the type is asserted below
            path.unlink()  # what the upload route does, with the error still alive
            error = exc

        assert isinstance(error, UnreadablePDFError)
        assert "not a readable PDF" in str(error)
        assert not path.exists()

    @pytest.mark.parametrize("data", [b"", b"%PDF-1.7\n1 0 obj\n<<"], ids=["empty", "truncated"])
    def test_empty_and_damaged_files_are_unreadable(self, tmp_path: Path, data: bytes):
        path = tmp_path / "damaged.pdf"
        path.write_bytes(data)

        with pytest.raises(UnreadablePDFError):
            PDFExtractor().extract(path)

    def test_a_password_protected_pdf_says_so(self, tmp_path: Path):
        import fitz  # PyMuPDF

        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "Results that need a password.")
        path = tmp_path / "locked.pdf"
        path.write_bytes(doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o"))
        doc.close()

        with pytest.raises(UnreadablePDFError, match="password-protected"):
            PDFExtractor().extract(path)


class TestLigatures:
    def test_ligatures_are_expanded_into_plain_letters(self, tmp_path: Path):
        """Regression (walkthrough K4): text kept PyMuPDF's ligature characters,
        so "flagged" was stored as "\ufb02agged" and a search for the word, or a
        tester's question, could not match it. Many real papers are set with
        ligatures; the shaping layout engine used here produces them too."""
        import io

        import fitz  # PyMuPDF

        buffer = io.BytesIO()
        writer = fitz.DocumentWriter(buffer)
        story = fitz.Story(
            html="<p>The system flagged five defects in the first official field test, offline.</p>",
            user_css="* { font-family: sans-serif; }",
        )
        device = writer.begin_page(fitz.paper_rect("a4"))
        story.place(fitz.paper_rect("a4") + (50, 50, -50, -50))
        story.draw(device)
        writer.end_page()
        writer.close()
        path = tmp_path / "ligatures.pdf"
        path.write_bytes(buffer.getvalue())

        text = " ".join(PDFExtractor().extract_text(path).split())

        assert "flagged" in text and "first official field" in text and "offline" in text
        assert not any(ligature in text for ligature in "ﬀﬁﬂﬃﬄ")
