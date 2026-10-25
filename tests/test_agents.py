"""Unit tests for the agent layer: routing, citations, KG, and JSON parsing."""

from __future__ import annotations

import pytest

from services.agents.base import AgentContext
from services.agents.citations import CitationAgent, fallback_apa
from services.agents.kg_agent import KnowledgeGraphAgent
from services.agents.literature import LiteratureAgent
from services.agents.router import FLOWS, RouterAgent
from services.common.json_utils import extract_json
from services.knowledge_graph.entity_extractor import EntityRelationExtractor
from services.knowledge_graph.networkx_store import KnowledgeGraphStore


class TestJsonExtraction:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        raw = 'Sure!\n```json\n{"a": [1, 2]}\n```\nHope that helps.'
        assert extract_json(raw) == {"a": [1, 2]}

    def test_json_embedded_in_prose(self):
        raw = 'Here is the result: {"flow": "search"} — let me know.'
        assert extract_json(raw) == {"flow": "search"}

    def test_braces_inside_strings_do_not_break_parsing(self):
        raw = 'text {"note": "a } brace", "ok": true} tail'
        assert extract_json(raw) == {"note": "a } brace", "ok": True}

    def test_unparseable_returns_default(self):
        assert extract_json("no json here", default={}) == {}

    def test_none_returns_default(self):
        assert extract_json(None, default=[]) == []


class TestRouter:
    def test_document_forces_analyze(self):
        decision = RouterAgent(llm=None).decide("anything", has_document=True)
        assert decision.flow == "analyze"

    def test_search_intent_detected(self):
        decision = RouterAgent(llm=None).decide("find papers on graph neural networks")
        assert decision.flow == "search"

    def test_empty_library_routes_to_search(self):
        decision = RouterAgent(llm=None).decide("what is attention?", doc_count=0)
        assert decision.flow == "search"

    def test_populated_library_routes_to_answer(self):
        decision = RouterAgent(llm=None).decide("what is attention?", doc_count=3)
        assert decision.flow == "answer"

    def test_explicit_flow_wins(self):
        decision = RouterAgent(llm=None).decide(
            "find papers on X", doc_count=0, forced_flow="answer"
        )
        assert decision.flow == "answer"
        assert decision.source == "explicit"

    def test_every_flow_maps_to_known_agents(self):
        from services.agents.orchestrator import AgentOrchestrator

        registry = set(AgentOrchestrator(llm=object()).agents)
        for flow, agents in FLOWS.items():
            missing = set(agents) - registry
            assert not missing, f"flow '{flow}' names unknown agents: {missing}"


class TestCitations:
    def test_apa_single_author(self):
        ref = fallback_apa(
            {"title": "Attention Is All You Need", "authors": ["Ashish Vaswani"], "year": "2017"}
        )
        assert ref.startswith("Vaswani, A. (2017).")

    def test_apa_multiple_authors_use_ampersand(self):
        ref = fallback_apa(
            {"title": "A Paper", "authors": ["Jane Doe", "John Roe"], "year": "2020"}
        )
        assert "Doe, J., & Roe, J." in ref

    def test_missing_year_becomes_nd(self):
        assert "(n.d.)" in fallback_apa({"title": "Untitled", "authors": []})

    @pytest.mark.asyncio
    async def test_agent_falls_back_to_documents_when_no_papers(self):
        ctx = AgentContext(question="q")
        ctx.retrieved_chunks = [
            {"document_name": "paper.pdf", "text": "…", "chunk_id": "c1"}
        ]
        ctx = await CitationAgent(llm=None).run(ctx)
        assert len(ctx.intermediate_results["references"]) == 1

    @pytest.mark.asyncio
    async def test_agent_handles_no_sources(self):
        ctx = await CitationAgent(llm=None).run(AgentContext(question="q"))
        assert ctx.intermediate_results["references"] == []


class TestEntityExtractor:
    class _FakeLLM:
        def __init__(self, response: str):
            self.response = response

        def invoke(self, prompt: str) -> str:
            return self.response

    def test_valid_extraction(self):
        extractor = EntityRelationExtractor(
            llm=self._FakeLLM(
                '```json\n{"entities": [{"name": "RAG", "type": "Method"},'
                ' {"name": "Hallucination", "type": "Concept"}],'
                ' "relations": [{"subject": "RAG", "relation": "IMPROVES",'
                ' "object": "Hallucination", "confidence": 0.9}]}\n```'
            )
        )
        result = extractor.extract("some text")
        assert {e.name for e in result.entities} == {"RAG", "Hallucination"}
        assert result.relations[0].relation == "IMPROVES"

    def test_unknown_relation_normalised(self):
        extractor = EntityRelationExtractor(
            llm=self._FakeLLM(
                '{"entities": [{"name": "A"}, {"name": "B"}],'
                ' "relations": [{"subject": "A", "relation": "zaps", "object": "B"}]}'
            )
        )
        assert extractor.extract("x").relations[0].relation == "RELATED_TO"

    def test_relation_endpoints_are_promoted_to_entities(self):
        extractor = EntityRelationExtractor(
            llm=self._FakeLLM(
                '{"entities": [{"name": "A"}],'
                ' "relations": [{"subject": "A", "relation": "USES", "object": "B"}]}'
            )
        )
        assert "B" in {e.name for e in extractor.extract("x").entities}

    def test_garbage_response_is_survivable(self):
        assert EntityRelationExtractor(llm=self._FakeLLM("sorry!")).extract("x").entities == []

    def test_no_llm_returns_empty(self):
        assert EntityRelationExtractor(llm=None).extract("x").entities == []


class TestGraphStore:
    def test_entities_merge_and_count_mentions(self, tmp_path):
        graph = KnowledgeGraphStore(tmp_path).for_project("p1")
        graph.add_entity("Transformer", "Method", "an architecture")
        graph.add_entity("Transformer", "Unknown", "")
        assert graph.graph.nodes["Transformer"]["mentions"] == 2
        assert graph.graph.nodes["Transformer"]["type"] == "Method"

    def test_relation_creates_missing_nodes(self, tmp_path):
        graph = KnowledgeGraphStore(tmp_path).for_project("p1")
        assert graph.add_relation("A", "USES", "B")
        assert graph.stats() == {"nodes": 2, "edges": 1}

    def test_self_loop_rejected(self, tmp_path):
        graph = KnowledgeGraphStore(tmp_path).for_project("p1")
        assert graph.add_relation("A", "USES", "A") is False

    def test_projects_are_isolated(self, tmp_path):
        store = KnowledgeGraphStore(tmp_path)
        store.for_project("p1").add_entity("OnlyInP1")
        assert store.for_project("p2").stats()["nodes"] == 0

    def test_graph_persists_across_instances(self, tmp_path):
        KnowledgeGraphStore(tmp_path).for_project("p1").add_relation("A", "USES", "B")
        reloaded = KnowledgeGraphStore(tmp_path).for_project("p1")
        assert reloaded.stats() == {"nodes": 2, "edges": 1}

    def test_to_json_is_force_graph_shaped(self, tmp_path):
        graph = KnowledgeGraphStore(tmp_path).for_project("p1")
        graph.add_relation("A", "USES", "B")
        data = graph.to_json()
        assert {n["id"] for n in data["nodes"]} == {"A", "B"}
        assert data["links"][0] == {
            "source": "A",
            "target": "B",
            "label": "USES",
            "confidence": 1.0,
        }

    def test_neighbors_respects_depth(self, tmp_path):
        graph = KnowledgeGraphStore(tmp_path).for_project("p1")
        graph.add_relation("A", "USES", "B")
        graph.add_relation("B", "USES", "C")
        assert graph.neighbors("A", depth=1) == {"B"}
        assert graph.neighbors("A", depth=2) == {"B", "C"}


class TestKnowledgeGraphAgent:
    @pytest.mark.asyncio
    async def test_papers_and_authors_become_nodes(self, tmp_path):
        store = KnowledgeGraphStore(tmp_path)
        ctx = AgentContext(question="q", project_id="p1")
        ctx.intermediate_results["retrieved_papers"] = [
            {"title": "Attention Is All You Need", "authors": ["Ashish Vaswani"], "url": ""}
        ]

        ctx = await KnowledgeGraphAgent(llm=None, store=store).run(ctx)

        graph = store.for_project("p1").graph
        assert graph.has_node("Attention Is All You Need")
        assert graph.has_edge("Attention Is All You Need", "Ashish Vaswani")
        assert ctx.intermediate_results["graph_stats"]["nodes"] >= 2


class TestLiteratureAgent:
    def test_query_builder_drops_stopwords(self):
        query = LiteratureAgent._build_query("What are the recent papers on graph neural networks?")
        assert "graph" in query
        assert "all:what" not in query.lower()

    @pytest.mark.asyncio
    async def test_network_failure_degrades_gracefully(self, monkeypatch):
        agent = LiteratureAgent(llm=None)

        async def boom(_question):
            raise ConnectionError("offline")

        monkeypatch.setattr(agent, "fetch", boom)
        ctx = await agent.run(AgentContext(question="topic"))

        assert ctx.intermediate_results["retrieved_papers"] == []
        assert any("failed" in line.lower() for line in ctx.trace)


class TestExtractionReportsWhyItFoundNothing:
    """A live run added "+0 nodes" three times with no explanation."""

    def test_empty_model_output_is_reported(self):
        from services.knowledge_graph.entity_extractor import EntityRelationExtractor

        result = EntityRelationExtractor(llm=lambda prompt: "").extract("Transformers use attention.")
        assert result.entities == []
        assert "empty response" in result.problem

    def test_unparseable_model_output_is_reported(self):
        from services.knowledge_graph.entity_extractor import EntityRelationExtractor

        result = EntityRelationExtractor(llm=lambda prompt: "Sure! Here are the entities: attention").extract("text")
        assert "no parseable JSON" in result.problem

    def test_valid_output_reports_no_problem(self):
        from services.knowledge_graph.entity_extractor import EntityRelationExtractor

        payload = '{"entities": [{"name": "self-attention", "type": "Method"}], "relations": []}'
        result = EntityRelationExtractor(llm=lambda prompt: payload).extract("text")
        assert [e.name for e in result.entities] == ["self-attention"]
        assert result.problem == ""

    def test_the_prompt_has_no_stray_quote_after_the_schema(self):
        from services.knowledge_graph.entity_extractor import EXTRACTION_PROMPT

        rendered = EXTRACTION_PROMPT.format(text="x")
        assert '}]}\n\nRules:' in rendered
