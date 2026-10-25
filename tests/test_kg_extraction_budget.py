"""Why the knowledge graph stayed empty with a reasoning model — and the fix.

Diagnosed with one live call to `openai/gpt-oss-120b` (22 October 2026): the
extractor itself worked, returning 7 entities and 6 relations for a
330-character input, but it spent 1,156 of the 1,400-token cap doing so (683
of them hidden reasoning). The real inputs the agent sends are 1,600-1,800
characters, so the reply ran out of budget mid-JSON, nothing parsed, and every
analysis added "+0 nodes" without an error.

These tests replay that failure offline with a real LangChain chat model whose
replies have the same shape as the live one.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from services.knowledge_graph.entity_extractor import EntityRelationExtractor

# The live reply, as returned: pretty-printed, entities first.
LIVE_REPLY = """{
  "entities": [
    {
      "name": "grounded generation",
      "type": "Method",
      "description": "retrieval-augmented generation conditioned on retrieved passages"
    },
    {
      "name": "dense retriever",
      "type": "Method",
      "description": "retrieves passages for conditioning"
    },
    {
      "name": "Natural Questions dataset",
      "type": "Dataset",
      "description": "benchmark used for evaluation"
    }
  ],
  "relations": [
    {
      "subject": "grounded generation",
      "relation": "USES",
      "object": "dense retriever",
      "confidence": 0.95
    },
    {
      "subject": "grounded generation",
      "relation": "EVALUATED_ON",
      "object": "Natural Questions dataset",
      "confidence": 0.9
    }
  ]
}"""

# Where the token cap cuts it: inside the second relation.
CUT_IN_RELATIONS = LIVE_REPLY[: LIVE_REPLY.index('"relation": "EVALUATED_ON"')]
# Where a tighter cap cuts it: inside the entity list.
CUT_IN_ENTITIES = LIVE_REPLY[: LIVE_REPLY.index('"name": "Natural Questions')]


class ScriptedChatModel(BaseChatModel):
    """Returns a fixed reply and records the per-call kwargs it was given."""

    reply: str = ""
    finish_reason: str = "stop"
    calls: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        self.calls.append(kwargs)
        message = AIMessage(content=self.reply, response_metadata={"finish_reason": self.finish_reason})
        return ChatResult(generations=[ChatGeneration(message=message)])


def model(reply: str, finish_reason: str = "stop") -> ScriptedChatModel:
    return ScriptedChatModel(reply=reply, finish_reason=finish_reason, calls=[])


class TestExtractionBudget:
    def test_the_extraction_call_gets_its_own_budget(self):
        llm = model(LIVE_REPLY)
        EntityRelationExtractor(llm=llm, max_tokens=4096).extract("text")
        assert llm.calls == [{"max_tokens": 4096}]

    def test_the_agent_uses_the_configured_extraction_budget(self, monkeypatch):
        from app.config import settings
        from services.agents.kg_agent import KnowledgeGraphAgent

        monkeypatch.setattr(settings, "llm_extraction_max_tokens", 3000)
        assert KnowledgeGraphAgent(llm=model(LIVE_REPLY)).extractor.max_tokens == 3000

    def test_without_a_budget_no_override_is_sent(self):
        llm = model(LIVE_REPLY)
        EntityRelationExtractor(llm=llm).extract("text")
        assert llm.calls == [{}]

    def test_the_complete_live_reply_still_parses(self):
        result = EntityRelationExtractor(llm=model(LIVE_REPLY), max_tokens=4096).extract("text")
        assert [e.name for e in result.entities] == [
            "grounded generation",
            "dense retriever",
            "Natural Questions dataset",
        ]
        assert len(result.relations) == 2
        assert result.problem == ""


class TestTruncatedReplies:
    def test_cut_off_in_the_relations_keeps_the_entities_and_says_why(self):
        result = EntityRelationExtractor(llm=model(CUT_IN_RELATIONS, "length")).extract("text")
        assert [e.name for e in result.entities] == [
            "grounded generation",
            "dense retriever",
            "Natural Questions dataset",
        ]
        assert result.relations == []
        assert "output token limit" in result.problem
        assert "entity list was kept" in result.problem

    def test_cut_off_in_the_entities_reports_the_limit(self):
        result = EntityRelationExtractor(llm=model(CUT_IN_ENTITIES, "length")).extract("text")
        assert result.entities == []
        assert "output token limit" in result.problem

    def test_budget_spent_entirely_on_reasoning(self):
        result = EntityRelationExtractor(llm=model("", "length")).extract("text")
        assert result.entities == []
        assert "output token limit" in result.problem

    def test_unparseable_but_not_truncated_is_reported_as_such(self):
        result = EntityRelationExtractor(llm=model("I could not find entities.", "stop")).extract("text")
        assert "no parseable JSON" in result.problem


class TestTheAgentEndToEnd:
    @pytest.mark.asyncio
    async def test_a_truncated_reply_still_grows_the_graph_and_the_run_says_why(self, tmp_path):
        from services.agents.base import AgentContext
        from services.agents.kg_agent import KnowledgeGraphAgent
        from services.knowledge_graph.networkx_store import KnowledgeGraphStore

        store = KnowledgeGraphStore(base_dir=tmp_path)
        agent = KnowledgeGraphAgent(llm=model(CUT_IN_RELATIONS, "length"), store=store)
        ctx = AgentContext(question="q", project_id="p1")
        ctx.intermediate_results["analysis"] = {"summary": "Grounded generation uses a dense retriever."}

        ctx = await agent.run(ctx)

        assert store.for_project("p1").stats()["nodes"] == 3
        assert any("Entity extraction was incomplete" in line and "output token limit" in line for line in ctx.trace)
