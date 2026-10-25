"""Regression tests for the independent review of the literature search and the
`project` flow (25 October 2026).

One class per finding, most serious first. Each finding was reproduced before
it was fixed. Run against the reviewed commit (dd7a18c), 27 of these 30 tests
fail, at least one per finding. The three that pass there are guards that a
fix did not overreach: a figure the user did state is kept, a project that
mentions patents later is still a project, and a failed first model call still
raises.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from literature_fixtures import SEMANTIC_SCHOLAR_SEARCH, use_recorded_sources
from services.agents.base import AgentContext, BaseAgent
from services.agents.indexer import IndexerAgent, RetrieverAgent
from services.agents.intake import ProjectIntakeAgent
from services.agents.literature import LiteratureAgent
from services.agents.novelty import NoveltyAgent
from services.agents.router import RouterAgent, looks_like_project_description
from services.literature.coverage import describe_scope
from services.literature.merge import merge_ranked
from services.literature.papers import new_paper, paper_aliases
from services.literature.queries import SEARCH_STOPWORDS, plan_queries, rule_queries
from services.literature.sources import (
    ArxivSource,
    SemanticScholarSource,
    SourceResponseError,
    arxiv_query,
    parse_arxiv,
)

DESCRIPTION = (
    "Low-cost railway track crack detection robot\n"
    "Manual inspection of railway tracks is slow and expensive. We propose a robot "
    "that detects cracks wider than 2 mm in railway tracks using a camera and "
    "infrared sensors, and sends an alert with the GPS location of each crack."
)


class _Model:
    """A live-looking model with a fixed reply that counts its calls."""

    def __init__(self, reply: Any = ""):
        self.reply = reply if isinstance(reply, str) else json.dumps(reply)
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        return self.reply


def _rag_paper() -> dict:
    return new_paper(
        "arxiv", "2005.11401v4", title="Retrieval-Augmented Generation",
        abstract="Retrieval augmented generation grounds answers in retrieved passages.",
        arxiv_id="2005.11401",
    )


async def _index(store, project: str, papers: list[dict]) -> None:
    ctx = AgentContext(question="rag", project_id=project, chroma_store=store)
    ctx.intermediate_results["retrieved_papers"] = papers
    await IndexerAgent(llm=None).run(ctx)


# ---------------------------------------------------------------------------
# 1. Fetched-paper chunk ids were shared across projects
# ---------------------------------------------------------------------------
class TestFetchedChunksStayInTheirProject:
    @pytest.mark.asyncio
    async def test_a_second_project_fetching_the_same_paper_leaves_the_first_intact(
        self, chroma_store
    ):
        await _index(chroma_store, "A", [_rag_paper()])
        await _index(chroma_store, "B", [_rag_paper()])

        assert chroma_store.count("A") > 0, "project B's search took project A's chunks"
        assert chroma_store.count("B") > 0

        chroma_store.delete_project("B")
        assert chroma_store.count("A") > 0, "deleting B removed a chunk A relied on"

    @pytest.mark.asyncio
    async def test_re_indexing_replaces_an_earlier_builds_copy(self, chroma_store):
        # What a build before stable ids wrote: the versioned arXiv id.
        chroma_store.add_chunks(
            ["arxiv_2005.11401v4_0"],
            ["Title: Retrieval-Augmented Generation (old copy)"],
            [{"document_id": "arxiv_2005.11401v4", "document_name": "Retrieval-Augmented Generation",
              "project_id": "A", "page": 1, "chunk_index": 0}],
        )
        await _index(chroma_store, "A", [_rag_paper()])

        documents = {c["document_id"] for c in chroma_store.all_chunks("A")}
        assert documents == {"arxiv_2005.11401"}


# ---------------------------------------------------------------------------
# 2. A string where the model should give a list was read letter by letter
# ---------------------------------------------------------------------------
class TestBriefFieldsGivenAsStrings:
    def test_a_comma_separated_string_is_split_into_items(self):
        brief, dropped = ProjectIntakeAgent(llm=_Model({
            "title": "Railway crack robot",
            "problem": "Manual inspection of railway tracks is slow and expensive.",
            "methods": "camera, infrared sensors",
            "contributions": "a robot that detects cracks in railway tracks, using a camera",
            "keywords": "railway inspection, crack detection",
        })).model_brief(DESCRIPTION)

        assert brief["keywords"] == ["railway inspection", "crack detection"]
        assert brief["methods"] == ["camera", "infrared sensors"]
        # A sentence field keeps its commas: one contribution, not two.
        assert brief["contributions"] == ["a robot that detects cracks in railway tracks, using a camera"]
        assert dropped == 0

    def test_a_single_letter_is_never_a_search_query(self):
        planned, _ = plan_queries(DESCRIPTION, 4, seeds=[{"text": "r"}, {"text": "a"}])
        assert planned and all(len(p["text"]) > 1 for p in planned)


# ---------------------------------------------------------------------------
# 3. Project coverage checked only the retriever's top passages
# ---------------------------------------------------------------------------
class TestEveryFetchedPaperIsChecked:
    @pytest.mark.asyncio
    async def test_contributions_are_checked_against_every_fetched_abstract(
        self, monkeypatch, chroma_store, tmp_path
    ):
        from services.knowledge_graph.networkx_store import kg_store

        monkeypatch.setattr(kg_store, "_base_dir", tmp_path / "graphs")
        kg_store.reset()
        use_recorded_sources(monkeypatch)

        ctx = AgentContext(question="sequence transduction", project_id="p1", chroma_store=chroma_store)
        ctx.intermediate_results["project_brief"] = {
            "search_text": "sequence transduction with attention",
            "contributions": ["Dense passage retrieval for open-domain question answering"],
        }
        ctx = await LiteratureAgent(llm=None).run(ctx)
        ctx = await IndexerAgent(llm=None).run(ctx)
        # Retrieval for the description as a whole keeps one passage only.
        ctx = await RetrieverAgent(llm=None, top_k=1).run(ctx)
        ctx = await NoveltyAgent(llm=None).run(ctx)
        kg_store.reset()

        report = ctx.intermediate_results["novelty"]
        assert "4 abstract(s) fetched from arXiv, OpenAlex and Semantic Scholar during this run" in report["scope"]
        nearest = report["assessments"][0]["nearest_prior_work"][0]["citation"]["document_name"]
        assert nearest.startswith("Dense Passage Retrieval")


# ---------------------------------------------------------------------------
# 4. A paper's identity depended on which source answered
# ---------------------------------------------------------------------------
class TestOnePaperOneRecord:
    def _search(self, client, project_id, monkeypatch, **status):
        use_recorded_sources(monkeypatch, **status)
        task = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "find papers on retrieval augmented generation", "flow": "search"},
        ).json()
        assert client.get(f"/api/tasks/{task['id']}").json()["status"] == "completed"

    def test_a_paper_found_through_different_sources_is_stored_once(self, client, monkeypatch):
        from app import dependencies as deps

        project_id = client.post("/api/projects", json={"name": "Ids"}).json()["id"]
        # Semantic Scholar down: DPR is known only by its DOI (OpenAlex).
        self._search(client, project_id, monkeypatch, semantic_scholar=503)
        # Next time it answers, and supplies DPR's arXiv id as well.
        self._search(client, project_id, monkeypatch)

        titles = [p["title"] for p in client.get(f"/api/projects/{project_id}/papers").json()]
        assert titles.count("Dense Passage Retrieval for Open-Domain Question Answering") == 1
        dpr_documents = {
            c["document_id"]
            for c in deps.get_chroma_store().all_chunks(project_id)
            if c["document_name"].startswith("Dense Passage")
        }
        assert dpr_documents == {"arxiv_2004.04906"}

    def test_a_record_stored_by_an_earlier_build_is_replaced(self, client):
        from app.store import metadata_store

        project_id = client.post("/api/projects", json={"name": "Legacy"}).json()["id"]
        # Earlier builds stored arXiv papers under the versioned arXiv id.
        metadata_store.add_paper(project_id, {"id": "2005.11401v4", "title": "Retrieval-Augmented Generation"})
        paper = merge_ranked([[_rag_paper()]])[0][0]
        metadata_store.add_paper(project_id, paper, aliases=paper_aliases(paper))

        stored = metadata_store.list_papers(project_id)
        assert [p.id for p in stored] == [f"{project_id}:arxiv:2005.11401"]


# ---------------------------------------------------------------------------
# 5. An invented number passed the grounding check
# ---------------------------------------------------------------------------
class TestNumbersMustBeTheUsers:
    def _contributions(self, claimed: str) -> tuple[list[str], int]:
        brief, dropped = ProjectIntakeAgent(llm=_Model({
            "title": "Railway crack robot",
            "problem": "Manual inspection of railway tracks is slow and expensive.",
            "contributions": [claimed],
        })).model_brief(DESCRIPTION)
        return brief["contributions"], dropped

    def test_a_figure_the_description_never_gave_is_dropped(self):
        contributions, dropped = self._contributions("The robot detects 95% of cracks in railway tracks")
        assert contributions == [] and dropped == 1

    def test_a_figure_the_description_gives_is_kept(self):
        contributions, _ = self._contributions("A robot that detects cracks wider than 2 mm")
        assert contributions == ["A robot that detects cracks wider than 2 mm"]


# ---------------------------------------------------------------------------
# 6. Every request of 800+ characters was routed to `project`
# ---------------------------------------------------------------------------
class TestLongRequestsKeepTheirIntent:
    def test_a_long_patent_request_goes_to_the_patent_flow(self):
        request = (
            "Does anything in this project overlap the patent claims below? "
            + "1. A method for detecting rail cracks comprising a camera, wherein ... " * 12
        )
        assert len(request) > 800
        assert not looks_like_project_description(request)
        assert RouterAgent.heuristic(request, False, 5)[0] == "patent"

    def test_a_long_request_that_opens_with_a_search_is_a_search(self):
        request = "Find papers on " + "graph neural networks for molecule property prediction " * 16
        assert RouterAgent.heuristic(request, False, 0)[0] == "search"

    def test_a_description_that_mentions_a_patent_later_is_still_a_project(self):
        text = DESCRIPTION + " We hope to patent the design once it works."
        assert RouterAgent.heuristic(text, False, 3)[0] == "project"


# ---------------------------------------------------------------------------
# 7. Records joined only through a third record were not merged
# ---------------------------------------------------------------------------
class TestBridgedRecordsMerge:
    def test_a_record_carrying_both_ids_joins_the_other_two(self):
        preprint = new_paper("arxiv", "2101.00001v1", title="Crack Detection on Rails with Vision",
                             arxiv_id="2101.00001")
        published = new_paper("openalex", "W9", title="Vision-Based Rail Crack Detection for Low-Cost Robots",
                              doi="10.1000/rail.2021")
        bridge = new_paper("semantic_scholar", "s9", title="Vision-Based Rail Crack Detection",
                           arxiv_id="2101.00001", doi="10.1000/rail.2021")

        merged, duplicates = merge_ranked([[preprint], [published], [bridge]])

        assert len(merged) == 1 and duplicates == 2
        assert merged[0]["sources"] == ["arXiv", "OpenAlex", "Semantic Scholar"]
        assert merged[0]["doi"] == "10.1000/rail.2021"


# ---------------------------------------------------------------------------
# 8. Every concept was attributed to the same chunks
# ---------------------------------------------------------------------------
class TestConceptsPointAtTheirOwnPassages:
    @pytest.mark.asyncio
    async def test_attribution_and_paper_links_follow_mentions(self, tmp_path):
        from services.agents.kg_agent import KnowledgeGraphAgent
        from services.knowledge_graph.networkx_store import KnowledgeGraphStore

        store = KnowledgeGraphStore(base_dir=tmp_path)
        reply = json.dumps({
            "entities": [
                {"name": "dense passage retrieval", "type": "Method"},
                {"name": "BM25", "type": "Method"},
            ],
            "relations": [],
        })
        ctx = AgentContext(question="q", project_id="p1")
        ctx.retrieved_chunks = [
            {"chunk_id": "c1", "text": "We use dense passage retrieval over the notes."},
            {"chunk_id": "c2", "text": "BM25 remains a strong sparse baseline."},
        ]
        ctx.intermediate_results["retrieved_papers"] = [
            {"title": "Sparse Baselines", "authors": [], "abstract": "A study of BM25 baselines."}
        ]

        await KnowledgeGraphAgent(llm=lambda prompt: reply, store=store).run(ctx)

        graph = store.for_project("p1").graph
        assert graph.nodes["dense passage retrieval"]["source_chunk_ids"] == ["c1"]
        assert graph.nodes["BM25"]["source_chunk_ids"] == ["c2"]
        linked = {t for s, t, d in graph.edges(data=True) if s == "Sparse Baselines" and d["relation"] == "PART_OF"}
        assert linked == {"BM25"}


# ---------------------------------------------------------------------------
# 9. Acronyms were dropped from rule-based queries
# ---------------------------------------------------------------------------
class TestAcronymsAreSearched:
    def test_rule_based_queries_keep_acronyms(self):
        assert rule_queries("AI in healthcare") == ["ai healthcare"]
        assert rule_queries("3D object detection for 5G networks") == ["3d object detection 5g networks"]

    def test_the_arxiv_expression_keeps_them_too(self):
        assert arxiv_query("AI in healthcare") == "all:AI AND all:healthcare"
        assert arxiv_query("ai healthcare") == "all:ai AND all:healthcare"

    def test_ordinary_two_letter_words_are_still_dropped(self):
        assert rule_queries("an AI as we go to it") == ["ai"]


# ---------------------------------------------------------------------------
# 10. arXiv's in-band error entry was parsed as a paper
# ---------------------------------------------------------------------------
ARXIV_ERROR_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>http://arxiv.org/api/errors#incorrect_id_format_for_x</id><title>Error</title>
<summary>incorrect id format for x</summary>
<author><name>arXiv api core</name></author></entry></feed>"""


class TestArxivErrorsAreErrors:
    def test_an_error_feed_raises_with_arxivs_message(self):
        with pytest.raises(SourceResponseError, match="incorrect id format"):
            parse_arxiv(ARXIV_ERROR_FEED)

    @pytest.mark.asyncio
    async def test_the_source_reports_a_failure_not_a_paper(self):
        class Client:
            async def get(self, url, **kwargs):
                return httpx.Response(200, text=ARXIV_ERROR_FEED, request=httpx.Request("GET", url))

        run = await ArxivSource().search(Client(), ["rag"])
        assert run.status == "failed" and run.returned == 0
        assert "arXiv reported an error" in run.detail


# ---------------------------------------------------------------------------
# 11. No configured source was reported as "could not be reached"
# ---------------------------------------------------------------------------
class TestSourceConfiguration:
    @pytest.mark.asyncio
    async def test_no_configured_source_says_so_and_spends_no_model_call(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "literature_sources", "")
        model = _Model('{"queries": ["rag systems"]}')
        ctx = await LiteratureAgent(llm=model).run(AgentContext(question="rag"))

        coverage = ctx.intermediate_results["literature_coverage"]
        assert coverage["warnings"][0].startswith("No literature source is configured")
        assert describe_scope(coverage) == "no literature source (none is configured)"
        assert model.calls == 0

    @pytest.mark.asyncio
    async def test_an_unknown_source_name_is_named(self, monkeypatch):
        from app.config import settings

        use_recorded_sources(monkeypatch)
        monkeypatch.setattr(settings, "literature_sources", "arxiv,pubmed")
        ctx = await LiteratureAgent(llm=None).run(AgentContext(question="rag"))

        warnings = ctx.intermediate_results["literature_coverage"]["warnings"]
        assert any("pubmed" in w and "ignored" in w for w in warnings)


# ---------------------------------------------------------------------------
# 12. A stalled Semantic Scholar held up the whole search
# ---------------------------------------------------------------------------
class TestSemanticScholarDeadline:
    @pytest.mark.asyncio
    async def test_sequential_queries_stop_at_the_deadline(self):
        delay = 0.3

        class SlowClient:
            requests = 0

            async def get(self, url, **kwargs):
                SlowClient.requests += 1
                timeout = kwargs.get("timeout")
                if timeout is not None and timeout < delay:
                    await asyncio.sleep(timeout)
                    raise httpx.ReadTimeout("timed out")
                await asyncio.sleep(delay)
                return httpx.Response(200, json=SEMANTIC_SCHOLAR_SEARCH, request=httpx.Request("GET", url))

        source = SemanticScholarSource(deadline=0.5, request_timeout=20)
        started = time.monotonic()
        run = await source.search(SlowClient(), ["q1", "q2", "q3", "q4"])
        elapsed = time.monotonic() - started

        assert elapsed < 4 * delay, "the deadline did not cap the search"
        assert SlowClient.requests < 4
        assert run.status == "ok" and run.returned > 0  # what arrived in time is kept
        assert "Stopped after" in run.detail and "0.5 s" in run.detail


# ---------------------------------------------------------------------------
# 13. A failed retry discarded the first reply
# ---------------------------------------------------------------------------
class _CutOffThenRateLimited(BaseChatModel):
    calls: list = []

    @property
    def _llm_type(self) -> str:
        return "cut-off-then-429"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        self.calls.append(kwargs)
        if kwargs.get("max_tokens"):
            raise RuntimeError("429 rate limit")
        message = AIMessage(content='{"gaps": [{"gap": "no abl', response_metadata={"finish_reason": "length"})
        return ChatResult(generations=[ChatGeneration(message=message)])


class _Echo(BaseAgent):
    name = "echo"

    async def run(self, ctx):  # pragma: no cover
        return ctx


class TestRetryFailureKeepsTheReply:
    def test_the_cut_off_reply_is_returned_when_the_retry_fails(self):
        model = _CutOffThenRateLimited(calls=[])
        assert _Echo(llm=model).invoke_llm("find gaps") == '{"gaps": [{"gap": "no abl'
        assert len(model.calls) == 2

    def test_a_failed_first_call_still_raises(self):
        class Down(BaseChatModel):
            @property
            def _llm_type(self) -> str:
                return "down"

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                raise RuntimeError("provider down")

        with pytest.raises(RuntimeError, match="provider down"):
            _Echo(llm=Down()).invoke_llm("anything")


# ---------------------------------------------------------------------------
# 14. A project answer lost its header when the novelty step failed
# ---------------------------------------------------------------------------
class TestProjectAnswerWithoutNovelty:
    @pytest.mark.asyncio
    async def test_the_header_and_the_focused_question_survive(self):
        from services.agents.synthesis import SynthesisAgent
        from services.generation.provider import OfflineChatModel

        asked: list[str] = []

        class Generation:
            async def generate(self, question, chunks):
                asked.append(question)
                return "What the sources say."

        agent = SynthesisAgent(llm=OfflineChatModel())
        agent._generation = Generation()
        ctx = AgentContext(question=DESCRIPTION * 5, project_id="p1")
        ctx.retrieved_chunks = [{"chunk_id": "c1", "document_name": "Paper", "text": "Rail cracks."}]
        ctx.intermediate_results.update(
            routing={"flow": "project"},
            project_brief={
                "problem": "Manual inspection of railway tracks is slow and expensive.",
                "contributions": ["A robot that detects cracks"],
                "search_text": "railway crack detection robot",
                "extracted_by": "rules",
            },
            literature_coverage={
                "sources": [{"name": "arXiv", "status": "ok"}],
                "queries": [{"text": "railway crack detection"}],
                "papers_kept": 3,
                "papers_by_source": {"arXiv": 3},
                "searched_on": "2026-10-25",
                "warnings": [],
            },
        )
        # No `novelty` result: the step failed.
        await agent.run(ctx)

        answer = ctx.intermediate_results["final_answer"]
        assert answer.startswith("**Your project, as MAIROS read it**")
        assert "**Searched:** arXiv (1 query, 2026-10-25); kept 3 abstract(s), all from arXiv." in answer
        assert asked == ["railway crack detection robot"]


# ---------------------------------------------------------------------------
# 15. The literature package kept two stopword lists that disagreed
# ---------------------------------------------------------------------------
class TestOneStopwordList:
    def test_queries_and_arxiv_terms_share_one_list(self):
        import services.literature.sources as sources_module

        assert sources_module.SEARCH_STOPWORDS is SEARCH_STOPWORDS
        assert not hasattr(sources_module, "_STOPWORDS")

    @pytest.mark.parametrize("word", ["did", "survey", "approach", "or"])
    def test_a_word_dropped_from_queries_is_dropped_from_arxiv_terms(self, word):
        assert word in SEARCH_STOPWORDS
        assert arxiv_query(f"{word} retrieval") == "all:retrieval"
