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


class PDFExtractor:
    """Extract text and a best-effort title from PDF files."""

    def extract(self, pdf_path: str | Path) -> list[ExtractedPage]:
        """Return one ``ExtractedPage`` per page, in order."""
        import fitz  # PyMuPDF

        pdf_path = Path(pdf_path)
        pages: list[ExtractedPage] = []

        with fitz.open(pdf_path) as doc:
            for page_num, page in enumerate(doc, start=1):
                text = page.get_text("text").strip()
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
