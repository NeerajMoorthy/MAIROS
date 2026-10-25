"""Patent Awareness Agent — overlap reporting, not legal analysis.

What this does: tells a researcher that the vocabulary their project is built
on also appears in a patent text they supplied, names the claim or section it
appears in, ranks each finding by an explainable similarity score, and shows
both sides of the match so they can judge it themselves.

What this deliberately does not do: construe claims, assess novelty, or say
anything about infringement. Those are legal determinations. Every response
carries the disclaimer, and the wording throughout calls a finding an
*overlap*, never a conflict or a risk.

**The findings are computed, not generated.** Segmentation, matching and
scoring all happen in ``services/patents/`` in Python, between the project's
own concepts and the patent text the user pasted, so a model cannot invent a
match that is not there. An LLM is used for one thing only — a plain-language
summary sentence of findings that already exist — and if it returns nothing
usable, or anything that reads like a legal conclusion, a deterministic summary
is used instead. Nothing a model says can add, remove, or re-score a finding.
"""

from __future__ import annotations

from services.common.json_utils import extract_json
from services.generation.provider import TASK_PATENT
from services.patents.findings import (
    MAX_CONCEPTS,
    MIN_CONCEPT_CHARS,
    compute_findings,
    deterministic_summary,
    project_concepts,
)
from services.patents.sources import DISCLAIMER
from services.patents.wording import contains_legal_conclusion

from .base import AgentContext, BaseAgent

PATENT_SUMMARY_PROMPT = (
    TASK_PATENT + "\n"
    "Summarise, in ONE neutral sentence, the wording overlaps listed below between a "
    "research project's concepts and a patent's text. Do not give legal advice, "
    "do not assess novelty or infringement, and do not add findings.\n\n"
    "Return ONLY JSON: {{\"summary\": \"...\"}}\n\n"
    "{concepts}\n"
    "PATENT TEXT:\n{patent_text}\n"
)

# Kept importable from here: older tests and callers reference them.
__all__ = ["MAX_CONCEPTS", "MIN_CONCEPT_CHARS", "PatentAwarenessAgent"]


class PatentAwarenessAgent(BaseAgent):
    """Report computed wording overlaps between project concepts and supplied patents."""

    name = "patent_awareness"
    stage = "analyzing"

    # ------------------------------------------------------------------
    @staticmethod
    def _project_concepts(ctx: AgentContext) -> list[str]:
        """Concept vocabulary of the project: graph entities, then chunk terms."""
        return project_concepts(ctx.project_id, ctx.retrieved_chunks)

    @staticmethod
    def _corpus(ctx: AgentContext) -> list[dict]:
        """Every indexed passage of the project — the denominator for term rarity."""
        store = ctx.chroma_store
        if store is not None and ctx.project_id:
            try:
                corpus = store.all_chunks(project_id=ctx.project_id)
                if corpus:
                    return corpus
            except Exception:
                pass
        return list(ctx.retrieved_chunks)

    # ------------------------------------------------------------------
    @staticmethod
    def _record_in_graph(project_id: str | None, patent, concepts: list[str]) -> None:
        """Add the patent to the knowledge graph as a ``Patent`` node.

        This is what makes patents visible next to the literature in the graph
        view — and what triggers the standing disclaimer there. Edges use
        ``RELATED_TO`` only: the graph records that a term is shared, never
        that the work is covered by the patent.
        """
        if not project_id:
            return

        try:
            from services.knowledge_graph.networkx_store import kg_store

            graph = kg_store.for_project(project_id)
            label = patent.title or patent.number or "Patent"
            graph.add_entity(
                label,
                "Patent",
                description=(patent.number or patent.url or "user-supplied patent"),
                save=False,
            )
            for concept in concepts:
                graph.add_relation(label, "RELATED_TO", concept, confidence=0.5, save=False)
            graph.save()
        except Exception as exc:  # the graph is a view, never the source of truth
            print(f"[patent_awareness] graph update skipped: {exc}")

    # ------------------------------------------------------------------
    def _summarise(self, result: dict, patents: list) -> str:
        deterministic = deterministic_summary(result)
        overlaps = result.get("overlaps", [])
        if self.llm is None or not overlaps:
            return deterministic

        try:
            raw = self.invoke_llm(
                PATENT_SUMMARY_PROMPT.format(
                    concepts="\n".join(f"CONCEPT: {item['concept']}" for item in overlaps[:10]),
                    patent_text=(patents[0].text or "")[:1500],
                )
            )
            parsed = extract_json(raw, default={})
            summary = str((parsed or {}).get("summary", "")).strip()[:400]
        except Exception:
            return deterministic

        # A model asked for a neutral sentence may still volunteer a verdict.
        # Its text is phrasing only, so a summary that reads like a legal
        # conclusion is discarded rather than shown.
        if not summary or contains_legal_conclusion(summary):
            return deterministic
        return summary

    # ------------------------------------------------------------------
    async def run(self, ctx: AgentContext) -> AgentContext:
        from app.store import metadata_store

        patents = metadata_store.list_patents(ctx.project_id) if ctx.project_id else []

        if not patents:
            result = compute_findings([], [], [])
            result["summary"] = "No patent text has been added to this project yet."
            ctx.intermediate_results["patent_awareness"] = result
            ctx.log(self.name, "No patents supplied for this project", self.stage)
            return ctx

        concepts = self._project_concepts(ctx)
        ctx.log(
            self.name,
            f"Checking {len(concepts)} project concept(s) against {len(patents)} patent text(s)",
            self.stage,
        )

        result = compute_findings(
            patents,
            concepts,
            corpus_chunks=self._corpus(ctx),
            cite_chunks=ctx.retrieved_chunks,
        )

        for patent in patents:
            matched = [o["concept"] for o in result["overlaps"] if o["patent_id"] == patent.id]
            self._record_in_graph(ctx.project_id, patent, matched)

        result["summary"] = self._summarise(result, patents)
        ctx.intermediate_results["patent_awareness"] = result
        ctx.log(
            self.name,
            f"{len(result['overlaps'])} overlap(s) across {len(patents)} patent(s) — {DISCLAIMER}",
            self.stage,
        )
        return ctx
