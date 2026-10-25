"""Shared context and base class for all MAIROS agents.

Every agent takes an :class:`AgentContext`, mutates it, and returns it. That
single contract is what lets the orchestrator add new agents (hypothesis
generation, novelty detection, experiment design) without any agent knowing
about any other.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AgentContext:
    """State passed through the agent pipeline."""

    question: str
    project_id: str | None = None
    document_id: str | None = None

    # Retrieval state
    retrieved_chunks: list[dict] = field(default_factory=list)
    graph_results: list[dict] = field(default_factory=list)

    # Agent outputs, keyed by agent name
    intermediate_results: dict = field(default_factory=dict)

    # Human-readable reasoning trace
    trace: list[str] = field(default_factory=list)

    # Shared services injected by the orchestrator
    chroma_store: Any = None

    # Live progress reporting to the UI
    task_id: str | None = None
    emit_event: Callable[..., None] | None = None

    def log(
        self,
        agent_name: str,
        message: str,
        stage: str = "orchestrating",
        status: str = "running",
    ) -> None:
        """Record a step and stream it to the Agent Activity panel."""
        self.trace.append(f"{agent_name}: {message}")
        if self.emit_event and self.task_id:
            try:
                self.emit_event(self.task_id, agent_name, stage, status, message)
            except Exception as exc:  # telemetry must never break the pipeline
                print(f"[agent] event emit failed: {exc}")

    def focus_text(self) -> str:
        """What retrieval should look for.

        Usually the question itself. When the user pasted a whole project
        description, the Intake agent condenses it into a focused query: a
        2,000-character description embedded as one query is mostly framing,
        and the embedding model reads only its first few hundred tokens.
        """
        brief = self.intermediate_results.get("project_brief") or {}
        return str(brief.get("search_text") or self.question)

    def context_text(self, limit: int = 12000) -> str:
        """Concatenated text of the retrieved chunks."""
        return "\n\n".join(c.get("text", "") for c in self.retrieved_chunks)[:limit]


def _hit_token_cap(response) -> bool:
    """Whether the provider stopped this reply at its output token limit."""
    metadata = getattr(response, "response_metadata", None) or {}
    return metadata.get("finish_reason") == "length"


class BaseAgent(ABC):
    """Abstract base class for MAIROS agents.

    Args:
        llm: A LangChain chat model shared across agents.
    """

    name: str = "base"
    stage: str = "orchestrating"

    def __init__(self, llm=None):
        self.llm = llm

    # ------------------------------------------------------------------
    def invoke_llm(self, prompt: str) -> str:
        """Call the LLM and return plain text ('' if unavailable).

        A reply cut off at the token cap is retried once with the larger
        ``llm_retry_max_tokens`` budget. A reasoning model (gpt-oss) spends
        part of the cap thinking before it writes anything, so a cut-off reply
        is usually half a JSON object that every caller would then discard as
        unparseable — the same failure that once left the knowledge graph
        empty.

        If the retry itself fails — on a free tier, usually a 429 because the
        retry spends a second budget straight after the first (seen live) — the
        cut-off reply is returned rather than lost: a caller that can salvage
        part of it still can, and one that cannot parses nothing, as it would
        have without the retry. Only a failed *first* call raises.
        """
        from services.common.json_utils import as_text

        if self.llm is None:
            return ""
        try:
            response = self.llm.invoke(prompt)
        except Exception as exc:
            print(f"[{self.name}] LLM call failed: {exc}")
            raise

        if _hit_token_cap(response) and hasattr(self.llm, "bind"):
            from app.config import settings

            print(
                f"[{self.name}] reply reached the token cap; retrying with "
                f"{settings.llm_retry_max_tokens} tokens"
            )
            try:
                retried = self.llm.bind(max_tokens=settings.llm_retry_max_tokens).invoke(prompt)
            except Exception as exc:
                print(f"[{self.name}] retry failed ({type(exc).__name__}); keeping the cut-off reply")
                return as_text(response)
            if _hit_token_cap(retried):
                print(f"[{self.name}] reply still reached the token cap after the retry")
            response = retried
        return as_text(response)

    @abstractmethod
    async def run(self, ctx: AgentContext) -> AgentContext:
        """Execute this agent's role and return the updated context."""
        ...

    async def safe_run(self, ctx: AgentContext) -> AgentContext:
        """Run the agent, converting any failure into a logged error event.

        A single failing agent degrades the answer; it never aborts the run.
        """
        try:
            return await self.run(ctx)
        except Exception as exc:
            ctx.log(self.name, f"{type(exc).__name__}: {exc}", self.stage, "failed")
            ctx.intermediate_results.setdefault("errors", []).append(
                {"agent": self.name, "error": str(exc)}
            )
            return ctx
