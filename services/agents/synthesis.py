"""Synthesis Agent — produces the final grounded answer.

This is the agent that writes ``final_answer``. It never invents sources: the
answer is generated strictly from the chunks already on the context, and each
chunk is echoed back as a structured citation so the UI can show provenance
next to the prose.
"""

from __future__ import annotations

from services.generation.llm import GenerationService

from .base import AgentContext, BaseAgent
from .evidence import NEUTRAL_QUESTION, strip_question_framing

OVERVIEW_PROMPT = (
    "You are writing a short literature overview for a researcher.\n"
    "Using ONLY the paper abstracts below, write 4-6 sentences covering: what "
    "problem this line of work addresses, the main approaches taken, and where "
    "the papers agree or differ. Cite each paper inline by its number, e.g. [1].\n"
    "Do not use any knowledge beyond the abstracts.\n\n"
    "Topic: {question}\n\n"
    "Papers:\n{papers}\n"
)


class SynthesisAgent(BaseAgent):
    """Turn retrieved evidence into a citation-backed answer."""

    name = "synthesis"
    stage = "analyzing"

    def __init__(self, llm=None):
        super().__init__(llm=llm)
        self._generation: GenerationService | None = None

    @property
    def generation(self) -> GenerationService:
        if self._generation is None:
            self._generation = GenerationService(llm=self.llm)
        return self._generation

    # ------------------------------------------------------------------
    @staticmethod
    def _citations(ctx: AgentContext) -> list[dict]:
        """Structured provenance for every chunk that fed the answer."""
        citations = []
        for chunk in ctx.retrieved_chunks[:10]:
            citations.append(
                {
                    "document_id": chunk.get("document_id", ""),
                    "chunk_id": chunk.get("chunk_id", ""),
                    "document_name": chunk.get("document_name", ""),
                    "text": (chunk.get("text", "") or "")[:600],
                    "page": chunk.get("page"),
                    "score": chunk.get("score"),
                }
            )
        return citations

    async def _overview(self, ctx: AgentContext) -> str:
        """Summarise newly discovered literature (the 'search' flow)."""
        papers = ctx.intermediate_results.get("retrieved_papers", [])
        if not papers:
            return (
                "No papers were retrieved for this topic. Try a broader phrasing, "
                "or upload a PDF to build the library directly."
            )

        listing = "\n\n".join(
            f"[{i}] {p['title']} ({p.get('year') or 'n.d.'})\n"
            f"Authors: {', '.join(p.get('authors', [])[:5])}\n"
            f"Abstract: {p.get('abstract', '')[:1200]}"
            for i, p in enumerate(papers, start=1)
        )

        if self.llm is None:
            return "\n".join(
                f"[{i}] {p['title']} — {p.get('abstract', '')[:220]}…"
                for i, p in enumerate(papers, start=1)
            )

        return self.invoke_llm(
            OVERVIEW_PROMPT.format(question=ctx.question, papers=listing)
        ).strip()

    # ------------------------------------------------------------------
    # Novelty-safe synthesis
    # ------------------------------------------------------------------
    # The framing stripper lives in `evidence.py` because the Novelty agent
    # needs the same answer for its scoring — see `strip_question_framing`.
    NEUTRAL_FALLBACK = NEUTRAL_QUESTION

    @classmethod
    def _neutralise(cls, question: str) -> str:
        """Strip novelty framing from a question before a model sees it.

        The generator's system prompt requires grounding and citation, but says
        nothing about novelty — so asked "is X novel?" over passages that do not
        mention X, a perfectly obedient model answers "none of these passages
        describe X, so it appears to be novel", cites a passage for it, and
        breaks the one promise the novelty flow makes. The fix is not to trust
        the model with the question: it is never given it.
        """
        return strip_question_framing(question)

    @staticmethod
    def _novelty_answer(ctx: AgentContext, corpus_summary: str) -> str:
        """Compose the novelty answer from the report, not from a model.

        Every verdict here is one the agent computed. The model's contribution
        is confined to `corpus_summary`, which describes what the corpus says
        about the topic and never whether anything is new.
        """
        report = ctx.intermediate_results.get("novelty") or {}
        assessments = report.get("assessments", [])
        scope = report.get("scope", "the sources searched")

        lines = [
            f"**Checked against {scope}.** This says what is already covered by "
            "those sources. It is not an assessment of novelty in the field — "
            "MAIROS has not searched the published literature and cannot make "
            "that claim.",
            "",
        ]

        for assessment in assessments:
            lines.append(f"**{assessment['claim']}**")
            lines.append(f"- {assessment['verdict_label']} "
                         f"({round(assessment['corpus_overlap'] * 100)}% wording overlap).")
            for prior in assessment.get("nearest_prior_work", []):
                citation = prior.get("citation") or {}
                page = citation.get("page")
                marker = f"[{citation.get('document_name', 'source')}"
                marker += f", p. {page}]" if page is not None else "]"
                lines.append(f"- {prior['note']} {marker}")
            if not assessment.get("nearest_prior_work"):
                lines.append(
                    "- No passage in the searched sources mentions this. That means "
                    "MAIROS found nothing, not that nothing exists."
                )
            lines.append("")

        if corpus_summary:
            lines.append("**What these sources do say on the topic**")
            lines.append(corpus_summary)

        return "\n".join(lines).strip()

    @staticmethod
    def _project_header(ctx: AgentContext) -> str:
        """What MAIROS took the project to be, and what it searched.

        Composed from the brief and the coverage report, not by a model, so a
        reader can check the framing before reading anything built on it.
        """
        from services.literature import describe_scope

        brief = ctx.intermediate_results.get("project_brief") or {}
        by = "the live model, checked against your text" if brief.get("extracted_by") == "model" else "rules"
        lines = [f"**Your project, as MAIROS read it** (extracted by {by})"]
        if brief.get("problem"):
            lines.append(f"- Problem: {brief['problem']}")
        if brief.get("methods"):
            lines.append(f"- Methods: {', '.join(brief['methods'])}")
        contributions = brief.get("contributions") or []
        lines.append(
            f"- Stated contributions: {len(contributions)} (each checked below)"
            if contributions
            else "- Stated contributions: none found, so the description itself is checked below"
        )

        coverage = ctx.intermediate_results.get("literature_coverage")
        scope = describe_scope(coverage)
        if scope:
            lines.append("")
            lines.append(f"**Searched:** {scope}.")
            for warning in (coverage or {}).get("warnings", []):
                lines.append(f"- {warning}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    async def run(self, ctx: AgentContext) -> AgentContext:
        flow = (ctx.intermediate_results.get("routing") or {}).get("flow", "answer")

        if flow == "search":
            ctx.log(self.name, "Synthesising an overview of the retrieved papers", self.stage)
            answer = await self._overview(ctx)
        elif ctx.intermediate_results.get("novelty"):
            # Any flow that ran the novelty agent — `novelty`, `review`, or a
            # composed one — goes down this path. Keyed on the result, not the
            # flow name, so a new flow that includes the agent is covered
            # automatically rather than silently falling through to free text.
            ctx.log(
                self.name,
                "Composing a scoped novelty answer (field-level novelty not asserted)",
                self.stage,
            )
            summary = ""
            if ctx.retrieved_chunks:
                summary = await self.generation.generate(
                    self._neutralise(ctx.focus_text()), _as_objects(ctx)
                )
            answer = self._novelty_answer(ctx, summary)
            if ctx.intermediate_results.get("project_brief"):
                answer = self._project_header(ctx) + "\n\n" + answer
        else:
            ctx.log(
                self.name,
                f"Generating a grounded answer from {len(ctx.retrieved_chunks)} passages",
                self.stage,
            )
            if not ctx.retrieved_chunks:
                answer = (
                    "I cannot answer this based on the provided documents — nothing "
                    "in this project matched the question. Upload a PDF or run a "
                    "topic search first."
                )
            else:
                answer = await self.generation.generate(ctx.question, _as_objects(ctx))

        ctx.intermediate_results["final_answer"] = answer
        ctx.intermediate_results["citations"] = self._citations(ctx)
        ctx.log(self.name, f"Answer generated ({len(answer)} chars)", self.stage)
        return ctx


class _Chunk:
    """Lightweight adapter so dict chunks satisfy GenerationService."""

    __slots__ = ("document_name", "page", "text")

    def __init__(self, data: dict):
        self.document_name = data.get("document_name", "")
        self.page = data.get("page")
        self.text = data.get("text", "")


def _as_objects(ctx: AgentContext) -> list[_Chunk]:
    return [_Chunk(c) for c in ctx.retrieved_chunks]
