"""Agent Orchestrator — the entry point to the multi-agent system.

Design note: **no LangGraph.** MAIROS's flows are short, linear, and fully
determined by one routing decision made up front — there is no cyclic state
machine, no conditional re-entry, and no need for checkpointing at mid-review
scale. A LangGraph ``StateGraph`` here would add a dependency and an
indirection layer without removing a single line of the logic below. The
registry pattern used instead keeps the same extension property that matters:
adding hypothesis generation, novelty detection, or experiment design means
writing one ``BaseAgent`` subclass, registering it, and naming it in a flow —
the orchestrator itself does not change.
"""

from __future__ import annotations

from typing import Callable

from .analysis import AnalysisAgent
from .base import AgentContext, BaseAgent
from .citations import CitationAgent
from .comparison import ComparisonAgent
from .experiment import ExperimentAgent
from .gaps import GapDetectionAgent
from .hypothesis import HypothesisAgent
from .indexer import IndexerAgent, LoaderAgent, RetrieverAgent
from .intake import ProjectIntakeAgent
from .kg_agent import KnowledgeGraphAgent
from .literature import LiteratureAgent
from .novelty import NoveltyAgent
from .patent_awareness import PatentAwarenessAgent
from .planner import PlannerAgent
from .router import FLOWS, RouterAgent
from .synthesis import SynthesisAgent


class AgentOrchestrator:
    """Route a request to the right agents and aggregate their output.

    Args:
        llm: Chat model shared by every agent. Resolved from the configured
            provider when omitted.
        chroma_store: Vector store handed to the agents that need it.
        top_k: Passages to retrieve in the question-answering flow.
    """

    def __init__(self, llm=None, chroma_store=None, top_k: int = 5):
        if llm is None:
            from services.generation.provider import get_chat_model

            llm = get_chat_model()

        self.llm = llm
        self.chroma_store = chroma_store
        self.router = RouterAgent(llm=llm)

        # Agent registry — add new capabilities here, then name them in a flow.
        self.agents: dict[str, BaseAgent] = {
            "literature": LiteratureAgent(llm=llm),
            "indexer": IndexerAgent(llm=llm),
            "loader": LoaderAgent(llm=llm),
            "retriever": RetrieverAgent(llm=llm, top_k=top_k),
            "analysis": AnalysisAgent(llm=llm),
            "knowledge_graph": KnowledgeGraphAgent(llm=llm),
            "citation": CitationAgent(llm=llm),
            "synthesis": SynthesisAgent(llm=llm),
            # Research workflows
            "comparison": ComparisonAgent(llm=llm),
            "gaps": GapDetectionAgent(llm=llm),
            "hypothesis": HypothesisAgent(llm=llm),
            "experiment": ExperimentAgent(llm=llm),
            "novelty": NoveltyAgent(llm=llm),
            "patent_awareness": PatentAwarenessAgent(llm=llm),
            "intake": ProjectIntakeAgent(llm=llm),
            # Registered but not in a default flow — see router.FLOWS.
            "planner": PlannerAgent(llm=llm),
        }

    # ------------------------------------------------------------------
    def register(self, agent: BaseAgent) -> None:
        """Add an agent to the registry at runtime."""
        self.agents[agent.name] = agent

    # ------------------------------------------------------------------
    async def run(
        self,
        question: str,
        project_id: str | None = None,
        document_id: str | None = None,
        retrieved_chunks: list[dict] | None = None,
        graph_results: list[dict] | None = None,
        task_id: str | None = None,
        emit_event: Callable[..., None] | None = None,
        flow_type: str | None = None,
        doc_count: int = 0,
    ) -> AgentContext:
        """Execute the pipeline and return the completed context.

        Args:
            question: The user's request.
            project_id: Workspace the request belongs to.
            document_id: Set when the request concerns one uploaded document.
            flow_type: Force a flow (``search`` / ``analyze`` / ``answer``);
                omit to let the Router decide.
            doc_count: How many documents the project already has — the Router
                uses this to avoid sending an empty library down the RAG path.

        Returns:
            The :class:`AgentContext` carrying every agent's output.
        """
        ctx = AgentContext(
            question=question,
            project_id=project_id,
            document_id=document_id,
            retrieved_chunks=list(retrieved_chunks or []),
            graph_results=list(graph_results or []),
            chroma_store=self.chroma_store,
            task_id=task_id,
            emit_event=emit_event,
        )

        # 1. Decide the plan.
        decision = self.router.decide(
            question,
            has_document=bool(document_id),
            doc_count=doc_count,
            forced_flow=flow_type,
        )
        ctx.intermediate_results["routing"] = decision.as_dict()
        ctx.log(
            "orchestrator",
            f"Routing to '{decision.flow}' flow ({decision.source}): {decision.reason}",
            "orchestrating",
            "running",
        )
        ctx.log(
            "orchestrator",
            "Pipeline: " + " → ".join(decision.agents),
            "orchestrating",
            "running",
        )

        # 2. Execute it. safe_run keeps one failure from aborting the pipeline.
        for agent_name in decision.agents:
            agent = self.agents.get(agent_name)
            if agent is None:
                ctx.log("orchestrator", f"Unknown agent '{agent_name}' skipped", "orchestrating")
                continue
            ctx = await agent.safe_run(ctx)

        # 3. Guarantee the caller always gets an answer field.
        if not ctx.intermediate_results.get("final_answer"):
            ctx.intermediate_results["final_answer"] = self._fallback_answer(ctx)

        errors = ctx.intermediate_results.get("errors", [])
        ctx.log(
            "orchestrator",
            "Pipeline complete"
            + (f" with {len(errors)} degraded step(s)" if errors else " successfully"),
            "completed",
            "completed",
        )
        return ctx

    # ------------------------------------------------------------------
    @staticmethod
    def _fallback_answer(ctx: AgentContext) -> str:
        """Compose a useful answer when no synthesis agent ran."""
        analysis = ctx.intermediate_results.get("analysis")
        if isinstance(analysis, dict) and analysis.get("summary"):
            parts = [analysis["summary"]]
            if analysis.get("contributions"):
                parts.append("\n\n**Key contributions**")
                parts += [f"- {c}" for c in analysis["contributions"]]
            if analysis.get("methodology"):
                parts.append(f"\n\n**Methodology**\n{analysis['methodology']}")
            if analysis.get("limitations"):
                parts.append("\n\n**Limitations**")
                parts += [f"- {c}" for c in analysis["limitations"]]
            return "\n".join(str(p) for p in parts)

        papers = ctx.intermediate_results.get("retrieved_papers", [])
        if papers:
            return "\n".join(
                f"[{i}] {p['title']} ({p.get('year') or 'n.d.'})"
                for i, p in enumerate(papers, start=1)
            )

        return "The pipeline completed but produced no answer content."


__all__ = ["AgentOrchestrator", "FLOWS"]
