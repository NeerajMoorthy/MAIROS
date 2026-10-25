"""arXiv response parsing, tested offline against a canned API response."""

from __future__ import annotations

import pytest

from services.agents.base import AgentContext
from services.agents.indexer import IndexerAgent
from services.agents.literature import LiteratureAgent

# Trimmed but structurally faithful arXiv Atom response.
ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2005.11401v4</id>
    <published>2020-05-22T21:34:47Z</published>
    <title>Retrieval-Augmented Generation for
  Knowledge-Intensive NLP Tasks</title>
    <summary>  Large pre-trained language models store factual knowledge in their
parameters. We explore a general-purpose fine-tuning recipe.
</summary>
    <author><name>Patrick Lewis</name></author>
    <author><name>Ethan Perez</name></author>
    <link href="http://arxiv.org/abs/2005.11401v4" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2005.11401v4" rel="related" type="application/pdf"/>
    <arxiv:primary_category term="cs.CL"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All You Need</title>
    <summary>  The dominant sequence transduction models are based on complex
recurrent or convolutional neural networks.
</summary>
    <author><name>Ashish Vaswani</name></author>
    <link href="http://arxiv.org/abs/1706.03762v7" rel="alternate" type="text/html"/>
    <arxiv:primary_category term="cs.CL"/>
  </entry>
</feed>
"""


class _FakeResponse:
    text = ARXIV_XML

    def raise_for_status(self) -> None:
        return None


class _UnavailableResponse:
    """What the other sources answer while only arXiv is stubbed."""

    status_code = 503
    text = ""

    def raise_for_status(self) -> None:
        import httpx

        request = httpx.Request("GET", "https://example.invalid")
        raise httpx.HTTPStatusError("503", request=request, response=httpx.Response(503, request=request))


class _FakeClient:
    """Stands in for httpx.AsyncClient as an async context manager.

    Answers arXiv with the canned feed and every other source with HTTP 503,
    so these tests exercise arXiv parsing and a partly unavailable search.
    """

    def __init__(self, *args, **kwargs):
        self.requested_url: str | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        if "arxiv.org" not in url:
            return _UnavailableResponse()
        self.requested_url = url
        _FakeClient.last_url = url
        return _FakeResponse()


@pytest.fixture()
def patched_arxiv(monkeypatch):
    import services.agents.literature as literature_module

    monkeypatch.setattr(literature_module.httpx, "AsyncClient", _FakeClient)
    return _FakeClient


class TestArxivParsing:
    @pytest.mark.asyncio
    async def test_parses_all_entries(self, patched_arxiv):
        papers = await LiteratureAgent(llm=None).fetch("retrieval augmented generation")
        assert len(papers) == 2

    @pytest.mark.asyncio
    async def test_multiline_title_is_normalised(self, patched_arxiv):
        papers = await LiteratureAgent(llm=None).fetch("rag")
        assert papers[0]["title"] == (
            "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"
        )

    @pytest.mark.asyncio
    async def test_fields_extracted(self, patched_arxiv):
        paper = (await LiteratureAgent(llm=None).fetch("rag"))[0]
        # Stored under its versionless arXiv id; the versioned one is kept.
        assert paper["id"] == "arxiv:2005.11401"
        assert paper["source_ids"]["arxiv"] == "2005.11401v4"
        assert paper["authors"] == ["Patrick Lewis", "Ethan Perez"]
        assert paper["year"] == "2020"
        assert paper["pdf_url"].endswith("2005.11401v4")
        assert paper["primary_category"] == "cs.CL"
        assert "fine-tuning recipe" in paper["abstract"]

    @pytest.mark.asyncio
    async def test_missing_pdf_link_is_not_fatal(self, patched_arxiv):
        papers = await LiteratureAgent(llm=None).fetch("attention")
        paper = next(p for p in papers if p["title"] == "Attention Is All You Need")
        assert paper["pdf_url"] == ""

    @pytest.mark.asyncio
    async def test_query_is_url_encoded(self, patched_arxiv):
        await LiteratureAgent(llm=None).fetch("graph neural networks")
        assert "search_query=" in _FakeClient.last_url
        assert " " not in _FakeClient.last_url

    @pytest.mark.asyncio
    async def test_run_populates_chunks_for_downstream_agents(self, patched_arxiv):
        ctx = await LiteratureAgent(llm=None).run(AgentContext(question="rag"))
        assert len(ctx.intermediate_results["retrieved_papers"]) == 2
        assert len(ctx.retrieved_chunks) == 2
        assert "Abstract:" in ctx.retrieved_chunks[0]["text"]


class TestIndexer:
    @pytest.mark.asyncio
    async def test_retrieved_papers_are_indexed(self, patched_arxiv, chroma_store):
        """Step 3 of the demo flow: fetched papers must become queryable."""
        ctx = AgentContext(question="rag", project_id="p1", chroma_store=chroma_store)
        ctx = await LiteratureAgent(llm=None).run(ctx)
        ctx = await IndexerAgent(llm=None).run(ctx)

        assert ctx.intermediate_results["indexed_chunks"] > 0
        assert chroma_store.count() > 0

        hits = chroma_store.query(
            "language models factual knowledge parameters",
            top_k=3,
            where={"project_id": "p1"},
        )
        assert hits
        assert any("Retrieval-Augmented" in h.document_name for h in hits)

    @pytest.mark.asyncio
    async def test_indexer_without_store_is_a_noop(self, patched_arxiv):
        ctx = await LiteratureAgent(llm=None).run(AgentContext(question="rag"))
        ctx = await IndexerAgent(llm=None).run(ctx)
        assert "indexed_chunks" not in ctx.intermediate_results
