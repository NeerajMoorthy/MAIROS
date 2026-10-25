"""Research Gap Detection Agent — evidence-first.

A "research gap" is easy to hallucinate and hard to defend, so this agent will
not report one it cannot point at. Two independent sources of evidence feed it:

1. **Stated limitations in the text.** The model is asked to return the
   sentence that states each gap. A returned gap is kept only if that wording
   can still be located in a retrieved passage (``citation_for``); otherwise it
   is dropped and counted, never displayed. A gap with no quote is not a gap,
   it is a guess.

2. **Structural signals from the knowledge graph.** Computed, not generated:
   concepts that only one paper mentions, and method pairs that no source ever
   compares. These are reported separately as *signals* rather than claims,
   because a missing edge is evidence of absence in this corpus only.

The two are kept apart in the output so a reader always knows whether they are
looking at something a paper said or something the graph implies.
"""

from __future__ import annotations

from services.common.json_utils import extract_json
from services.generation.provider import TASK_GAPS

from .base import AgentContext, BaseAgent
from .evidence import citation_for, group_sources, render_sources

GAP_PROMPT = (
    TASK_GAPS + "\n"
    "You are finding open research gaps for a researcher, using ONLY the "
    "sources below.\n\n"
    "Look for: stated limitations, explicit future work, unanswered questions, "
    "and claims the sources say are unverified. For each gap you report you "
    "MUST quote the sentence from the source that states it — if you cannot "
    "quote it, do not report it.\n\n"
    "Return ONLY JSON:\n"
    '{{"gaps": [{{"gap": "one sentence describing the gap",\n'
    '             "evidence_quote": "the exact sentence from the source",\n'
    '             "source_key": "S1",\n'
    '             "kind": "stated_limitation|future_work|open_question"}}]}}\n\n'
    "Sources:\n{sources}\n"
)

ALLOWED_KINDS = {"stated_limitation", "future_work", "open_question"}
MAX_GAPS = 8


class GapDetectionAgent(BaseAgent):
    """Detect research gaps that can be traced back to a passage."""

    name = "gaps"
    stage = "analyzing"

    # ------------------------------------------------------------------
    @staticmethod
    def _graph_signals(project_id: str | None) -> list[dict]:
        """Structural under-exploration signals computed from the graph."""
        if not project_id:
            return []

        try:
            from services.knowledge_graph.networkx_store import kg_store

            graph = kg_store.for_project(project_id).graph
        except Exception:
            return []

        if graph.number_of_nodes() == 0:
            return []

        signals: list[dict] = []

        # 1. Concepts mentioned exactly once — thin coverage in this corpus.
        thin = sorted(
            name
            for name, data in graph.nodes(data=True)
            if data.get("type") in {"Concept", "Method", "Dataset", "Metric", "Task"}
            and data.get("mentions", 1) == 1
        )
        if thin:
            signals.append(
                {
                    "signal": "under_represented_concepts",
                    "detail": (
                        "Mentioned by only one source in this project, so nothing here "
                        "corroborates them."
                    ),
                    "entities": thin[:10],
                }
            )

        # 2. Methods that no source in this corpus ever compares.
        methods = sorted(
            name for name, data in graph.nodes(data=True) if data.get("type") == "Method"
        )
        compared: set[frozenset[str]] = {
            frozenset((subject, obj))
            for subject, obj, data in graph.edges(data=True)
            if data.get("relation") == "COMPARES_TO"
        }
        uncompared = [
            f"{a} vs {b}"
            for index, a in enumerate(methods)
            for b in methods[index + 1 :]
            if frozenset((a, b)) not in compared
        ]
        if uncompared:
            signals.append(
                {
                    "signal": "uncompared_methods",
                    "detail": (
                        "No source in this project compares these methods directly — "
                        "absence of evidence in this corpus, not evidence of absence."
                    ),
                    "entities": uncompared[:10],
                }
            )

        return signals

    # ------------------------------------------------------------------
    async def run(self, ctx: AgentContext) -> AgentContext:
        chunks = list(ctx.retrieved_chunks)
        sources = group_sources(chunks)
        signals = self._graph_signals(ctx.project_id)

        if not sources:
            ctx.intermediate_results["gaps"] = {
                "gaps": [],
                "graph_signals": signals,
                "note": (
                    "No passages were retrieved, so no gap could be evidenced. "
                    "Index a document or run a topic search first."
                ),
            }
            ctx.log(self.name, "No passages to analyse for gaps", self.stage)
            return ctx

        ctx.log(
            self.name,
            f"Scanning {len(chunks)} passages across {len(sources)} sources for stated gaps",
            self.stage,
        )

        parsed = {}
        if self.llm is not None:
            parsed = extract_json(
                self.invoke_llm(GAP_PROMPT.format(sources=render_sources(sources))),
                default={},
            )
        if not isinstance(parsed, dict):
            parsed = {}

        by_key = {source.key: source for source in sources}
        gaps: list[dict] = []
        dropped = 0

        for index, item in enumerate(parsed.get("gaps", [])[: MAX_GAPS * 2]):
            if not isinstance(item, dict):
                continue
            text = str(item.get("gap", "")).strip()
            quote = str(item.get("evidence_quote", "")).strip()
            if not text or not quote:
                dropped += 1
                continue

            source = by_key.get(str(item.get("source_key", "")).strip())
            # Fall back to searching every retrieved chunk: a model that
            # mislabels the source key should not cost us a real gap, but an
            # unlocatable quote still must.
            pool = source.chunks if source else chunks
            citation = citation_for(quote, pool) or citation_for(text, pool)
            if citation is None:
                dropped += 1
                continue

            kind = str(item.get("kind", "stated_limitation")).strip().lower()
            gaps.append(
                {
                    "id": f"GAP{len(gaps) + 1}",
                    "gap": text[:400],
                    "kind": kind if kind in ALLOWED_KINDS else "stated_limitation",
                    "source_document": citation["document_name"],
                    "evidence_quote": quote[:320],
                    "citation": citation,
                }
            )
            if len(gaps) >= MAX_GAPS:
                break

        result = {
            "gaps": gaps,
            "graph_signals": signals,
            "uncited_gaps_dropped": dropped,
        }
        if not gaps:
            result["note"] = (
                "No gap in these passages could be tied to a quotable sentence, so "
                "none is reported. The structural signals below are computed from "
                "the knowledge graph instead."
            )

        ctx.intermediate_results["gaps"] = result
        ctx.log(
            self.name,
            f"{len(gaps)} evidenced gap(s), {len(signals)} graph signal(s)"
            + (f", {dropped} unciteable claim(s) dropped" if dropped else ""),
            self.stage,
        )
        return ctx
