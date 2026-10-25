"""Literature Retrieval Agent — searches arXiv, OpenAlex and Semantic Scholar.

One search runs several queries (see ``services/literature/queries.py``)
against every configured source at once, merges the results so a paper found
three times counts once, and keeps the best-ranked papers. Alongside the
papers it records a coverage report — what was searched, what answered, and
what the set is too small or too narrow to support — so every later agent's
output can be read against the search behind it.

Only titles, abstracts and metadata are fetched. Full texts are never
downloaded.
"""

from __future__ import annotations

import asyncio

import httpx

from services.literature import (
    build_coverage,
    build_sources,
    document_id_for,
    merge_ranked,
    plan_queries,
)
from services.literature.sources import arxiv_query, unknown_sources

from .base import AgentContext, BaseAgent


class LiteratureAgent(BaseAgent):
    """Find papers on a topic across the configured literature sources.

    Produces ``intermediate_results['retrieved_papers']``, the coverage report
    in ``intermediate_results['literature_coverage']``, and one pseudo-chunk
    per abstract in ``ctx.retrieved_chunks`` so downstream agents treat fetched
    abstracts exactly like uploaded document text.

    Args:
        max_results: Papers to keep; ``LITERATURE_MAX_RESULTS`` when omitted.
        sources: Source names to search; ``LITERATURE_SOURCES`` when omitted.
    """

    name = "literature"
    stage = "retrieving"

    def __init__(
        self,
        llm=None,
        max_results: int | None = None,
        timeout: float | None = None,
        sources: list[str] | None = None,
    ):
        super().__init__(llm=llm)
        self.max_results = max_results
        self.timeout = timeout
        self.sources = sources

    # ------------------------------------------------------------------
    @staticmethod
    def _build_query(question: str) -> str:
        """The arXiv search expression for *question* (kept for callers)."""
        return arxiv_query(question)

    def _query_writer(self):
        """The live model as a ``prompt -> reply`` callable, or ``None``.

        The offline model would only echo the rule-based queries back, so it is
        not asked.
        """
        from services.generation.provider import OfflineChatModel

        if self.llm is None or isinstance(self.llm, OfflineChatModel):
            return None
        return self.invoke_llm

    @staticmethod
    def _seed(ctx: AgentContext) -> str:
        """What to search for: the parsed project brief if there is one."""
        brief = ctx.intermediate_results.get("project_brief") or {}
        return str(brief.get("search_text") or ctx.question or "").strip()

    # ------------------------------------------------------------------
    async def search(self, text: str, seeds: list[dict] | None = None) -> tuple[list[dict], dict]:
        """Search every configured source for *text*.

        Args:
            seeds: Queries chosen before the search (a project brief's
                keywords), run ahead of any the model writes.

        Returns:
            The kept papers, best first, and the coverage report.
        """
        from app.config import settings

        names = self.sources or settings.literature_source_list
        timeout = self.timeout or settings.literature_timeout
        sources = build_sources(
            names,
            settings.literature_per_query,
            mailto=settings.openalex_mailto,
            s2_key=settings.semantic_scholar_api_key,
            deadline=settings.literature_source_deadline,
            request_timeout=timeout,
        )
        ignored = unknown_sources(names)
        if not sources:
            # Nothing would run, so the model is not asked for queries either.
            return [], build_coverage([], [], 0, [], 0, ignored_sources=ignored)

        planned, note = plan_queries(
            text,
            max(1, settings.literature_query_count),
            invoke=self._query_writer(),
            seeds=seeds,
        )
        if not planned:
            planned = [{"text": " ".join(text.split()[:8]) or "research", "written_by": "rules"}]
        queries = [item["text"] for item in planned]

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            runs = await asyncio.gather(*(source.search(client, queries) for source in sources))

        merged, duplicates = merge_ranked(
            [ranked for run in runs for ranked in run.ranked],
            focus=" ".join([text] + queries),
        )
        kept = merged[: self.max_results or settings.literature_max_results]
        coverage = build_coverage(
            planned, list(runs), len(merged), kept, duplicates,
            query_note=note, ignored_sources=ignored,
        )
        return kept, coverage

    async def fetch(self, question: str) -> list[dict]:
        """The papers a search for *question* keeps, without the report."""
        papers, _coverage = await self.search(question)
        return papers

    # ------------------------------------------------------------------
    async def run(self, ctx: AgentContext) -> AgentContext:
        seed = self._seed(ctx)
        ctx.log(self.name, f"Searching the literature for: {seed[:90]}", self.stage)

        brief = ctx.intermediate_results.get("project_brief") or {}
        seeds = [
            {"text": keyword, "written_by": brief.get("extracted_by", "rules")}
            for keyword in brief.get("keywords") or []
        ]
        try:
            papers, coverage = await self.search(seed, seeds=seeds or None)
        except Exception as exc:
            ctx.log(
                self.name,
                f"Literature search failed ({type(exc).__name__}) — continuing with "
                "documents already in the library",
                self.stage,
                "failed",
            )
            ctx.intermediate_results["retrieved_papers"] = []
            return ctx

        ctx.intermediate_results["literature_coverage"] = coverage
        queries = coverage["queries"]
        if queries:
            writers = sorted({q["written_by"] for q in queries})
            ctx.log(
                self.name,
                f"Ran {len(queries)} quer{'y' if len(queries) == 1 else 'ies'} "
                f"(written by {' and '.join(writers)}): "
                + "; ".join(q["text"] for q in queries),
                self.stage,
            )
        for source in coverage["sources"]:
            if source["status"] != "ok":
                ctx.log(self.name, f"{source['name']} failed: {source['detail']}", self.stage)

        if not papers:
            ctx.log(self.name, "No source returned a matching paper", self.stage)
            for warning in coverage["warnings"]:
                ctx.log(self.name, f"Coverage: {warning}", self.stage)
            ctx.intermediate_results["retrieved_papers"] = []
            return ctx

        ctx.intermediate_results["retrieved_papers"] = papers

        # Represent each abstract as a chunk so the rest of the pipeline is
        # identical for fetched papers and uploaded PDFs. They are also kept
        # apart: a later retrieval step replaces `retrieved_chunks`, and the
        # Novelty agent must still check claims against every fetched paper.
        fetched: list[dict] = []
        for paper in papers:
            document_id = document_id_for(paper)
            details = [f"Title: {paper['title']}", f"Authors: {', '.join(paper['authors'])}"]
            if paper.get("published") or paper.get("year"):
                details.append(f"Published: {paper.get('published') or paper['year']}")
            if paper.get("venue"):
                details.append(f"Venue: {paper['venue']}")
            fetched.append(
                {
                    "chunk_id": document_id,
                    "document_id": document_id,
                    "document_name": paper["title"],
                    "page": None,
                    "text": "\n".join(details) + f"\n\nAbstract: {paper.get('abstract', '')}",
                    "score": 1.0,
                    "source": paper["source"],
                }
            )
        ctx.retrieved_chunks.extend(fetched)
        ctx.intermediate_results["fetched_chunks"] = fetched

        answered = [s["name"] for s in coverage["sources"] if s["status"] == "ok"]
        ctx.log(
            self.name,
            f"Kept {len(papers)} of {coverage['papers_found']} papers from "
            f"{', '.join(answered)} ({coverage['duplicates_merged']} duplicate record(s) "
            "merged): " + "; ".join(p["title"][:60] for p in papers[:3]),
            self.stage,
            "running",
        )
        for warning in coverage["warnings"]:
            ctx.log(self.name, f"Coverage: {warning}", self.stage)
        return ctx
