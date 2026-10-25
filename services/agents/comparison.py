"""Comparison Agent — builds a cited comparison table across papers.

The output is a table, not prose: rows are comparison dimensions, columns are
the documents being compared, and **every cell carries the passage that
supports it**. A cell whose claim cannot be traced back to a retrieved chunk of
that document is dropped rather than shown, so the table cannot quietly assert
something no source said.

The agent also widens its own retrieval when the context holds fewer than two
documents — comparing one paper with itself is not a comparison, and a flow
that silently produced a one-column table would be worse than one that says it
needs more sources.
"""

from __future__ import annotations

from services.common.json_utils import extract_json
from services.generation.provider import TASK_COMPARISON

from .base import AgentContext, BaseAgent
from .evidence import Source, citation_for, group_sources, render_sources

COMPARISON_PROMPT = (
    TASK_COMPARISON + "\n"
    "Compare the sources below for a researcher. Use ONLY their content.\n\n"
    "Pick 3-5 comparison dimensions that the sources actually speak to (for "
    "example: problem addressed, method, data used, reported results, stated "
    "limitations). For each dimension, give one short cell per source, quoting "
    "or closely paraphrasing that source. If a source says nothing about a "
    "dimension, omit its cell — never guess.\n\n"
    "Return ONLY JSON:\n"
    '{{"dimensions": ["..."],\n'
    ' "rows": [{{"dimension": "...", "cells": [{{"source_key": "S1", "value": "..."}}]}}],\n'
    ' "agreements": [{{"claim": "...", "sources": ["S1", "S2"]}}],\n'
    ' "contradictions": [{{"claim": "...", "positions": [{{"source_key": "S1", "position": "..."}}]}}],\n'
    ' "gaps": ["..."]}}\n\n'
    "Sources:\n{sources}\n"
)

MIN_SOURCES = 2
WIDE_RETRIEVAL_K = 24


class ComparisonAgent(BaseAgent):
    """Cross-source comparison rendered as a citation-backed table."""

    name = "comparison"
    stage = "analyzing"

    # ------------------------------------------------------------------
    def _widen(self, ctx: AgentContext) -> list[dict]:
        """Retrieve a broader slice so more than one document is in play."""
        if ctx.chroma_store is None:
            return list(ctx.retrieved_chunks)

        from services.retrieval.hybrid import HybridRetriever

        chunks, _ = HybridRetriever(vector=ctx.chroma_store).retrieve(
            ctx.focus_text(), project_id=ctx.project_id, top_k=WIDE_RETRIEVAL_K
        )
        return [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "document_name": chunk.document_name,
                "page": chunk.page,
                "text": chunk.text,
                "score": chunk.score,
            }
            for chunk in chunks
        ] or list(ctx.retrieved_chunks)

    # ------------------------------------------------------------------
    @staticmethod
    def _cite_cells(rows: list, sources: dict[str, Source]) -> tuple[list[dict], int]:
        """Attach a supporting passage to each cell; drop what cannot be cited."""
        cited_rows: list[dict] = []
        dropped = 0

        for row in rows:
            if not isinstance(row, dict):
                continue
            dimension = str(row.get("dimension", "")).strip()
            if not dimension:
                continue

            cells = []
            for cell in row.get("cells", []):
                if not isinstance(cell, dict):
                    continue
                key = str(cell.get("source_key", "")).strip()
                value = str(cell.get("value", "")).strip()
                source = sources.get(key)
                if not value or source is None:
                    dropped += 1
                    continue

                citation = citation_for(value, source.chunks)
                if citation is None:
                    # Nothing in this document's retrieved text supports the
                    # claim — a cited table must not display it.
                    dropped += 1
                    continue

                cells.append(
                    {
                        "source_key": key,
                        "document_name": source.document_name,
                        "value": value[:400],
                        "citation": citation,
                    }
                )

            if cells:
                cited_rows.append({"dimension": dimension, "cells": cells})

        return cited_rows, dropped

    # ------------------------------------------------------------------
    async def run(self, ctx: AgentContext) -> AgentContext:
        chunks = list(ctx.retrieved_chunks)
        sources = group_sources(chunks)

        if len(sources) < MIN_SOURCES:
            chunks = self._widen(ctx)
            sources = group_sources(chunks)
            ctx.log(
                self.name,
                f"Widened retrieval to find comparable documents ({len(sources)} found)",
                self.stage,
            )

        if len(sources) < MIN_SOURCES:
            ctx.intermediate_results["comparison"] = {
                "sources": [source.as_dict() for source in sources],
                "dimensions": [],
                "rows": [],
                "agreements": [],
                "contradictions": [],
                "gaps": [],
                "note": (
                    "A comparison needs at least two distinct documents; this "
                    "project matched only "
                    f"{len(sources)}. Upload another paper or run a topic search first."
                ),
            }
            ctx.log(
                self.name,
                "Fewer than two distinct sources — nothing to compare",
                self.stage,
            )
            return ctx

        ctx.log(
            self.name,
            "Comparing " + ", ".join(f"{s.key}={s.document_name}" for s in sources),
            self.stage,
        )

        parsed = {}
        if self.llm is not None:
            parsed = extract_json(
                self.invoke_llm(
                    COMPARISON_PROMPT.format(sources=render_sources(sources))
                ),
                default={},
            )
        if not isinstance(parsed, dict):
            parsed = {}

        by_key = {source.key: source for source in sources}
        rows, dropped = self._cite_cells(parsed.get("rows", []), by_key)

        agreements = [
            {
                "claim": str(item.get("claim", ""))[:300],
                "sources": [
                    by_key[str(key)].document_name
                    for key in item.get("sources", [])
                    if str(key) in by_key
                ],
            }
            for item in parsed.get("agreements", [])
            if isinstance(item, dict) and item.get("claim")
        ]

        contradictions = []
        for item in parsed.get("contradictions", []):
            if not isinstance(item, dict) or not item.get("claim"):
                continue
            positions = []
            for position in item.get("positions", []):
                if isinstance(position, dict):
                    key = str(position.get("source_key", ""))
                    text = str(position.get("position", ""))[:300]
                elif isinstance(position, str):
                    key, text = "", position[:300]
                else:
                    continue
                source = by_key.get(key)
                positions.append(
                    {
                        "document_name": source.document_name if source else "",
                        "position": text,
                        "citation": citation_for(text, source.chunks) if source else None,
                    }
                )
            contradictions.append(
                {"claim": str(item.get("claim", ""))[:300], "positions": positions}
            )

        comparison = {
            "sources": [source.as_dict() for source in sources],
            "dimensions": [row["dimension"] for row in rows],
            "rows": rows,
            "agreements": agreements,
            "contradictions": contradictions,
            "gaps": [str(gap)[:300] for gap in parsed.get("gaps", []) if str(gap).strip()],
            "uncited_cells_dropped": dropped,
        }

        ctx.intermediate_results["comparison"] = comparison
        ctx.log(
            self.name,
            f"Built a {len(rows)}-dimension table across {len(sources)} sources "
            f"({sum(len(row['cells']) for row in rows)} cited cells"
            + (f", {dropped} uncited dropped)" if dropped else ")"),
            self.stage,
        )
        return ctx
