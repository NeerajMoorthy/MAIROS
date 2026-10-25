"""Novelty agent and the `review` flow.

The point of these tests is the boundary the agent exists to hold: it may say
what is already covered by the project's own sources, and it may never say
anything is new in the field. Several tests below assert the absence of that
claim rather than the presence of a feature, which is deliberate — a
regression here would be a system quietly overclaiming, and nothing else in
the suite would catch it.
"""

from __future__ import annotations

import pytest

from services.agents.base import AgentContext
from services.agents.hypothesis import HypothesisAgent
from services.agents.novelty import (
    COVERED_THRESHOLD,
    FIELD_NOVELTY,
    NoveltyAgent,
    VERDICT_LABELS,
)
from services.agents.router import FLOW_DESCRIPTIONS, FLOWS, RouterAgent
from services.generation.provider import OfflineChatModel


def chunk(chunk_id: str, document: str, text: str, page: int = 1) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document.lower().replace(" ", "-"),
        "document_name": document,
        "page": page,
        "text": text,
        "score": 0.9,
    }


CORPUS = [
    chunk(
        "c1",
        "Attention Paper",
        "The transformer architecture relies on self attention to process sequences in "
        "parallel, which reports faster training than recurrent baselines on the same "
        "hardware. Memory grows quadratically with sequence length.",
    ),
    chunk(
        "c2",
        "RAG Paper",
        "Retrieval augmented generation grounds answers in retrieved passages and "
        "reduces hallucination on open domain question answering benchmarks.",
    ),
]


def make_ctx(question: str, chunks=None, **results) -> AgentContext:
    ctx = AgentContext(
        question=question,
        project_id="p1",
        retrieved_chunks=list(CORPUS if chunks is None else chunks),
    )
    ctx.intermediate_results.update(results)
    return ctx


async def assess(ctx: AgentContext, llm=None) -> dict:
    agent = NoveltyAgent(llm=llm if llm is not None else OfflineChatModel())
    await agent.run(ctx)
    return ctx.intermediate_results["novelty"]


# ---------------------------------------------------------------------------
# The claim the agent must never make
# ---------------------------------------------------------------------------
class TestFieldNoveltyIsNeverClaimed:
    @pytest.mark.asyncio
    async def test_every_assessment_reports_field_novelty_as_not_assessed(self):
        report = await assess(
            make_ctx("is this idea novel: self attention for protein folding")
        )
        assert report["field_novelty"] == FIELD_NOVELTY == "not_assessed"
        for assessment in report["assessments"]:
            assert assessment["field_novelty"] == "not_assessed"

    @pytest.mark.asyncio
    async def test_a_claim_absent_from_the_corpus_is_not_called_novel(self):
        """The interesting case: nothing matched, and it still must not overclaim."""
        report = await assess(
            make_ctx("quantum annealing schedules for ribosome kinetics", chunks=CORPUS)
        )
        assessment = report["assessments"][0]

        assert assessment["verdict"] == "not_found_in_corpus"
        # The wording is about the corpus, never about the field.
        assert "this project" in assessment["verdict_label"].lower()
        assert assessment["field_novelty"] == "not_assessed"

        rendered = str(report).lower()
        for overclaim in ("is novel", "is new in the field", "no prior work exists"):
            assert overclaim not in rendered

    @pytest.mark.asyncio
    async def test_the_reason_names_exactly_what_was_searched(self):
        ctx = make_ctx("is this new", retrieved_papers=[{"title": "A"}, {"title": "B"}])
        report = await assess(ctx)
        reason = report["assessments"][0]["field_novelty_reason"]

        assert "2 document(s) already in this project" in reason
        assert "systematic search" in reason

    @pytest.mark.asyncio
    async def test_fetched_abstracts_are_not_counted_twice_as_project_documents(self):
        """The `review` flow indexes arXiv abstracts and retrieves them straight back.

        Counting them both as "documents from this project" and as "abstracts
        from arXiv" described one corpus as two — and on a project with no
        uploads it presented "absent from one arXiv query run moments ago" as a
        statement about the user's own library.
        """
        fetched = [
            {
                "chunk_id": "a1",
                "document_id": "arxiv_2401.00001",
                "document_name": "A Fetched Paper",
                "page": 1,
                "text": "Retrieval augmented generation grounds answers in passages.",
                "score": 0.9,
            }
        ]
        ctx = make_ctx(
            "retrieval augmented generation",
            chunks=CORPUS + fetched,
            retrieved_papers=[{"title": "A Fetched Paper"}],
        )
        report = await assess(ctx)

        assert "2 document(s) already in this project" in report["scope"]
        assert "1 abstract(s) fetched from arXiv during this run" in report["scope"]
        # And the total is right: three sources, described once each.
        assert report["scope"].count("document(s)") == 1

    @pytest.mark.asyncio
    async def test_a_review_with_no_uploads_does_not_call_arxiv_results_the_users_library(self):
        fetched = [
            {
                "chunk_id": "a1",
                "document_id": "arxiv_2401.00001",
                "document_name": "A Fetched Paper",
                "page": 1,
                "text": "Retrieval augmented generation grounds answers in passages.",
                "score": 0.9,
            }
        ]
        report = await assess(
            make_ctx("anything", chunks=fetched, retrieved_papers=[{"title": "A"}])
        )

        assert "already in this project" not in report["scope"]
        assert "fetched from arXiv during this run" in report["scope"]

    @pytest.mark.asyncio
    async def test_limits_paragraph_spells_out_what_not_found_does_not_mean(self):
        report = await assess(make_ctx("is this new"))
        assert "not a finding of originality" in report["limits"]


# ---------------------------------------------------------------------------
# Corpus coverage — the claim the agent may make
# ---------------------------------------------------------------------------
class TestCorpusCoverage:
    @pytest.mark.asyncio
    async def test_a_claim_restating_the_corpus_is_marked_covered_and_cited(self):
        report = await assess(
            make_ctx(
                "self attention processes sequences in parallel and reports faster "
                "training than recurrent baselines"
            )
        )
        assessment = report["assessments"][0]

        assert assessment["verdict"] == "covered_in_corpus"
        assert assessment["corpus_overlap"] >= COVERED_THRESHOLD
        citation = assessment["nearest_prior_work"][0]["citation"]
        assert citation["document_name"] == "Attention Paper"
        assert "self attention" in citation["quote"]

    @pytest.mark.asyncio
    async def test_verdicts_are_computed_not_taken_from_the_model(self):
        """A model insisting everything is groundbreaking changes no verdict."""

        class Sycophant(OfflineChatModel):
            def _call(self, messages, stop=None, run_manager=None, **kwargs):
                return (
                    '{"related": [{"claim_index": 0, "source_key": "S1", '
                    '"note": "This claim is completely novel and unprecedented."}]}'
                )

        report = await assess(
            make_ctx(
                "self attention processes sequences in parallel and reports faster "
                "training than recurrent baselines"
            ),
            llm=Sycophant(),
        )
        assessment = report["assessments"][0]

        assert assessment["verdict"] == "covered_in_corpus"
        # And the unsupported note was dropped rather than displayed.
        assert report["uncited_notes_dropped"] == 1
        assert all(
            "unprecedented" not in entry["note"]
            for entry in assessment["nearest_prior_work"]
        )

    @pytest.mark.asyncio
    async def test_with_no_corpus_nothing_is_cited_and_scope_says_so(self):
        report = await assess(make_ctx("anything at all", chunks=[]))
        assessment = report["assessments"][0]

        assert report["scope"] == "no documents from this project"
        assert assessment["verdict"] == "not_found_in_corpus"
        assert assessment["nearest_prior_work"] == []
        assert assessment["field_novelty"] == "not_assessed"

    @pytest.mark.asyncio
    async def test_hypotheses_are_assessed_in_preference_to_the_question(self):
        ctx = make_ctx(
            "what should we try next?",
            # The shape HypothesisAgent stores, not a bare list.
            hypotheses={
                "hypotheses": [
                    {"statement": "Retrieval augmented generation reduces hallucination."},
                    {"statement": "Quantum annealing improves ribosome kinetics."},
                ]
            },
        )
        report = await assess(ctx)

        assert [a["origin"] for a in report["assessments"]] == ["hypothesis", "hypothesis"]
        assert report["assessments"][0]["verdict"] == "covered_in_corpus"
        assert report["assessments"][1]["verdict"] == "not_found_in_corpus"

    @pytest.mark.asyncio
    async def test_the_hypothesis_steps_own_output_is_what_gets_assessed(self):
        """Regression (walkthrough K1). The hypothesis step stores
        ``{"hypotheses": [...]}``; this step looked for a bare list, never found
        one, and scored the request "what hypotheses follow…?" as the claim.
        Chaining the real agents keeps both sides of that contract in one test.
        """
        ctx = make_ctx("What hypotheses follow from the gaps in this literature?")
        ctx.intermediate_results["gaps"] = {
            "gaps": [
                {
                    "id": "GAP1",
                    "gap": "Retrieval quality under paraphrased questions is not yet measured.",
                    "source_document": "RAG Paper",
                    "citation": {"chunk_id": "c1", "document_name": "RAG Paper", "page": 1},
                }
            ],
            "graph_signals": [],
        }
        await HypothesisAgent(llm=OfflineChatModel()).run(ctx)
        report = await assess(ctx)

        statements = [h["statement"] for h in ctx.intermediate_results["hypotheses"]["hypotheses"]]
        assert statements, "a quoted gap must yield a hypothesis"
        assert [a["claim"] for a in report["assessments"]] == statements
        assert {a["origin"] for a in report["assessments"]} == {"hypothesis"}

    @pytest.mark.asyncio
    async def test_a_hypothesis_step_that_proposed_nothing_leaves_the_request_unscored(self):
        ctx = make_ctx("What hypotheses follow from the gaps in this literature?")
        await HypothesisAgent(llm=OfflineChatModel()).run(ctx)  # no gaps, so no hypotheses
        report = await assess(ctx)

        assert report["assessments"] == []
        assert report["note"].startswith("No hypothesis was proposed")

    @pytest.mark.asyncio
    async def test_how_the_question_is_phrased_does_not_change_the_verdict(self):
        """The bias that mattered: verbose phrasing pushed a covered claim to "not found".

        The overlap ratio divides by the claim's own token count, so every word
        typed only to ask the question is a token the corpus can never match.
        Novelty requests are phrased that way by definition, and the drift runs
        towards the one verdict a reader takes as a novelty signal.
        """
        phrasings = [
            "self attention processes sequences in parallel",
            "Is self attention processing sequences in parallel novel?",
            "Is my idea that self attention processes sequences in parallel novel, "
            "or has anyone already done this before?",
            "Has anyone already published anything similar to my idea, which is that "
            "self attention processes sequences in parallel?",
        ]
        verdicts = []
        for phrasing in phrasings:
            report = await assess(make_ctx(phrasing))
            verdicts.append(report["assessments"][0]["verdict"])

        assert set(verdicts) == {"covered_in_corpus"}, dict(zip(phrasings, verdicts))

    @pytest.mark.asyncio
    async def test_a_short_claim_needs_real_evidence_not_just_a_high_ratio(self):
        """Four content words reach 0.75 on three incidental hits in a caption."""
        caption = [
            chunk(
                "cap",
                "Results Table",
                "Table 3 reports accuracy on the transformer baseline; see the "
                "appendix for the full protein assay accuracy breakdown.",
            )
        ]
        report = await assess(
            make_ctx("Transformer accuracy on protein assays", chunks=caption)
        )
        assessment = report["assessments"][0]

        assert assessment["corpus_overlap"] >= COVERED_THRESHOLD, "the ratio is high"
        assert assessment["matched_terms"] < 4, "but little actually matched"
        assert assessment["verdict"] != "covered_in_corpus"

    @pytest.mark.asyncio
    async def test_a_substantive_claim_with_real_overlap_is_still_covered(self):
        """The floor must not make the agent useless on genuine matches."""
        report = await assess(
            make_ctx(
                "self attention processes sequences in parallel with faster training "
                "than recurrent baselines"
            )
        )
        assessment = report["assessments"][0]

        assert assessment["verdict"] == "covered_in_corpus"
        assert assessment["matched_terms"] >= 4

    @pytest.mark.asyncio
    async def test_every_verdict_has_a_human_label(self):
        report = await assess(make_ctx("is this new"))
        for assessment in report["assessments"]:
            assert assessment["verdict_label"] == VERDICT_LABELS[assessment["verdict"]]

    @pytest.mark.asyncio
    async def test_a_failing_model_degrades_to_computed_coverage_only(self):
        class Broken(OfflineChatModel):
            def _call(self, messages, stop=None, run_manager=None, **kwargs):
                raise RuntimeError("provider down")

        ctx = make_ctx(
            "self attention processes sequences in parallel and reports faster "
            "training than recurrent baselines"
        )
        agent = NoveltyAgent(llm=Broken())
        await agent.safe_run(ctx)

        # safe_run recorded the failure; no novelty block was fabricated.
        assert ctx.intermediate_results["errors"][0]["agent"] == "novelty"
        assert "novelty" not in ctx.intermediate_results


# ---------------------------------------------------------------------------
# Flow registration
# ---------------------------------------------------------------------------
class TestReviewFlow:
    def test_review_chains_search_into_comparison_and_synthesis(self):
        agents = FLOWS["review"]
        assert agents[0] == "literature"
        assert agents[-1] == "synthesis"
        # The chain must keep this order to work at all.
        for earlier, later in (
            ("literature", "indexer"),
            ("indexer", "retriever"),
            ("retriever", "comparison"),
            ("comparison", "synthesis"),
        ):
            assert agents.index(earlier) < agents.index(later)

    def test_novelty_flow_retrieves_before_assessing(self):
        assert FLOWS["novelty"].index("retriever") < FLOWS["novelty"].index("novelty")

    def test_both_new_flows_are_described_for_the_ui(self):
        for flow in ("novelty", "review"):
            assert flow in FLOW_DESCRIPTIONS
            assert FLOW_DESCRIPTIONS[flow].strip()
        assert "never novelty in the field" in FLOW_DESCRIPTIONS["novelty"]

    def test_every_flow_still_names_only_registered_agents(self):
        from services.agents.orchestrator import AgentOrchestrator

        registry = set(AgentOrchestrator(llm=OfflineChatModel()).agents)
        for flow, agents in FLOWS.items():
            assert set(agents) <= registry, f"{flow} names an unregistered agent"

    ROUTING_CASES = [
        ("write a literature review of retrieval methods", "review"),
        ("survey the literature on attention", "review"),
        ("has this already been done before?", "novelty"),
        ("what is the novelty of this approach?", "novelty"),
        # Guards against the new hints swallowing the older flows.
        ("find papers on novel architectures", "search"),
        ("compare these two papers", "compare"),
        ("does this overlap any prior art?", "patent"),
        ("what gaps remain in this literature?", "gaps"),
        ("design experiments to test this", "experiment"),
        ("run an ablation study on the retriever", "experiment"),
        # Discovery intent must beat a subject-matter noun. Each of these used
        # to route into a research pipeline over the existing library, and only
        # once the project had documents — so the same request behaved
        # differently on day two than on day one.
        ("find recent papers on the Raft consensus protocol", "search"),
        ("papers on the MESI cache coherence protocol", "search"),
        ("literature on TLS 1.3 handshake protocol design", "search"),
        ("search for publications about ablation of attention heads", "search"),
        ("find papers on prior art search automation", "search"),
        # ...but an explicit comparison of what a search finds is still a compare.
        ("compare recent papers on retrieval augmented generation", "compare"),
    ]

    @pytest.mark.parametrize("question,expected", ROUTING_CASES)
    def test_heuristic_routing(self, question, expected):
        flow, _reason = RouterAgent.heuristic(question, has_document=False, doc_count=3)
        assert flow == expected

    @pytest.mark.parametrize("question,expected", ROUTING_CASES)
    def test_routing_is_the_same_on_an_empty_project_where_it_can_be(self, question, expected):
        """A discovery request must not depend on whether the library is empty."""
        flow, _reason = RouterAgent.heuristic(question, has_document=False, doc_count=0)
        if expected == "search":
            assert flow == "search"

    def test_the_run_method_counts_documents_not_chunks(self):
        """`doc_count` gates the research flows and is quoted to the model."""
        import asyncio

        ctx = AgentContext(question="anything", project_id="p1")
        # Six chunks, two documents. The old code passed 6.
        ctx.retrieved_chunks = [
            {"document_id": "d1", "text": "a"},
            {"document_id": "d1", "text": "b"},
            {"document_id": "d1", "text": "c"},
            {"document_id": "d2", "text": "d"},
            {"document_id": "d2", "text": "e"},
            {"document_id": "d2", "text": "f"},
        ]
        captured = {}
        agent = RouterAgent(llm=OfflineChatModel())
        original = agent.decide

        def spy(question, has_document=False, doc_count=0, forced_flow=None):
            captured["doc_count"] = doc_count
            return original(question, has_document, doc_count, forced_flow)

        agent.decide = spy
        asyncio.run(agent.run(ctx))
        assert captured["doc_count"] == 2

    def test_offline_router_agrees_with_the_heuristic(self):
        """The offline model's routing must not diverge from the fallback."""
        from services.common.json_utils import extract_json
        from services.agents.router import ROUTER_PROMPT

        model = OfflineChatModel()
        for question, _expected in self.ROUTING_CASES:
            raw = model.invoke(
                ROUTER_PROMPT.format(question=question, doc_count=3, doc_state="was not supplied")
            )
            offline_flow = extract_json(str(raw.content), default={})["flow"]
            heuristic_flow, _ = RouterAgent.heuristic(question, False, 3)
            assert offline_flow == heuristic_flow, question


# ---------------------------------------------------------------------------
# End-to-end through the real task pipeline
# ---------------------------------------------------------------------------
TRANSFORMER_PAGE = (
    "Transformers and Attention\n\n"
    "The transformer architecture relies on self attention to process sequences "
    "in parallel, reporting faster training than recurrent baselines. A stated "
    "limitation is that memory grows quadratically with sequence length."
)
RAG_PAGE = (
    "Retrieval-Augmented Generation\n\n"
    "Retrieval augmented generation grounds answers in retrieved passages and "
    "reduces hallucination. However, retrieval quality remains the dominant "
    "failure mode."
)


def _pdf_bytes(pages: list[str]) -> bytes:
    import fitz

    doc = fitz.open()
    for text in pages:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


class TestNoveltyThroughTheApi:
    def _project_with_corpus(self, client) -> str:
        import io

        project_id = client.post("/api/projects", json={"name": "Novelty"}).json()["id"]
        client.post(
            f"/api/projects/{project_id}/documents",
            files={
                "file": (
                    "paper.pdf",
                    io.BytesIO(_pdf_bytes([TRANSFORMER_PAGE, RAG_PAGE])),
                    "application/pdf",
                )
            },
        )
        return project_id

    def test_the_novelty_flow_completes_and_returns_a_scoped_report(self, client):
        project_id = self._project_with_corpus(client)

        created = client.post(
            f"/api/projects/{project_id}/tasks",
            json={
                "question": "Self attention processes sequences in parallel",
                "flow": "novelty",
            },
        )
        assert created.status_code == 201

        task = client.get(f"/api/tasks/{created.json()['id']}").json()
        assert task["status"] == "completed", task.get("error")

        report = task["result"]["novelty"]
        assert report is not None, "the novelty flow must populate the novelty field"
        assert report["field_novelty"] == "not_assessed"
        assert "this project" in report["scope"]
        assert report["assessments"][0]["verdict"] == "covered_in_corpus"

    def test_flows_endpoint_advertises_both_new_flows(self, client):
        names = {flow["name"] for flow in client.get("/api/flows").json()["flows"]}
        assert {"novelty", "review"} <= names

    def test_other_flows_leave_the_novelty_field_empty(self, client):
        """A new result field must not appear where its agent did not run."""
        project_id = self._project_with_corpus(client)

        created = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "How does RAG reduce hallucination?", "flow": "answer"},
        )
        task = client.get(f"/api/tasks/{created.json()['id']}").json()

        assert task["status"] == "completed", task.get("error")
        assert task["result"]["novelty"] is None


# ---------------------------------------------------------------------------
# The whole flow's prose, not just the agent's structured output
# ---------------------------------------------------------------------------
class TestTheAnswerTextNeverClaimsFieldNovelty:
    """The gap this class exists to close.

    `NoveltyAgent` was airtight about its own output while the `synthesis`
    agent that runs after it was still handed the user's raw question — so a
    perfectly obedient model asked "is this novel?" over passages that do not
    mention the idea would answer "none of these passages describe it, so it
    appears to be novel", cite a passage, and put that sentence in
    `final_answer`, which is the headline prose the UI shows above the hedged
    novelty card. Every assertion here is about `final_answer`.
    """

    OVERCLAIMS = (
        "is novel",
        "appears to be novel",
        "has not been done",
        "never been done",
        "no prior work",
        "unprecedented",
        "original contribution",
        "first to",
    )

    @staticmethod
    def _answer(client, project_id: str, question: str) -> str:
        created = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": question, "flow": "novelty"},
        )
        assert created.status_code == 201
        task = client.get(f"/api/tasks/{created.json()['id']}").json()
        assert task["status"] == "completed", task.get("error")
        return task["result"]["answer"]

    def _project(self, client) -> str:
        import io

        project_id = client.post("/api/projects", json={"name": "Answer text"}).json()["id"]
        client.post(
            f"/api/projects/{project_id}/documents",
            files={
                "file": (
                    "paper.pdf",
                    io.BytesIO(_pdf_bytes([TRANSFORMER_PAGE, RAG_PAGE])),
                    "application/pdf",
                )
            },
        )
        return project_id

    def test_the_answer_text_makes_no_novelty_claim_for_an_uncovered_idea(self, client):
        """The dangerous case: the corpus says nothing, and the prose must not fill the gap."""
        answer = self._answer(
            client,
            self._project(client),
            "Is my idea of using quantum annealing for ribosome kinetics novel?",
        ).lower()

        for overclaim in self.OVERCLAIMS:
            assert overclaim not in answer, f"answer claimed '{overclaim}': {answer[:400]}"

    def test_the_answer_states_its_scope_before_any_verdict(self, client):
        answer = self._answer(
            client, self._project(client), "Has self attention in parallel already been done?"
        )

        assert "Checked against" in answer
        assert "not an assessment of novelty in the field" in answer
        assert answer.index("Checked against") < answer.index("wording overlap")

    def test_absence_from_the_corpus_is_described_as_absence_not_originality(self, client):
        answer = self._answer(
            client, self._project(client), "quantum annealing for ribosome kinetics"
        )
        assert "MAIROS found nothing, not that nothing exists" in answer

    def test_an_overclaiming_model_cannot_get_a_novelty_claim_into_the_answer(self, client):
        """The model is never given the novelty question, so it cannot answer it."""
        from app import dependencies as deps
        from services.agents.orchestrator import AgentOrchestrator

        # A plain list, not a class attribute: OfflineChatModel is a pydantic
        # model, and pydantic reserves class-level annotations for fields.
        seen: list[str] = []

        class Overclaimer(OfflineChatModel):
            def _call(self, messages, stop=None, run_manager=None, **kwargs):
                prompt = "\n".join(str(getattr(m, "content", m)) for m in messages)
                seen.append(prompt)
                if "MAIROS-TASK: synthesis" in prompt:
                    return (
                        "This idea is novel and has never been done before in this "
                        "field [paper.pdf, p. 1]."
                    )
                return super()._call(messages, stop=stop, run_manager=run_manager, **kwargs)

        project_id = self._project(client)
        model = Overclaimer()
        deps.set_orchestrator(
            AgentOrchestrator(llm=model, chroma_store=deps.get_chroma_store())
        )
        try:
            answer = self._answer(
                client, project_id, "Is my idea of quantum annealing for ribosomes novel?"
            ).lower()
        finally:
            deps.set_orchestrator(None)

        # The model's sentence is confined to the "what these sources say"
        # section and never becomes a verdict...
        assert "not an assessment of novelty in the field" in answer
        # ...and the question it was asked had the novelty framing removed.
        synthesis_prompts = [p for p in seen if "MAIROS-TASK: synthesis" in p]
        assert synthesis_prompts, "synthesis should have run"
        for prompt in synthesis_prompts:
            question = prompt.rsplit("CONTEXT:", 1)[0]
            assert "novel" not in question.lower()

    def test_neutralise_strips_the_framing_but_keeps_the_subject(self):
        from services.agents.synthesis import SynthesisAgent

        cases = {
            "Is my idea of applying diffusion models to protein folding novel?":
                "diffusion models to protein folding",
            "Has anyone already done work on retrieval augmented generation?":
                "retrieval augmented generation",
            "What is the novelty of graph neural networks here?":
                "graph neural networks",
            "Has anyone already published anything similar to my idea, which is "
            "that we could use diffusion models for generating protein backbones?":
                "generating protein backbones",
        }
        for question, expected in cases.items():
            neutral = SynthesisAgent._neutralise(question)
            assert expected in neutral, f"{question!r} lost its subject: {neutral!r}"
            for word in ("novel", "novelty", "original", "unprecedented"):
                assert word not in neutral.lower()

    def test_a_question_that_is_nothing_but_framing_falls_back_to_a_neutral_one(self):
        """The fallback must not be the original question — that was the bug."""
        from services.agents.synthesis import SynthesisAgent

        for question in ("Is this novel?", "", "   ", "Is it original?"):
            neutral = SynthesisAgent._neutralise(question)
            assert neutral == SynthesisAgent.NEUTRAL_FALLBACK
            assert "novel" not in neutral.lower()

    def test_a_question_with_no_framing_is_left_alone(self):
        from services.agents.synthesis import SynthesisAgent

        question = "quantum annealing for ribosome kinetics"
        assert SynthesisAgent._neutralise(question) == question
