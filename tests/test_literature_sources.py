"""Multi-source literature search: parsing, merging, queries and coverage.

Everything runs offline against recorded-shape responses
(``literature_fixtures.py``); nothing here contacts arXiv, OpenAlex or
Semantic Scholar.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

from literature_fixtures import OPENALEX_WORKS, SEMANTIC_SCHOLAR_SEARCH, use_recorded_sources
from services.agents.base import AgentContext
from services.agents.literature import LiteratureAgent
from services.literature.coverage import build_coverage, describe_scope
from services.literature.merge import merge_ranked
from services.literature.papers import (
    bare_arxiv_id,
    document_id_for,
    new_paper,
    normalise_doi,
    safe_link,
)
from services.literature.queries import parse_model_queries, plan_queries, rule_queries
from services.literature.sources import (
    ArxivSource,
    SourceRun,
    parse_openalex,
    parse_semantic_scholar,
)

RAG_TITLE = "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"


# ---------------------------------------------------------------------------
# Records and links
# ---------------------------------------------------------------------------
class TestPaperRecords:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("https://doi.org/10.1145/3292500.3330701", "10.1145/3292500.3330701"),
            ("doi:10.1145/ABC", "10.1145/abc"),
            ("10.18653/v1/2020.emnlp-main.550", "10.18653/v1/2020.emnlp-main.550"),
            ("not a doi", ""),
            (None, ""),
        ],
    )
    def test_dois_are_normalised(self, raw, expected):
        assert normalise_doi(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2005.11401v4", "2005.11401"),
            ("http://arxiv.org/abs/2005.11401v2", "2005.11401"),
            ("10.48550/arXiv.2005.11401", "2005.11401"),
        ],
    )
    def test_arxiv_ids_lose_their_version(self, raw, expected):
        assert bare_arxiv_id(raw) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "https://doi.org/10.1145/1",
            "https://arxiv.org/abs/2005.11401",
            "https://openalex.org/W1",
            "https://www.semanticscholar.org/paper/abc",
        ],
    )
    def test_scholarly_links_are_kept(self, url):
        assert safe_link(url) == url

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "https://some-publisher.example/paper.pdf",
            "https://doi.org.evil.example/10.1/x",
            "ftp://arxiv.org/abs/1",
            "http://127.0.0.1:8000/api",
        ],
    )
    def test_any_other_link_is_dropped(self, url):
        """Links stay allowlisted: a metadata record cannot smuggle one in."""
        assert safe_link(url) == ""

    def test_document_ids_keep_the_arxiv_form_earlier_builds_wrote(self):
        paper = new_paper("arxiv", "2005.11401v4", title="T")
        assert document_id_for(paper) == "arxiv_2005.11401v4"
        assert document_id_for(new_paper("openalex", "W1", title="T")) == "openalex_W1"
        assert document_id_for(new_paper("semantic_scholar", "abc", title="T")) == "s2_abc"
        # A record saved before source ids existed came from arXiv.
        assert document_id_for({"id": "1706.03762v7"}) == "arxiv_1706.03762v7"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
class TestParsing:
    def test_openalex_works_are_read_including_the_inverted_abstract(self):
        papers = parse_openalex(OPENALEX_WORKS)
        rag = papers[0]

        assert rag["id"] == "W3027879771"
        assert rag["title"] == RAG_TITLE
        assert rag["abstract"] == "Large pre-trained language models store factual knowledge."
        assert rag["authors"][:2] == ["Patrick Lewis", "Ethan Perez"]
        assert rag["year"] == "2020"
        assert rag["doi"] == "10.5555/3495724.3496517"
        assert rag["arxiv_id"] == "2005.11401"  # from the arXiv landing page
        assert rag["venue"] == "Neural Information Processing Systems"
        assert rag["citation_count"] == 4100
        assert rag["url"] == "https://doi.org/10.5555/3495724.3496517"
        # A publisher PDF host is not on the allowlist.
        assert rag["pdf_url"] == ""

    def test_semantic_scholar_results_are_read(self):
        papers = parse_semantic_scholar(SEMANTIC_SCHOLAR_SEARCH)
        assert [p["title"] for p in papers][-1].startswith("REALM")
        dpr = papers[1]
        assert dpr["doi"] == "10.18653/v1/2020.emnlp-main.550"
        assert dpr["arxiv_id"] == "2004.04906"
        assert dpr["citation_count"] == 3300
        assert dpr["url"].startswith("https://www.semanticscholar.org/paper/")

    def test_malformed_records_are_skipped_not_fatal(self):
        assert parse_openalex({"results": [None, {"id": ""}, {"display_name": "No id"}]}) == []
        assert parse_semantic_scholar({"data": ["x", {"paperId": "1"}]}) == []
        assert parse_openalex({}) == []

    def test_arxiv_sends_every_query_in_one_request(self):
        url = ArxivSource(per_query=5).url(["graph neural networks", "message passing"])
        expression = parse_qs(urlparse(url).query)["search_query"][0]
        assert expression == "(all:graph AND all:neural AND all:networks) OR (all:message AND all:passing)"
        assert parse_qs(urlparse(url).query)["max_results"] == ["10"]


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------
def _ranked() -> list[list[dict]]:
    from test_literature import ARXIV_XML

    from services.literature.sources import parse_arxiv

    return [
        parse_arxiv(ARXIV_XML),
        parse_openalex(OPENALEX_WORKS),
        parse_semantic_scholar(SEMANTIC_SCHOLAR_SEARCH),
    ]


class TestMerging:
    def test_one_paper_from_three_sources_is_one_record(self):
        merged, duplicates = merge_ranked(_ranked())
        titles = [p["title"] for p in merged]

        assert titles.count(RAG_TITLE) == 1
        assert len(merged) == 4  # RAG, DPR, Attention, REALM
        assert duplicates == 3  # RAG twice more, DPR once more

        rag = merged[0]
        assert rag["sources"] == ["arXiv", "OpenAlex", "Semantic Scholar"]
        assert set(rag["source_ids"]) == {"arxiv", "openalex", "semantic_scholar"}

    def test_the_merged_record_keeps_the_most_useful_metadata(self):
        rag = merge_ranked(_ranked())[0][0]
        # The published version's DOI, not arXiv's own.
        assert rag["doi"] == "10.5555/3495724.3496517"
        assert rag["url"] == "https://doi.org/10.5555/3495724.3496517"
        assert rag["citation_count"] == 4300
        assert rag["venue"] == "Neural Information Processing Systems"
        assert rag["pdf_url"].startswith("http://arxiv.org/pdf/")
        # The indexing id stays the arXiv one.
        assert document_id_for(rag) == "arxiv_2005.11401v4"

    def test_papers_several_sources_agree_on_rank_first(self):
        titles = [p["title"] for p in merge_ranked(_ranked())[0]]
        assert titles[0] == RAG_TITLE  # first in all three lists
        assert titles[1].startswith("Dense Passage Retrieval")  # second in two
        assert titles.index("Attention Is All You Need") < titles.index(
            "REALM: Retrieval-Augmented Language Model Pre-Training"
        )

    def test_the_topic_outranks_agreement_on_a_broad_query(self):
        """From a live search: a broad query ("low-cost robot") returned the same
        off-topic benchmark from two sources, and rank fusion alone put it
        above "Railway Track Crack Detection Vehicle"."""
        generic = [
            new_paper(s, f"{s}-robel", title="ROBEL: Robotics Benchmarks for Learning with Low-Cost Robots",
                      abstract="Benchmarks for learning on low-cost robots.", arxiv_id="1909.11639")
            for s in ("arxiv", "openalex")
        ]
        on_topic = new_paper(
            "openalex", "W2", title="Railway Track Crack Detection Vehicle",
            abstract="A vehicle that detects cracks in railway tracks with infrared sensors.",
        )
        lists = [[generic[0]], [generic[1], on_topic]]
        focus = "railway track crack detection robot using infrared sensors"

        unfocused = [p["title"] for p in merge_ranked(lists)[0]]
        focused = [p["title"] for p in merge_ranked(lists, focus=focus)[0]]
        assert unfocused[0].startswith("ROBEL")
        assert focused[0] == "Railway Track Crack Detection Vehicle"

    def test_short_identical_titles_are_not_merged(self):
        a = new_paper("openalex", "W1", title="Introduction")
        b = new_paper("semantic_scholar", "s1", title="Introduction")
        merged, duplicates = merge_ranked([[a], [b]])
        assert len(merged) == 2 and duplicates == 0

    def test_a_title_match_merges_records_without_shared_ids(self):
        a = new_paper("openalex", "W1", title="A Study of Retrieval for Long Scientific Documents")
        b = new_paper(
            "semantic_scholar", "s1", title="A study of retrieval for long scientific documents."
        )
        merged, duplicates = merge_ranked([[a], [b]])
        assert len(merged) == 1 and duplicates == 1


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
DESCRIPTION = (
    "We are building a low-cost robot that detects cracks in railway tracks. "
    "The robot uses a camera and infrared sensors to find rail cracks, and a "
    "GSM module sends an alert with the GPS location of each crack. Manual "
    "inspection of railway tracks is slow, so automatic crack detection on "
    "railway tracks would make inspection cheaper."
)


class TestQueries:
    def test_a_short_topic_is_one_query(self):
        assert rule_queries("What are recent papers on graph neural networks?") == [
            "graph neural networks"
        ]

    def test_a_long_description_gives_several_queries(self):
        queries = rule_queries(DESCRIPTION, 4)
        assert len(queries) == 4
        assert "railway tracks" in queries
        assert len(set(queries)) == len(queries)

    def test_long_text_queries_are_its_technical_phrases(self):
        assert rule_queries(DESCRIPTION, 4) == [
            "automatic crack detection",
            "railway tracks",
            "infrared sensors",
            "gsm module",
        ]

    def test_seeds_lead_and_the_model_still_adds_its_own(self):
        seeds = [
            {"text": "rail crack detection", "written_by": "model"},
            {"text": "track inspection robot", "written_by": "model"},
            {"text": "a third seed", "written_by": "model"},
        ]
        planned, _ = plan_queries(
            DESCRIPTION, 4, invoke=lambda p: '{"queries": ["ultrasonic rail testing"]}', seeds=seeds
        )
        assert [p["text"] for p in planned][:3] == [
            "rail crack detection",
            "track inspection robot",
            "ultrasonic rail testing",
        ]

    def test_model_queries_are_validated(self):
        raw = (
            '{"queries": ["railway crack detection", "rail defect AND inspection", '
            '"\\"track\\" inspection robot", "x", "a b c d e f g h i j k", '
            '"railway crack detection", "infrared sensor rail inspection"]}'
        )
        assert parse_model_queries(raw, 5) == [
            "railway crack detection",
            "rail defect inspection",
            "track inspection robot",
            "infrared sensor rail inspection",
        ]

    def test_the_model_writes_queries_after_the_rule_based_core(self):
        replies = []

        def model(prompt):
            replies.append(prompt)
            return '{"queries": ["rail surface defect detection", "track inspection robot"]}'

        planned, note = plan_queries(DESCRIPTION, 3, invoke=model)
        assert [p["written_by"] for p in planned] == ["rules", "model", "model"]
        assert planned[1]["text"] == "rail surface defect detection"
        assert note == ""
        assert "[MAIROS-TASK: queries]" in replies[0]

    def test_an_unusable_reply_falls_back_to_rules_and_says_so(self):
        planned, note = plan_queries(DESCRIPTION, 3, invoke=lambda prompt: "Sure! Here are some.")
        assert {p["written_by"] for p in planned} == {"rules"}
        assert len(planned) == 3
        assert "unusable" in note

    def test_a_failing_model_falls_back_to_rules(self):
        def broken(prompt):
            raise TimeoutError("slow")

        planned, note = plan_queries(DESCRIPTION, 2, invoke=broken)
        assert len(planned) == 2 and "TimeoutError" in note


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------
def _run(source: str, status: str = "ok", n: int = 1) -> SourceRun:
    run = SourceRun(source, status=status, detail="" if status == "ok" else "down")
    if status == "ok":
        run.ranked = [[{"title": f"p{i}"} for i in range(n)]]
    return run


class TestCoverage:
    TODAY = date(2026, 10, 22)

    def _papers(self, count: int, year: str = "2025", abstract: str = "text") -> list[dict]:
        return [
            {"title": f"P{i}", "year": year, "abstract": abstract, "sources": ["OpenAlex"]}
            for i in range(count)
        ]

    def test_a_healthy_search_has_no_warnings(self):
        report = build_coverage(
            [{"text": "q", "written_by": "rules"}],
            [_run("arxiv"), _run("openalex")],
            found=9,
            kept=self._papers(8),
            duplicates=2,
            today=self.TODAY,
        )
        assert report["warnings"] == []
        assert report["papers_kept"] == 8
        assert report["year_range"] == [2025, 2025]
        assert report["papers_by_source"] == {"OpenAlex": 8}
        assert report["full_text_read"] is False
        assert "not a systematic review" in report["scope_note"]

    def test_a_source_that_did_not_answer_is_named(self):
        report = build_coverage(
            [], [_run("arxiv"), _run("semantic_scholar", "rate_limited")], 8, self._papers(8), 0,
            today=self.TODAY,
        )
        assert report["warnings"] == [
            "Semantic Scholar did not answer, so this search covers arXiv only."
        ]

    def test_a_small_set_is_flagged_as_too_small_to_conclude_from(self):
        report = build_coverage([], [_run("openalex")], 3, self._papers(3), 0, today=self.TODAY)
        assert any("Only 3 paper(s)" in w for w in report["warnings"])

    def test_a_stale_set_and_missing_abstracts_are_flagged(self):
        report = build_coverage(
            [], [_run("openalex")], 6, self._papers(6, year="2015", abstract=""), 0,
            today=self.TODAY,
        )
        assert any("newest paper found is from 2015" in w for w in report["warnings"])
        assert any("6 paper(s) have no abstract" in w for w in report["warnings"])

    def test_nothing_reachable_says_nothing_was_searched(self):
        report = build_coverage(
            [], [_run("arxiv", "failed"), _run("openalex", "failed")], 0, [], 0, today=self.TODAY
        )
        assert len(report["warnings"]) == 1
        assert "nothing was searched" in report["warnings"][0]
        assert describe_scope(report) == "no literature source (none could be reached)"


# ---------------------------------------------------------------------------
# The agent, end to end over recorded responses
# ---------------------------------------------------------------------------
class _QueryWritingModel:
    """A live-looking model that only answers the query-writing prompt."""

    def __init__(self):
        self.prompts: list[str] = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return '{"queries": ["dense passage retrieval", "retrieval augmented language models"]}'


class TestLiteratureAgent:
    @pytest.mark.asyncio
    async def test_a_search_merges_all_three_sources(self, monkeypatch):
        use_recorded_sources(monkeypatch)
        ctx = await LiteratureAgent(llm=None).run(
            AgentContext(question="retrieval augmented generation")
        )

        papers = ctx.intermediate_results["retrieved_papers"]
        coverage = ctx.intermediate_results["literature_coverage"]

        assert len(papers) == 4
        assert papers[0]["sources"] == ["arXiv", "OpenAlex", "Semantic Scholar"]
        assert [s["status"] for s in coverage["sources"]] == ["ok", "ok", "ok"]
        assert coverage["papers_found"] == 4
        assert coverage["duplicates_merged"] == 3
        assert coverage["queries"] == [
            {"text": "retrieval augmented generation", "written_by": "rules"}
        ]
        # One chunk per kept paper, under its source's document-id prefix.
        assert {c["document_id"].split("_")[0] for c in ctx.retrieved_chunks} == {
            "arxiv",
            "openalex",
            "s2",
        }
        assert any("Venue: Neural Information Processing Systems" in c["text"] for c in ctx.retrieved_chunks)

    @pytest.mark.asyncio
    async def test_a_rate_limited_source_narrows_the_search_without_ending_it(self, monkeypatch):
        use_recorded_sources(monkeypatch, semantic_scholar=429)
        ctx = await LiteratureAgent(llm=None).run(AgentContext(question="rag"))

        coverage = ctx.intermediate_results["literature_coverage"]
        s2 = coverage["sources"][2]
        assert s2["status"] == "rate_limited"
        assert "SEMANTIC_SCHOLAR_API_KEY" in s2["detail"]
        assert ctx.intermediate_results["retrieved_papers"]  # arXiv and OpenAlex still answered
        assert any("Semantic Scholar did not answer" in w for w in coverage["warnings"])
        assert any("Semantic Scholar failed" in line for line in ctx.trace)

    @pytest.mark.asyncio
    async def test_no_reachable_source_leaves_an_honest_empty_result(self):
        # conftest's client refuses every connection.
        ctx = await LiteratureAgent(llm=None).run(AgentContext(question="rag"))
        assert ctx.intermediate_results["retrieved_papers"] == []
        coverage = ctx.intermediate_results["literature_coverage"]
        assert {s["status"] for s in coverage["sources"]} == {"failed"}
        assert "nothing was searched" in coverage["warnings"][0]

    @pytest.mark.asyncio
    async def test_a_live_model_writes_the_extra_queries(self, monkeypatch):
        client = use_recorded_sources(monkeypatch)
        model = _QueryWritingModel()
        ctx = await LiteratureAgent(llm=model).run(AgentContext(question="retrieval augmented generation"))

        coverage = ctx.intermediate_results["literature_coverage"]
        assert [q["written_by"] for q in coverage["queries"]] == ["rules", "model", "model"]
        # arXiv gets one combined request; OpenAlex and Semantic Scholar one per query.
        hosts = [urlparse(u).hostname for u in client.requests]
        assert hosts.count("export.arxiv.org") == 1
        assert hosts.count("api.openalex.org") == 3
        assert hosts.count("api.semanticscholar.org") == 3

    @pytest.mark.asyncio
    async def test_the_configured_sources_are_the_ones_searched(self, monkeypatch):
        from app.config import settings

        client = use_recorded_sources(monkeypatch)
        monkeypatch.setattr(settings, "literature_sources", "openalex")
        ctx = await LiteratureAgent(llm=None).run(AgentContext(question="rag"))

        assert {urlparse(u).hostname for u in client.requests} == {"api.openalex.org"}
        assert [s["name"] for s in ctx.intermediate_results["literature_coverage"]["sources"]] == [
            "OpenAlex"
        ]

    @pytest.mark.asyncio
    async def test_max_results_caps_what_is_kept(self, monkeypatch):
        from app.config import settings

        use_recorded_sources(monkeypatch)
        monkeypatch.setattr(settings, "literature_max_results", 2)
        ctx = await LiteratureAgent(llm=None).run(AgentContext(question="rag"))
        coverage = ctx.intermediate_results["literature_coverage"]
        assert len(ctx.intermediate_results["retrieved_papers"]) == 2
        assert (coverage["papers_found"], coverage["papers_kept"]) == (4, 2)


class TestDownstream:
    @pytest.mark.asyncio
    async def test_fetched_abstracts_are_indexed_under_their_source(self, monkeypatch, chroma_store):
        from services.agents.indexer import IndexerAgent

        use_recorded_sources(monkeypatch)
        ctx = AgentContext(question="rag", project_id="p1", chroma_store=chroma_store)
        ctx = await LiteratureAgent(llm=None).run(ctx)
        ctx = await IndexerAgent(llm=None).run(ctx)

        hits = chroma_store.query("open-domain question answering passage retrieval", top_k=8)
        dpr = next(h for h in hits if h.document_name.startswith("Dense Passage"))
        assert dpr.document_id == "openalex_W3099700870"

    @pytest.mark.asyncio
    async def test_graph_hits_boost_the_chunks_of_a_fetched_abstract(
        self, monkeypatch, chroma_store, tmp_path
    ):
        """The graph cites a fetched abstract by its document id, while the index
        holds it as `<document id>_0`, `_1`, …. Matching chunk ids only, a live
        run used 21 graph relations and boosted 0 passages."""
        from services.agents.indexer import IndexerAgent
        from services.knowledge_graph.networkx_store import KnowledgeGraphStore
        from services.retrieval.graph_retriever import GraphRetriever
        from services.retrieval.hybrid import HybridRetriever

        use_recorded_sources(monkeypatch)
        ctx = AgentContext(question="rag", project_id="p1", chroma_store=chroma_store)
        ctx = await LiteratureAgent(llm=None).run(ctx)
        ctx = await IndexerAgent(llm=None).run(ctx)

        # What the Knowledge Graph agent records for a fetched abstract.
        dpr_document = "openalex_W3099700870"
        assert dpr_document in {c["chunk_id"] for c in ctx.retrieved_chunks}
        store = KnowledgeGraphStore(base_dir=tmp_path / "graphs")
        graph = store.for_project("p1")
        graph.add_entity("dense passage retrieval", "Method", source_chunk_ids=[dpr_document])
        graph.add_relation("dense passage retrieval", "USES", "dual encoder")

        chunks, relations = HybridRetriever(
            vector=chroma_store, graph=GraphRetriever("p1", store)
        ).retrieve("open-domain question answering", project_id="p1", entities=["dense passage retrieval"], top_k=8)

        boosted = [c for c in chunks if c.metadata.get("graph_hit")]
        assert boosted, "no passage was boosted by the graph"
        assert {c.document_id for c in boosted} == {dpr_document}
        # The id the graph holds is not any indexed chunk's own id.
        assert all(c.chunk_id != dpr_document for c in boosted)

    def test_an_uploaded_document_is_still_matched_by_chunk_only(self):
        """Citing one chunk of an upload must not boost its other chunks."""
        from services.retrieval.hybrid import HybridRetriever
        from services.retrieval.vector_store import RetrievedChunk

        chunks = [
            RetrievedChunk(chunk_id=f"doc1_{i}", document_id="doc1", document_name="up.pdf",
                           page=1, text=f"passage {i}", score=0.0, metadata={})
            for i in range(3)
        ]

        class _Vector:
            def query(self, *args, **kwargs):
                return chunks

        class _Graph:
            def search(self, **kwargs):
                from services.retrieval.graph_retriever import GraphResult

                return [GraphResult("a", "USES", "b", chunk_ids=["doc1_1"])]

        result, _ = HybridRetriever(vector=_Vector(), graph=_Graph()).retrieve("q", top_k=3)
        assert [c.chunk_id for c in result if c.metadata.get("graph_hit")] == ["doc1_1"]

    @pytest.mark.asyncio
    async def test_novelty_scope_names_every_source_searched(self, monkeypatch):
        from services.agents.novelty import NoveltyAgent

        use_recorded_sources(monkeypatch)
        ctx = await LiteratureAgent(llm=None).run(AgentContext(question="rag"))
        ctx = await NoveltyAgent(llm=None).run(ctx)

        scope = ctx.intermediate_results["novelty"]["scope"]
        assert "4 abstract(s) fetched from arXiv, OpenAlex and Semantic Scholar" in scope
        assert ctx.intermediate_results["novelty"]["field_novelty"] == "not_assessed"

    def test_references_use_the_venue_when_there_is_one(self):
        from services.agents.citations import fallback_apa

        rag = merge_ranked(_ranked())[0][0]
        reference = fallback_apa(rag)
        assert "Neural Information Processing Systems." in reference
        assert reference.endswith("https://doi.org/10.5555/3495724.3496517")
