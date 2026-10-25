"""The `project` flow: a pasted project description, reviewed against the literature.

Covers the Intake agent (reading the description into a brief that says
nothing the description does not), routing (a long description is recognised
without spending a model call), and the whole flow through the API over
recorded literature responses.
"""

from __future__ import annotations

import json

import pytest

from literature_fixtures import use_recorded_sources
from services.agents.base import AgentContext
from services.agents.intake import ProjectIntakeAgent, search_text_for
from services.agents.router import FLOWS, RouterAgent, looks_like_project_description

DESCRIPTION = (
    "Retrieval-augmented question answering for course notes\n"
    "Students struggle to find answers in long lecture notes, and manual search "
    "is slow. We propose a retrieval-augmented generation system that answers "
    "questions from the course notes with citations to the passage used. The "
    "system uses dense passage retrieval over the notes and a language model "
    "to write the answer. We will evaluate it on questions written by teaching "
    "assistants. Our approach aims to reduce the time students spend searching."
)


class _BriefModel:
    """A live-looking model that answers the intake prompt with a fixed brief."""

    def __init__(self, brief: dict):
        self.reply = json.dumps(brief)
        self.prompts: list[str] = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.reply


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------
class TestIntakeRules:
    def test_the_rules_brief_uses_the_descriptions_own_sentences(self):
        brief = ProjectIntakeAgent.rules_brief(DESCRIPTION)

        assert brief["title"] == "Retrieval-augmented question answering for course notes"
        assert brief["problem"].startswith("Students struggle to find answers")
        assert any(c.startswith("We propose a retrieval-augmented generation system") for c in brief["contributions"])
        assert brief["keywords"]
        # Every sentence it reports is a sentence the user wrote.
        for item in brief["contributions"] + brief["goals"] + [brief["problem"]]:
            assert item.rstrip("…") in " ".join(DESCRIPTION.split())

    def test_plans_and_aims_are_goals_not_contributions(self):
        """Checking "we will evaluate it…" for coverage only reported noise."""
        brief = ProjectIntakeAgent.rules_brief(DESCRIPTION)
        assert len(brief["contributions"]) == 1
        assert any(g.startswith("We will evaluate it") for g in brief["goals"])
        assert any(g.startswith("Our approach aims") for g in brief["goals"])

    def test_the_rules_keywords_are_the_descriptions_technical_terms(self):
        keywords = ProjectIntakeAgent.rules_brief(DESCRIPTION)["keywords"]
        assert keywords[:3] == [
            "retrieval-augmented question answering",
            "dense passage retrieval",
            "retrieval-augmented generation",
        ]
        # Connective prose never forms a search phrase.
        assert not any(w in " ".join(keywords) for w in ("struggle", "slow", "manual search"))

    @pytest.mark.asyncio
    async def test_offline_the_brief_is_built_by_rules_and_says_so(self):
        from services.generation.provider import OfflineChatModel

        ctx = await ProjectIntakeAgent(llm=OfflineChatModel()).run(AgentContext(question=DESCRIPTION))
        brief = ctx.intermediate_results["project_brief"]
        assert brief["extracted_by"] == "rules"
        assert brief["search_text"]
        assert ctx.focus_text() == brief["search_text"]


class TestIntakeModel:
    @pytest.mark.asyncio
    async def test_items_the_description_does_not_support_are_dropped(self):
        model = _BriefModel(
            {
                "title": "Course-notes question answering",
                "problem": "Students struggle to find answers in long lecture notes.",
                "domain": "question answering",
                "methods": ["dense passage retrieval", "reinforcement learning from human feedback"],
                "datasets": ["questions written by teaching assistants", "the SQuAD benchmark"],
                "goals": ["reduce the time students spend searching"],
                "contributions": [
                    "A retrieval-augmented generation system that answers questions from course notes with citations.",
                    "A new state-of-the-art result on MMLU.",
                ],
                "keywords": ["retrieval-augmented generation", "educational QA", "RAG", "x" * 200],
            }
        )
        ctx = await ProjectIntakeAgent(llm=model).run(AgentContext(question=DESCRIPTION))
        brief = ctx.intermediate_results["project_brief"]

        assert brief["extracted_by"] == "model"
        assert brief["methods"] == ["dense passage retrieval"]
        assert brief["datasets"] == ["questions written by teaching assistants"]
        assert len(brief["contributions"]) == 1
        assert brief["dropped_ungrounded"] == 3
        # Keywords are search terms: synonyms are allowed, junk is not.
        assert brief["keywords"] == ["retrieval-augmented generation", "educational QA", "RAG"]
        assert "[MAIROS-TASK: intake]" in model.prompts[0]

    @pytest.mark.asyncio
    async def test_an_unusable_reply_falls_back_to_rules(self):
        model = _BriefModel({})
        model.reply = "I'd be happy to help with your project!"
        ctx = await ProjectIntakeAgent(llm=model).run(AgentContext(question=DESCRIPTION))
        brief = ctx.intermediate_results["project_brief"]
        assert brief["extracted_by"] == "rules"
        assert "unusable" in brief["note"]

    def test_the_search_text_is_compact(self):
        text = search_text_for(
            {
                "problem": "Students struggle to find answers in lecture notes.",
                "methods": ["dense passage retrieval", "language model"],
                "keywords": ["retrieval-augmented generation", "educational QA"],
            }
        )
        assert text == (
            "Students struggle to find answers in lecture notes. using dense passage "
            "retrieval, language model. retrieval-augmented generation, educational QA"
        )
        assert len(search_text_for({"problem": "word " * 200})) <= 300


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
class TestRouting:
    def test_a_pasted_description_is_a_project_request(self):
        assert looks_like_project_description(DESCRIPTION)
        assert RouterAgent.heuristic(DESCRIPTION, False, 0)[0] == "project"

    @pytest.mark.parametrize(
        "question",
        [
            "Is my project idea new?",
            "What gaps remain in this literature?",
            "find papers on retrieval augmented generation",
        ],
    )
    def test_short_requests_keep_their_usual_flow(self, question):
        assert not looks_like_project_description(question)
        assert RouterAgent.heuristic(question, False, 3)[0] != "project"

    def test_a_long_paste_without_the_usual_phrases_still_counts(self):
        assert looks_like_project_description("sensor data fusion " * 50)

    def test_a_description_mentioning_gaps_is_not_sent_to_the_gaps_flow(self):
        text = DESCRIPTION + " What gaps remain, and how does this compare to existing work?"
        assert RouterAgent.heuristic(text, False, 5)[0] == "project"

    def test_the_decision_is_made_without_a_model_call(self):
        calls = []

        class CountingModel:
            def invoke(self, prompt):
                calls.append(prompt)
                return '{"flow": "gaps"}'

        decision = RouterAgent(llm=CountingModel()).decide(DESCRIPTION, doc_count=4)
        assert decision.flow == "project"
        assert decision.source == "rule"
        assert calls == []

    def test_the_offline_router_agrees(self):
        from services.generation.provider import TASK_ROUTE, OfflineChatModel

        raw = OfflineChatModel().invoke(f"{TASK_ROUTE}\nUser request: {DESCRIPTION}").content
        assert json.loads(raw)["flow"] == "project"

    def test_the_flow_runs_intake_before_the_review_chain(self):
        agents = FLOWS["project"]
        assert agents[:2] == ["intake", "literature"]
        assert agents.index("retriever") < agents.index("comparison") < agents.index("novelty")
        assert agents[-1] == "synthesis"

    def test_the_graph_is_built_before_anything_reads_it(self):
        """A live run had `knowledge_graph` after `gaps`: the gap agent's graph
        signals came from an empty graph, and the section was blank."""
        agents = FLOWS["project"]
        assert agents.index("indexer") < agents.index("knowledge_graph")
        assert agents.index("knowledge_graph") < agents.index("retriever")
        assert agents.index("knowledge_graph") < agents.index("gaps")


# ---------------------------------------------------------------------------
# The flow through the API
# ---------------------------------------------------------------------------
class TestProjectFlowEndToEnd:
    def _run(self, client, monkeypatch, **status):
        use_recorded_sources(monkeypatch, **status)
        project_id = client.post("/api/projects", json={"name": "Course QA"}).json()["id"]
        created = client.post(f"/api/projects/{project_id}/tasks", json={"question": DESCRIPTION})
        assert created.status_code == 201
        task = client.get(f"/api/tasks/{created.json()['id']}").json()
        assert task["status"] == "completed", task.get("error")
        return project_id, task["result"]

    def test_a_description_is_read_searched_and_checked(self, client, monkeypatch):
        project_id, result = self._run(client, monkeypatch)

        assert result["routing"]["flow"] == "project"
        assert result["project_brief"]["extracted_by"] == "rules"
        coverage = result["literature_coverage"]
        assert [s["name"] for s in coverage["sources"]] == ["arXiv", "OpenAlex", "Semantic Scholar"]
        assert coverage["papers_kept"] == 4
        assert len(result["papers"]) == 4

        # The stated contributions are what the Novelty agent checked.
        assessments = result["novelty"]["assessments"]
        assert assessments and {a["origin"] for a in assessments} == {"project"}
        assert result["novelty"]["field_novelty"] == "not_assessed"

        answer = result["answer"]
        assert answer.startswith("**Your project, as MAIROS read it**")
        assert "**Searched:** arXiv, OpenAlex and Semantic Scholar (4 queries, " in answer
        assert (
            "; kept 4 abstract(s): 2 from arXiv, 2 from OpenAlex, 3 from Semantic Scholar "
            "(some found by more than one)." in answer
        )
        for overclaim in ("is novel", "is new in the field", "no prior work exists"):
            assert overclaim not in answer.lower()

    def test_gaps_see_the_graph_built_from_the_fetched_papers(self, client, monkeypatch):
        project_id, result = self._run(client, monkeypatch)

        signals = result["gaps"]["graph_signals"]
        assert signals, "the gap agent ran against an empty graph"
        thin = next(s for s in signals if s["signal"] == "under_represented_concepts")
        graph_nodes = {n["id"] for n in client.get(f"/api/projects/{project_id}/graph").json()["nodes"]}
        # Every signal names a concept that is really in this project's graph.
        assert set(thin["entities"]) <= graph_nodes

    def test_the_graph_boosts_retrieval_in_the_flow(self, client, monkeypatch):
        """Live, the retriever reported "21 graph relations used (0 chunks boosted)"."""
        import re

        use_recorded_sources(monkeypatch)
        project_id = client.post("/api/projects", json={"name": "Boost"}).json()["id"]
        task_id = client.post(
            f"/api/projects/{project_id}/tasks", json={"question": DESCRIPTION}
        ).json()["id"]
        events = client.get(f"/api/tasks/{task_id}").json()["events"]

        line = next(e["message"] for e in events if e["agent_name"] == "retriever")
        match = re.search(r"\((\d+) chunks boosted\)", line)
        assert match, line
        assert int(match.group(1)) > 0, line

        # The labels above each abstract are not concepts of the field.
        nodes = {n["id"].lower() for n in client.get(f"/api/projects/{project_id}/graph").json()["nodes"]}
        assert not nodes & {"abstract", "authors", "title", "published", "venue"}

    def test_the_briefs_keywords_are_what_gets_searched(self, client, monkeypatch):
        _, result = self._run(client, monkeypatch)
        queries = [q["text"] for q in result["literature_coverage"]["queries"]]
        assert queries[:2] == ["retrieval-augmented question answering", "dense passage retrieval"]

    def test_quoted_passages_never_include_the_users_own_text(self, client, monkeypatch):
        """Offline, the last quoted source ran on into the question and the
        user's description was presented as something a paper said."""
        _, result = self._run(client, monkeypatch)
        said = result["answer"].split("**What these sources do say on the topic**")[-1]
        assert "Students struggle" not in said
        assert "course notes" not in said

    def test_coverage_notes_quote_abstract_text_not_metadata(self, client, monkeypatch):
        _, result = self._run(client, monkeypatch)
        for assessment in result["novelty"]["assessments"]:
            for prior in assessment["nearest_prior_work"]:
                assert not prior["note"].startswith(("Title:", "Authors:"))

    def test_merged_papers_are_stored_with_every_source(self, client, monkeypatch):
        project_id, _ = self._run(client, monkeypatch)
        papers = client.get(f"/api/projects/{project_id}/papers").json()
        rag = next(p for p in papers if p["title"].startswith("Retrieval-Augmented Generation"))

        assert rag["sources"] == ["arXiv", "OpenAlex", "Semantic Scholar"]
        assert rag["doi"] == "10.5555/3495724.3496517"
        assert rag["venue"] == "Neural Information Processing Systems"
        assert rag["citation_count"] == 4300
        assert rag["url"] == "https://doi.org/10.5555/3495724.3496517"

    def test_an_unreachable_literature_is_stated_in_the_answer(self, client, monkeypatch):
        _, result = self._run(client, monkeypatch, arxiv=503, openalex=503, semantic_scholar=503)
        assert result["papers"] == []
        assert "no literature source (none could be reached)" in result["answer"]
        assert "nothing was searched" in result["literature_coverage"]["warnings"][0]

    def test_the_flow_is_listed_for_the_ui(self, client):
        flows = {f["name"]: f for f in client.get("/api/flows").json()["flows"]}
        assert flows["project"]["agents"][0] == "intake"
        assert "never a novelty verdict" in flows["project"]["description"]
