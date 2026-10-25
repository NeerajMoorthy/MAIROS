"""Tests for text chunking."""

from ingestion.chunker import RecursiveChunker


class TestRecursiveChunker:
    """Verify chunking produces correct output with overlap."""

    def test_short_text_single_chunk(self):
        chunker = RecursiveChunker(chunk_size=500, chunk_overlap=50)
        chunks = chunker.chunk("Hello world, this is a test.")

        assert len(chunks) == 1
        assert "Hello world" in chunks[0].text

    def test_long_text_produces_multiple_chunks(self):
        text = "Word " * 200  # ~1000 chars
        chunker = RecursiveChunker(chunk_size=100, chunk_overlap=20)
        chunks = chunker.chunk(text)

        assert len(chunks) > 1

    def test_overlap_exists_between_consecutive_chunks(self):
        text = "Sentence one. Sentence two. Sentence three. Sentence four. " * 10
        chunker = RecursiveChunker(chunk_size=80, chunk_overlap=20)
        chunks = chunker.chunk(text)

        if len(chunks) >= 2:
            # The end of chunk N should overlap with the start of chunk N+1
            tail = chunks[0].text[-20:]
            assert any(
                tail[i:] in chunks[1].text for i in range(len(tail))
            ), "Expected overlap between consecutive chunks"

    def test_page_number_preserved(self):
        chunker = RecursiveChunker(chunk_size=500)
        chunks = chunker.chunk("Some text", page=3)

        assert chunks[0].page == 3

    def test_document_fields_preserved(self):
        chunker = RecursiveChunker(chunk_size=500)
        chunks = chunker.chunk(
            "Some text",
            document_id="doc-1",
            document_name="paper.pdf",
        )

        assert chunks[0].document_id == "doc-1"
        assert chunks[0].document_name == "paper.pdf"

    def test_empty_text_returns_no_chunks(self):
        chunker = RecursiveChunker()
        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []

    def test_chunk_indices_are_sequential(self):
        text = "Word " * 200
        chunker = RecursiveChunker(chunk_size=100, chunk_overlap=10)
        chunks = chunker.chunk(text)

        indices = [c.index for c in chunks]
        assert indices == list(range(len(chunks)))
