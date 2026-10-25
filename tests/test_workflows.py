"""Research workflow tests — comparison, gaps, hypotheses, experiments, patents.

All offline and deterministic: the agents run against the ``OfflineChatModel``
and hand-built chunk lists, so every assertion here is about MAIROS's own
logic (evidence linking, validation, flow registration) rather than about what
a hosted model happened to say.
"""

from __future__ import annotations

import pytest

from services.agents.base import AgentContext
from services.agents.comparison import ComparisonAgent
from services.agents.evidence import citation_for, group_sources, render_sources
from services.agents.experiment import ExperimentAgent
from services.agents.gaps import GapDetectionAgent
from services.agents.hypothesis import HypothesisAgent
from services.agents.patent_awareness import PatentAwarenessAgent
from services.agents.router import FLOW_DESCRIPTIONS, FLOWS, RouterAgent
from services.generation.provider import OfflineChatModel
from services.patents.sources import (
    DISCLAIMER,
    PatentSourceError,
    describe_sources,
    validate_public_url,
)


def chunk(chunk_id: str, document: str, text: str, page: int = 1) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document.lower().replace(" ", "-"),
        "document_name": document,
        "page": page,
        "text": text,
        "score": 0.9,
    }


TRANSFORMER_CHUNKS = [
    chunk(
        "t1",
        "Attention Paper",
        "The transformer architecture relies on self attention to process sequences in "
        "parallel. It reports faster training than recurrent baselines on the same data. "
        "A limitation is that memory grows quadratically with sequence length.",
    ),
    chunk(
        "t2",
        "Attention Paper",
        "Query, key and value projections let the model weigh every position at once.",
        page=2,
    ),
]

RAG_CHUNKS = [
    chunk(
        "r1",
        "RAG Paper",
        "Retrieval augmented generation grounds answers in retrieved passages and reduces "
        "hallucination. It evaluates on open domain question answering benchmarks. "
        "However, retrieval quality remains the dominant failure mode.",
    ),
    chunk(
        "r2",
        "RAG Paper",
        "Dense vector similarity search selects passages before the generator runs.",
        page=3,
    ),
]


def make_ctx(chunks: list[dict], question: str = "compare these papers") -> AgentContext:
    return AgentContext(
        question=question,
        project_id="p1",
        retrieved_chunks=list(chunks),
    )


# ---------------------------------------------------------------------------
# Evidence helper
# ---------------------------------------------------------------------------
class TestEvidenceLinking:
    def test_sources_are_grouped_per_document_with_stable_keys(self):
        sources = group_sources(TRANSFORMER_CHUNKS + RAG_CHUNKS)
        assert [s.key for s in sources] == ["S1", "S2"]
        assert sources[0].document_name == "Attention Paper"
        assert len(sources[0].chunks) == 2

    def test_render_sources_labels_blocks_for_the_model(self):
        rendered = render_sources(group_sources(TRANSFORMER_CHUNKS))
        assert "--- S1 | Attention Paper ---" in rendered

    def test_citation_points_at_the_passage_that_supports_the_claim(self):
        citation = citation_for(
            "query key and value projections weigh every position", TRANSFORMER_CHUNKS
        )
        assert citation is not None
        assert citation["chunk_id"] == "t2"
        assert citation["page"] == 2

    def test_unsupported_claim_gets_no_citation(self):
        assert citation_for("quantum annealing schedules", TRANSFORMER_CHUNKS) is None


# ---------------------------------------------------------------------------
# Regressions — each of these reproduces a bug found in the audit pass
# ---------------------------------------------------------------------------
class TestRegressions:
    def test_chunk_count_is_scoped_to_one_project(self, client, sample_pdf):
        """Every project used to report the whole collection's chunk count."""
        first = client.post("/api/projects", json={"name": "First"}).json()["id"]
        second = client.post("/api/projects", json={"name": "Second"}).json()["id"]

        with open(sample_pdf, "rb") as handle:
            client.post(
                f"/api/projects/{first}/documents",
                files={"file": ("a.pdf", handle, "application/pdf")},
            )

        first_chunks = client.get(f"/api/projects/{first}/stats").json()["chunks"]
        second_chunks = client.get(f"/api/projects/{second}/stats").json()["chunks"]

        assert first_chunks > 0
        assert second_chunks == 0, "an empty project must not report another project's chunks"

    def test_patent_concepts_keep_their_frequency_ranking(self):
        """A sort-then-truncate used to discard the ranking alphabetically."""
        from services.agents.patent_awareness import MAX_CONCEPTS, PatentAwarenessAgent

        # "zebra" is the most frequent term; dozens of 'a'-words outrank it
        # alphabetically and used to push it out of the truncated list.
        filler = " ".join(f"alpha{i:03d}" for i in range(MAX_CONCEPTS * 2))
        ctx = make_ctx([chunk("c1", "Doc", f"zebra zebra zebra zebra {filler}")])

        concepts = PatentAwarenessAgent._project_concepts(ctx)

        assert len(concepts) <= MAX_CONCEPTS
        assert "zebra" in concepts, "the most frequent term must survive truncation"

    def test_drawing_an_edge_does_not_inflate_mention_counts(self, tmp_path):
        """`mentions` must mean "the corpus said this", not "code touched it"."""
        from services.knowledge_graph.networkx_store import kg_store

        kg_store.reset()
        kg_store._base_dir = tmp_path
        graph = kg_store.for_project("p1")

        graph.add_entity("Sparse Attention", "Method")  # mentioned once
        for _ in range(5):
            graph.add_relation("Some Paper", "PART_OF", "Sparse Attention")

        assert graph.graph.nodes["Sparse Attention"]["mentions"] == 1
        # A genuine second mention still counts.
        graph.add_entity("Sparse Attention", "Method")
        assert graph.graph.nodes["Sparse Attention"]["mentions"] == 2

        kg_store.reset()

    def test_thin_coverage_signal_survives_relation_building(self, tmp_path):
        """The inflated counter used to hide under-represented concepts."""
        from services.knowledge_graph.networkx_store import kg_store

        kg_store.reset()
        kg_store._base_dir = tmp_path
        graph = kg_store.for_project("p1")
        graph.add_entity("Curriculum Pretraining", "Concept")
        graph.add_relation("Paper A", "PART_OF", "Curriculum Pretraining")

        signals = GapDetectionAgent._graph_signals("p1")
        thin = next(s for s in signals if s["signal"] == "under_represented_concepts")

        assert "Curriculum Pretraining" in thin["entities"]
        kg_store.reset()

    @pytest.mark.asyncio
    async def test_papers_link_only_to_concepts_from_the_same_run(self, tmp_path):
        """Paper→concept edges used to be taken from the tail of the node list."""
        from services.agents.kg_agent import KnowledgeGraphAgent
        from services.knowledge_graph.networkx_store import kg_store

        kg_store.reset()
        kg_store._base_dir = tmp_path
        graph = kg_store.for_project("p1")
        graph.add_entity("Unrelated Legacy Concept", "Concept")

        ctx = make_ctx(TRANSFORMER_CHUNKS, "index this paper")
        ctx.project_id = "p1"
        ctx.intermediate_results["retrieved_papers"] = [
            {"id": "1", "title": "Fresh Paper", "authors": ["A Author"], "url": ""}
        ]

        await KnowledgeGraphAgent(llm=OfflineChatModel()).run(ctx)

        linked = {
            target
            for source, target, data in graph.graph.edges(data=True)
            if source == "Fresh Paper" and data.get("relation") == "PART_OF"
        }
        assert "Unrelated Legacy Concept" not in linked

        kg_store.reset()

    def test_every_flow_is_reachable_from_natural_language(self):
        """Five flows used to be unreachable unless the caller forced them."""
        cases = {
            "what gaps remain in this literature?": "gaps",
            "what hypotheses should we try next?": "hypothesis",
            "how would we test that claim?": "experiment",
            "is there any patent overlap here?": "patent",
            "compare these two papers": "compare",
            "what is self attention?": "answer",
            "find papers on graph neural networks": "search",
        }
        for question, expected in cases.items():
            flow, _reason = RouterAgent.heuristic(question, has_document=False, doc_count=3)
            assert flow == expected, f"{question!r} routed to {flow}, expected {expected}"

    def test_research_flows_need_an_indexed_library(self):
        """With nothing indexed, the useful answer is to go find papers."""
        for question in ("what gaps remain?", "how would we test this?", "patent overlap?"):
            flow, _reason = RouterAgent.heuristic(question, has_document=False, doc_count=0)
            assert flow == "search"

    def test_offline_router_matches_the_heuristic_ordering(self):
        model = OfflineChatModel()
        assert '"flow": "experiment"' in model._route("User request: how would we test this?")
        assert '"flow": "gaps"' in model._route("User request: what gaps remain?")
        assert '"flow": "patent"' in model._route("User request: check prior art please")

    def test_query_router_uses_the_shared_response_schema(self):
        """The router used to redeclare the models the schema package owns."""
        import schemas
        from app.routers import query as query_router

        assert query_router.RetrievalResult is schemas.RetrievalResult
        assert query_router.RetrievalResponse is schemas.RetrievalResponse


# ---------------------------------------------------------------------------
# Flow registration
# ---------------------------------------------------------------------------
class TestFlowRegistration:
    def test_compare_flow_is_registered_with_a_description(self):
        assert FLOWS["compare"] == ["retriever", "comparison", "citation", "synthesis"]
        assert FLOW_DESCRIPTIONS["compare"]

    def test_every_flow_has_a_description(self):
        assert set(FLOW_DESCRIPTIONS) == set(FLOWS)

    def test_router_heuristic_picks_compare_for_a_contrast_request(self):
        flow, _reason = RouterAgent.heuristic(
            "How does RAG differ from a purely parametric model?",
            has_document=False,
            doc_count=3,
        )
        assert flow == "compare"

    def test_compare_needs_a_library_to_compare(self):
        # With nothing indexed there is nothing to contrast — search first.
        flow, _reason = RouterAgent.heuristic(
            "compare these two approaches", has_document=False, doc_count=0
        )
        assert flow == "search"

    def test_offline_model_routes_comparison_requests(self):
        raw = OfflineChatModel()._route("User request: compare BERT versus GPT")
        assert '"flow": "compare"' in raw


# ---------------------------------------------------------------------------
# Comparison agent
# ---------------------------------------------------------------------------
class TestComparisonAgent:
    @pytest.mark.asyncio
    async def test_builds_a_table_with_a_citation_in_every_cell(self):
        agent = ComparisonAgent(llm=OfflineChatModel())
        ctx = await agent.run(make_ctx(TRANSFORMER_CHUNKS + RAG_CHUNKS))

        comparison = ctx.intermediate_results["comparison"]
        assert len(comparison["sources"]) == 2
        assert comparison["rows"], "offline comparison must still produce rows"

        for row in comparison["rows"]:
            assert row["dimension"]
            for cell in row["cells"]:
                assert cell["value"]
                assert cell["citation"] is not None
                assert cell["citation"]["document_name"] == cell["document_name"]
                assert cell["citation"]["chunk_id"]

    @pytest.mark.asyncio
    async def test_drops_cells_no_passage_supports(self):
        agent = ComparisonAgent(llm=OfflineChatModel())
        sources = {s.key: s for s in group_sources(TRANSFORMER_CHUNKS + RAG_CHUNKS)}

        rows, dropped = agent._cite_cells(
            [
                {
                    "dimension": "Invented",
                    "cells": [
                        {"source_key": "S1", "value": "quantum annealing on trapped ions"},
                        {"source_key": "S9", "value": "from a source that does not exist"},
                        {"source_key": "S2", "value": "retrieval reduces hallucination"},
                    ],
                }
            ],
            sources,
        )

        assert dropped == 2
        assert len(rows) == 1
        assert [cell["source_key"] for cell in rows[0]["cells"]] == ["S2"]

    @pytest.mark.asyncio
    async def test_single_source_reports_why_it_cannot_compare(self):
        agent = ComparisonAgent(llm=OfflineChatModel())
        ctx = await agent.run(make_ctx(TRANSFORMER_CHUNKS))

        comparison = ctx.intermediate_results["comparison"]
        assert comparison["rows"] == []
        assert "at least two distinct documents" in comparison["note"]

    @pytest.mark.asyncio
    async def test_failure_is_contained_by_safe_run(self):
        class Exploding(OfflineChatModel):
            def _call(self, *args, **kwargs):
                raise RuntimeError("model unavailable")

        agent = ComparisonAgent(llm=Exploding())
        ctx = await agent.safe_run(make_ctx(TRANSFORMER_CHUNKS + RAG_CHUNKS))

        assert ctx.intermediate_results["errors"][0]["agent"] == "comparison"


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------
class FixedResponseModel(OfflineChatModel):
    """Offline model that returns one canned payload — for validation tests."""

    payload: str = "{}"

    def _call(self, *args, **kwargs):  # noqa: D102 - see base class
        return self.payload


class TestGapDetectionAgent:
    @pytest.mark.asyncio
    async def test_reports_gaps_quoted_from_the_passages(self):
        agent = GapDetectionAgent(llm=OfflineChatModel())
        ctx = await agent.run(
            make_ctx(TRANSFORMER_CHUNKS + RAG_CHUNKS, "what is missing in this work?")
        )

        result = ctx.intermediate_results["gaps"]
        assert result["gaps"], "the offline model surfaces stated limitations"
        for gap in result["gaps"]:
            assert gap["citation"] is not None
            assert gap["citation"]["chunk_id"]
            assert gap["evidence_quote"]
            assert gap["kind"] in {"stated_limitation", "future_work", "open_question"}

    @pytest.mark.asyncio
    async def test_gap_without_a_locatable_quote_is_dropped(self):
        model = FixedResponseModel()
        model.payload = (
            '{"gaps": [{"gap": "Nobody has tried trapped-ion quantum annealing here.",'
            ' "evidence_quote": "trapped ion annealing schedules were never evaluated",'
            ' "source_key": "S1", "kind": "open_question"}]}'
        )

        ctx = await GapDetectionAgent(llm=model).run(make_ctx(TRANSFORMER_CHUNKS))
        result = ctx.intermediate_results["gaps"]

        assert result["gaps"] == []
        assert result["uncited_gaps_dropped"] == 1
        assert "could be tied to a quotable sentence" in result["note"]

    @pytest.mark.asyncio
    async def test_gap_with_a_mislabelled_source_is_still_kept_if_quotable(self):
        model = FixedResponseModel()
        model.payload = (
            '{"gaps": [{"gap": "Memory cost limits long sequences.",'
            ' "evidence_quote": "memory grows quadratically with sequence length",'
            ' "source_key": "S7", "kind": "stated_limitation"}]}'
        )

        ctx = await GapDetectionAgent(llm=model).run(make_ctx(TRANSFORMER_CHUNKS))
        gaps = ctx.intermediate_results["gaps"]["gaps"]

        assert len(gaps) == 1
        assert gaps[0]["citation"]["document_name"] == "Attention Paper"

    @pytest.mark.asyncio
    async def test_no_passages_means_no_gaps_and_an_explanation(self):
        ctx = await GapDetectionAgent(llm=OfflineChatModel()).run(make_ctx([]))
        result = ctx.intermediate_results["gaps"]

        assert result["gaps"] == []
        assert "No passages were retrieved" in result["note"]

    def test_graph_signals_flag_thin_coverage_and_uncompared_methods(self, tmp_path):
        from services.knowledge_graph.networkx_store import kg_store

        kg_store.reset()
        kg_store._base_dir = tmp_path
        graph = kg_store.for_project("p1")
        graph.add_entity("Sparse Attention", "Method")
        graph.add_entity("Dense Retrieval", "Method")
        graph.add_entity("Curriculum Pretraining", "Concept")  # mentioned once

        signals = GapDetectionAgent._graph_signals("p1")
        kinds = {signal["signal"] for signal in signals}

        assert "under_represented_concepts" in kinds
        assert "uncompared_methods" in kinds
        uncompared = next(s for s in signals if s["signal"] == "uncompared_methods")
        assert "Dense Retrieval vs Sparse Attention" in uncompared["entities"]

        kg_store.reset()

    def test_graph_signals_are_empty_without_a_graph(self):
        assert GapDetectionAgent._graph_signals(None) == []


# ---------------------------------------------------------------------------
# Hypothesis generation
# ---------------------------------------------------------------------------
EVIDENCED_GAPS = {
    "gaps": [
        {
            "id": "GAP1",
            "gap": "Memory cost limits long sequences.",
            "kind": "stated_limitation",
            "source_document": "Attention Paper",
            "evidence_quote": "memory grows quadratically with sequence length",
            "citation": {
                "chunk_id": "t1",
                "document_id": "attention-paper",
                "document_name": "Attention Paper",
                "page": 1,
                "quote": "memory grows quadratically with sequence length",
            },
        }
    ],
    "graph_signals": [],
}


class TestHypothesisAgent:
    @pytest.mark.asyncio
    async def test_hypotheses_inherit_the_citation_of_their_gap(self):
        ctx = make_ctx(TRANSFORMER_CHUNKS, "what should we try next?")
        ctx.intermediate_results["gaps"] = EVIDENCED_GAPS

        ctx = await HypothesisAgent(llm=OfflineChatModel()).run(ctx)
        hypotheses = ctx.intermediate_results["hypotheses"]["hypotheses"]

        assert hypotheses
        for hypothesis in hypotheses:
            assert hypothesis["statement"]
            assert hypothesis["testable_prediction"], "a hypothesis must be falsifiable"
            assert hypothesis["grounded_in_gap"] == "GAP1"
            assert hypothesis["citation"]["chunk_id"] == "t1"

    @pytest.mark.asyncio
    async def test_no_gaps_means_no_hypotheses(self):
        ctx = await HypothesisAgent(llm=OfflineChatModel()).run(make_ctx(TRANSFORMER_CHUNKS))
        result = ctx.intermediate_results["hypotheses"]

        assert result["hypotheses"] == []
        assert "only proposed on top of a gap" in result["note"]

    @pytest.mark.asyncio
    async def test_hypothesis_attached_to_no_real_gap_is_dropped(self):
        model = FixedResponseModel()
        model.payload = (
            '{"hypotheses": ['
            '{"statement": "Attached to nothing.", "testable_prediction": "p", "gap_index": 7},'
            '{"statement": "No prediction given.", "testable_prediction": "", "gap_index": 0},'
            '{"statement": "Valid one.", "testable_prediction": "beats baseline", "gap_index": 0}'
            "]}"
        )

        ctx = make_ctx(TRANSFORMER_CHUNKS)
        ctx.intermediate_results["gaps"] = EVIDENCED_GAPS
        ctx = await HypothesisAgent(llm=model).run(ctx)

        result = ctx.intermediate_results["hypotheses"]
        assert [h["statement"] for h in result["hypotheses"]] == ["Valid one."]
        assert result["unattached_dropped"] == 2


# ---------------------------------------------------------------------------
# Experiment design
# ---------------------------------------------------------------------------
GENERATED_HYPOTHESES = {
    "hypotheses": [
        {
            "id": "HYP1",
            "statement": "Sparse attention keeps accuracy while cutting memory on long inputs.",
            "testable_prediction": "Matches dense attention within 1 point at half the memory.",
            "grounded_in_gap": "GAP1",
            "gap_text": "Memory cost limits long sequences.",
            "citation": {"chunk_id": "t1", "document_name": "Attention Paper", "page": 1, "quote": "…"},
        }
    ]
}


class TestExperimentAgent:
    @pytest.mark.asyncio
    async def test_design_is_attached_to_its_hypothesis(self):
        ctx = make_ctx(TRANSFORMER_CHUNKS, "how would we test that?")
        ctx.intermediate_results["hypotheses"] = GENERATED_HYPOTHESES

        ctx = await ExperimentAgent(llm=OfflineChatModel()).run(ctx)
        experiments = ctx.intermediate_results["experiments"]["experiments"]

        assert experiments
        design = experiments[0]
        assert design["hypothesis_id"] == "HYP1"
        assert design["objective"]
        assert design["metrics"], "a design must name the metric that decides it"
        assert len(design["procedure"]) >= 2
        assert design["threats_to_validity"]

    @pytest.mark.asyncio
    async def test_no_hypotheses_means_no_designs(self):
        ctx = await ExperimentAgent(llm=OfflineChatModel()).run(make_ctx(TRANSFORMER_CHUNKS))
        result = ctx.intermediate_results["experiments"]

        assert result["experiments"] == []
        assert "Run the hypothesis workflow first" in result["note"]

    @pytest.mark.asyncio
    async def test_design_without_metric_or_procedure_is_dropped(self):
        model = FixedResponseModel()
        model.payload = (
            '{"experiments": ['
            '{"hypothesis_index": 0, "objective": "No metric", "metrics": [], "procedure": ["a"]},'
            '{"hypothesis_index": 0, "objective": "No steps", "metrics": ["acc"], "procedure": []},'
            '{"hypothesis_index": 9, "objective": "Orphan", "metrics": ["acc"], "procedure": ["a"]},'
            '{"hypothesis_index": 0, "objective": "Complete", "metrics": ["accuracy"],'
            ' "procedure": ["run baseline", "run variant"], "threats_to_validity": ["seed noise"]}'
            "]}"
        )

        ctx = make_ctx(TRANSFORMER_CHUNKS)
        ctx.intermediate_results["hypotheses"] = GENERATED_HYPOTHESES
        ctx = await ExperimentAgent(llm=model).run(ctx)

        result = ctx.intermediate_results["experiments"]
        assert [design["objective"] for design in result["experiments"]] == ["Complete"]
        assert result["incomplete_dropped"] == 3


# ---------------------------------------------------------------------------
# Patent awareness — safety boundary first
# ---------------------------------------------------------------------------
class TestPatentSources:
    def test_public_registries_are_accepted(self):
        url, name = validate_public_url("https://patents.google.com/patent/US1234567B2/en")
        assert url.startswith("https://patents.google.com")
        assert name == "Google Patents"

    def test_www_prefix_is_tolerated(self):
        _url, name = validate_public_url("https://www.patents.google.com/patent/US1B2")
        assert name == "Google Patents"

    def test_arbitrary_hosts_are_rejected(self):
        with pytest.raises(PatentSourceError) as excinfo:
            validate_public_url("https://patents.example.com/secret")
        assert "not a recognised public patent registry" in str(excinfo.value)

    def test_non_http_schemes_are_rejected(self):
        for url in ("file:///etc/passwd", "ftp://patents.google.com/x"):
            with pytest.raises(PatentSourceError):
                validate_public_url(url)

    def test_internal_addresses_are_rejected(self):
        # The allowlist is what blocks SSRF-style targets; MAIROS also never
        # fetches, so these can only ever have been stored, not requested.
        for url in ("http://localhost:8000/admin", "http://169.254.169.254/latest/meta-data"):
            with pytest.raises(PatentSourceError):
                validate_public_url(url)

    def test_empty_url_is_valid_manual_entry(self):
        assert validate_public_url("") == ("", "manual entry")

    def test_source_description_states_that_nothing_is_fetched(self):
        described = describe_sources()
        assert described["fetches_documents"] is False
        assert described["disclaimer"] == DISCLAIMER
        assert any("never downloads" in note for note in described["notes"])


class TestPatentAwarenessAgent:
    @pytest.mark.asyncio
    async def test_no_patents_yields_a_disclaimer_and_an_explanation(self, client):
        project_id = client.post("/api/projects", json={"name": "Patents"}).json()["id"]

        ctx = make_ctx(TRANSFORMER_CHUNKS)
        ctx.project_id = project_id
        ctx = await PatentAwarenessAgent(llm=OfflineChatModel()).run(ctx)

        result = ctx.intermediate_results["patent_awareness"]
        assert result["disclaimer"] == DISCLAIMER
        assert result["overlaps"] == []
        assert "never downloads patent documents" in result["note"]

    @pytest.mark.asyncio
    async def test_overlaps_are_literal_matches_with_a_citation(self, client):
        project_id = client.post("/api/projects", json={"name": "Patents"}).json()["id"]
        client.post(
            f"/api/projects/{project_id}/patents",
            json={
                "title": "Parallel sequence processing apparatus",
                "text": "A system using self attention to process a sequence in parallel.",
                "url": "https://patents.google.com/patent/US1234567B2/en",
            },
        )

        ctx = make_ctx(TRANSFORMER_CHUNKS)
        ctx.project_id = project_id
        ctx = await PatentAwarenessAgent(llm=OfflineChatModel()).run(ctx)

        result = ctx.intermediate_results["patent_awareness"]
        assert result["patents_checked"] == 1
        assert result["overlaps"], "a shared term must be reported"

        for overlap in result["overlaps"]:
            # Every reported term really is present in the patent text.
            assert overlap["concept"].lower() in (
                "a system using self attention to process a sequence in parallel."
            )
            assert overlap["patent_title"]
        assert result["disclaimer"] == DISCLAIMER

    @pytest.mark.asyncio
    async def test_absence_of_overlap_is_not_reported_as_clearance(self, client):
        project_id = client.post("/api/projects", json={"name": "Patents"}).json()["id"]
        client.post(
            f"/api/projects/{project_id}/patents",
            json={"title": "Unrelated", "text": "A brake caliper for bicycles."},
        )

        ctx = make_ctx(TRANSFORMER_CHUNKS)
        ctx.project_id = project_id
        ctx = await PatentAwarenessAgent(llm=OfflineChatModel()).run(ctx)

        result = ctx.intermediate_results["patent_awareness"]
        assert result["overlaps"] == []
        assert "not a legal clearance" in result["note"]

    @pytest.mark.asyncio
    async def test_a_model_cannot_invent_an_overlap(self, client):
        """Findings are computed; the LLM only phrases the summary."""
        project_id = client.post("/api/projects", json={"name": "Patents"}).json()["id"]
        client.post(
            f"/api/projects/{project_id}/patents",
            json={"title": "Unrelated", "text": "A brake caliper for bicycles."},
        )

        model = FixedResponseModel()
        model.payload = (
            '{"overlaps": [{"concept": "self attention", "overlap": "fabricated"}],'
            ' "summary": "invented"}'
        )

        ctx = make_ctx(TRANSFORMER_CHUNKS)
        ctx.project_id = project_id
        ctx = await PatentAwarenessAgent(llm=model).run(ctx)

        assert ctx.intermediate_results["patent_awareness"]["overlaps"] == []


class TestPatentAPI:
    def test_sources_endpoint_lists_the_allowlist(self, client):
        payload = client.get("/api/patents/sources").json()
        domains = {source["domain"] for source in payload["sources"]}
        assert "patents.google.com" in domains
        assert payload["disclaimer"] == DISCLAIMER

    def test_add_and_list_a_patent(self, client):
        project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]
        created = client.post(
            f"/api/projects/{project_id}/patents",
            json={
                "title": "Retrieval apparatus",
                "number": "US1234567B2",
                "text": "dense retrieval over an embedding index",
                "url": "https://patents.google.com/patent/US1234567B2/en",
            },
        )
        assert created.status_code == 201
        assert created.json()["source"] == "Google Patents"

        listed = client.get(f"/api/projects/{project_id}/patents").json()
        assert listed["disclaimer"] == DISCLAIMER
        assert len(listed["patents"]) == 1

    def test_disallowed_url_is_rejected_with_guidance(self, client):
        project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]
        response = client.post(
            f"/api/projects/{project_id}/patents",
            json={"title": "X", "text": "y", "url": "https://evil.example.com/p"},
        )
        assert response.status_code == 400
        assert "public patent registry" in response.json()["detail"]

    def test_empty_submission_is_rejected(self, client):
        project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]
        response = client.post(
            f"/api/projects/{project_id}/patents", json={"title": "X"}
        )
        assert response.status_code == 400

    def test_patent_can_be_deleted(self, client):
        project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]
        patent_id = client.post(
            f"/api/projects/{project_id}/patents",
            json={"title": "X", "text": "some text"},
        ).json()["id"]

        assert client.delete(f"/api/projects/{project_id}/patents/{patent_id}").status_code == 204
        assert client.get(f"/api/projects/{project_id}/patents").json()["patents"] == []

    def test_patent_flow_runs_end_to_end_with_the_disclaimer(self, client, sample_pdf):
        project_id = client.post("/api/projects", json={"name": "PatentFlow"}).json()["id"]
        with open(sample_pdf, "rb") as handle:
            client.post(
                f"/api/projects/{project_id}/documents",
                files={"file": ("paper.pdf", handle, "application/pdf")},
            )
        client.post(
            f"/api/projects/{project_id}/patents",
            json={
                "title": "Attention apparatus",
                "text": "self attention computes query key and value projections in parallel",
            },
        )

        task = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "any patent overlap here?", "flow": "patent"},
        ).json()

        result = client.get(f"/api/tasks/{task['id']}").json()
        assert result["status"] == "completed"

        awareness = result["result"]["patent_awareness"]
        assert awareness["disclaimer"] == DISCLAIMER
        assert awareness["patents_checked"] == 1

        agents = {event["agent_name"] for event in result["events"]}
        assert "patent_awareness" in agents

    def test_supplied_patent_appears_in_the_knowledge_graph(self, client, sample_pdf):
        project_id = client.post("/api/projects", json={"name": "PatentGraph"}).json()["id"]
        with open(sample_pdf, "rb") as handle:
            client.post(
                f"/api/projects/{project_id}/documents",
                files={"file": ("paper.pdf", handle, "application/pdf")},
            )
        client.post(
            f"/api/projects/{project_id}/patents",
            json={
                "title": "Parallel attention apparatus",
                "text": "self attention computes query key and value projections in parallel",
            },
        )
        client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "check patent overlap", "flow": "patent"},
        )

        graph = client.get(f"/api/projects/{project_id}/graph").json()
        patent_nodes = [node for node in graph["nodes"] if node["group"] == "Patent"]
        assert patent_nodes, "a supplied patent must show up in the graph as a Patent node"
        assert patent_nodes[0]["name"] == "Parallel attention apparatus"


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------
class TestWorkflowAPI:
    def test_flows_endpoint_mirrors_the_registry(self, client):
        payload = client.get("/api/flows").json()
        names = {flow["name"] for flow in payload["flows"]}
        assert names == set(FLOWS)
        assert all(flow["description"] for flow in payload["flows"])

    def test_task_rejects_an_unregistered_flow(self, client):
        project_id = client.post("/api/projects", json={"name": "Flows"}).json()["id"]
        response = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "x", "flow": "teleport"},
        )
        assert response.status_code == 400
        assert "compare" in response.json()["detail"]

    def test_compare_flow_runs_end_to_end_and_returns_a_cited_table(
        self, client, sample_pdf
    ):
        project_id = client.post("/api/projects", json={"name": "Compare"}).json()["id"]
        with open(sample_pdf, "rb") as handle:
            client.post(
                f"/api/projects/{project_id}/documents",
                files={"file": ("first.pdf", handle, "application/pdf")},
            )
        with open(sample_pdf, "rb") as handle:
            client.post(
                f"/api/projects/{project_id}/documents",
                files={"file": ("second.pdf", handle, "application/pdf")},
            )

        task = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "compare these two papers", "flow": "compare"},
        ).json()

        result = client.get(f"/api/tasks/{task['id']}").json()
        assert result["status"] == "completed"
        assert result["result"]["comparison"] is not None

        comparison = result["result"]["comparison"]
        assert len(comparison["sources"]) >= 2
        for row in comparison["rows"]:
            for cell in row["cells"]:
                assert cell["citation"]["chunk_id"]

        # The trace must show the comparison agent actually ran.
        assert any(event["agent_name"] == "comparison" for event in result["events"])

    def test_gaps_flow_runs_end_to_end_and_emits_events(self, client, sample_pdf):
        project_id = client.post("/api/projects", json={"name": "Gaps"}).json()["id"]
        with open(sample_pdf, "rb") as handle:
            client.post(
                f"/api/projects/{project_id}/documents",
                files={"file": ("paper.pdf", handle, "application/pdf")},
            )

        task = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "what gaps remain in this work?", "flow": "gaps"},
        ).json()

        result = client.get(f"/api/tasks/{task['id']}").json()
        assert result["status"] == "completed"

        gaps = result["result"]["gaps"]
        assert gaps is not None
        assert isinstance(gaps["graph_signals"], list)
        for gap in gaps["gaps"]:
            assert gap["citation"]["chunk_id"], "every reported gap must cite a passage"

        # Real events, not a simulated progress bar.
        agents = {event["agent_name"] for event in result["events"]}
        assert "gaps" in agents

    def test_hypothesis_flow_chains_gaps_into_hypotheses(self, client, sample_pdf):
        project_id = client.post("/api/projects", json={"name": "Hypotheses"}).json()["id"]
        with open(sample_pdf, "rb") as handle:
            client.post(
                f"/api/projects/{project_id}/documents",
                files={"file": ("paper.pdf", handle, "application/pdf")},
            )

        task = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "what should we investigate next?", "flow": "hypothesis"},
        ).json()

        result = client.get(f"/api/tasks/{task['id']}").json()
        assert result["status"] == "completed"
        assert result["result"]["gaps"] is not None
        assert result["result"]["hypotheses"] is not None

        for hypothesis in result["result"]["hypotheses"]["hypotheses"]:
            assert hypothesis["grounded_in_gap"]
            assert hypothesis["citation"] is not None

        agents = {event["agent_name"] for event in result["events"]}
        assert {"gaps", "hypothesis"} <= agents

    def test_experiment_flow_runs_the_whole_chain(self, client, sample_pdf):
        project_id = client.post("/api/projects", json={"name": "Experiments"}).json()["id"]
        with open(sample_pdf, "rb") as handle:
            client.post(
                f"/api/projects/{project_id}/documents",
                files={"file": ("paper.pdf", handle, "application/pdf")},
            )

        task = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "how would we test the open problems?", "flow": "experiment"},
        ).json()

        result = client.get(f"/api/tasks/{task['id']}").json()
        assert result["status"] == "completed"
        assert result["result"]["experiments"] is not None

        for design in result["result"]["experiments"]["experiments"]:
            assert design["hypothesis_id"]
            assert design["metrics"]
            assert design["procedure"]

        agents = {event["agent_name"] for event in result["events"]}
        assert {"gaps", "hypothesis", "experiment"} <= agents
