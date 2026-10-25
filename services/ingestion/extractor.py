"""PDF text extraction using PyMuPDF."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExtractedPage:
    """Text content of a single PDF page."""

    page_number: int
    text: str
    metadata: dict = field(default_factory=dict)


class UnreadablePDFError(ValueError):
    """The file cannot be read as a PDF. The message is written for the user."""


NOT_A_PDF = "This file is not a readable PDF. It may be damaged, or another kind of file renamed to .pdf."
PASSWORD_PROTECTED = (
    "This PDF is password-protected, so its text cannot be read. "
    "Remove the password and upload it again."
)


class PDFExtractor:
    """Extract text and a best-effort title from PDF files."""

    def extract(self, pdf_path: str | Path) -> list[ExtractedPage]:
        """Return one ``ExtractedPage`` per page, in order.

        Raises :class:`UnreadablePDFError` for a file that is not a PDF, is
        damaged, or is password-protected.
        """
        import fitz  # PyMuPDF

        pdf_path = Path(pdf_path)
        pages: list[ExtractedPage] = []

        # Opened from memory, never from the path. MuPDF keeps the handle of a
        # file it rejected for as long as the exception is alive, so on Windows
        # the upload route could not delete the file while handling the error:
        # that failure replaced the real one, and the file stayed locked.
        try:
            doc = fitz.open(stream=pdf_path.read_bytes(), filetype="pdf")
        except fitz.FileDataError as exc:
            raise UnreadablePDFError(NOT_A_PDF) from exc

        # PyMuPDF's default keeps typographic ligatures as single characters,
        # so "flagged" set with an fl-ligature came out as "ﬂagged" and no
        # search for the word could match it. These flags expand them.
        flags = fitz.TEXTFLAGS_TEXT & ~fitz.TEXT_PRESERVE_LIGATURES

        with doc:
            if doc.needs_pass:
                raise UnreadablePDFError(PASSWORD_PROTECTED)
            for page_num, page in enumerate(doc, start=1):
                text = page.get_text("text", flags=flags).strip()
                pages.append(
                    ExtractedPage(
                        page_number=page_num,
                        text=text,
                        metadata={
                            "source": pdf_path.name,
                            "char_count": len(text),
                            "word_count": len(text.split()) if text else 0,
                        },
                    )
                )

        return pages

    def extract_text(self, pdf_path: str | Path) -> str:
        """Full document text as one string."""
        return "\n\n".join(p.text for p in self.extract(pdf_path) if p.text)

    # ------------------------------------------------------------------
    def guess_title(self, pages: list[ExtractedPage], fallback: str = "") -> str:
        """Heuristic paper title: the first substantial line on page one.

        PDF metadata titles are unreliable (often the LaTeX filename), so this
        reads the rendered text instead.
        """
        if not pages or not pages[0].text:
            return fallback

        skip = re.compile(
            r"^(arxiv|doi|http|www|abstract|preprint|submitted|published|"
            r"proceedings|conference|copyright|\d+\s*$)",
            re.IGNORECASE,
        )

        for line in pages[0].text.splitlines()[:25]:
            candidate = " ".join(line.split())
            if 15 < len(candidate) < 200 and not skip.match(candidate):
                if sum(c.isalpha() for c in candidate) / len(candidate) > 0.6:
                    return candidate

        return fallback
