"""Citation Generation Agent — formats processed papers as APA references."""

from __future__ import annotations

import json
import re

from services.common.json_utils import extract_json
from services.generation.provider import TASK_CITATION

from .base import AgentContext, BaseAgent

CITATION_PROMPT = (
    TASK_CITATION + "\n"
    "Format the paper metadata below as APA 7th edition references.\n\n"
    "Rules: 'Surname, F. M.' for authors; '&' before the last author; up to 20 "
    "authors then an ellipsis; year in parentheses; sentence case title; end with "
    "the venue (or the source when there is no venue), then the URL. Use 'n.d.' "
    "when the year is unknown. Invent nothing — use "
    "only the metadata given.\n\n"
    "Return ONLY a JSON array of reference strings.\n\n"
    "Papers:\n{papers}\n"
)


def _apa_authors(authors: list[str]) -> str:
    """Deterministic APA author list — used as the offline/fallback formatter."""
    formatted: list[str] = []
    for author in authors[:20]:
        parts = [p for p in str(author).replace(".", " ").split() if p]
        if not parts:
            continue
        if len(parts) == 1:
            formatted.append(parts[0])
        else:
            initials = " ".join(f"{p[0].upper()}." for p in parts[:-1])
            formatted.append(f"{parts[-1]}, {initials}")

    if not formatted:
        return "Anonymous"
    if len(formatted) == 1:
        return formatted[0]
    return ", ".join(formatted[:-1]) + ", & " + formatted[-1]


def fallback_apa(paper: dict) -> str:
    """Format one reference without an LLM."""
    authors = _apa_authors(list(paper.get("authors") or []))
    year = str(paper.get("year") or paper.get("published") or "n.d.")[:4] or "n.d."
    title = str(paper.get("title", "Untitled")).strip().rstrip(".")
    # The venue is the APA "source" when a source reported one; otherwise the
    # service the paper was found in.
    source = paper.get("venue") or paper.get("source") or "MAIROS document library"
    url = paper.get("url", "")
    reference = f"{authors} ({year}). {title}. {source}."
    if url:
        reference += f" {url}"
    return reference


class CitationAgent(BaseAgent):
    """Produce a formatted reference list for every processed paper."""

    name = "citation"
    stage = "generating_citations"

    def _collect_papers(self, ctx: AgentContext) -> list[dict]:
        """Gather citable items from whichever flow produced them."""
        papers = list(ctx.intermediate_results.get("retrieved_papers", []))
        if papers:
            return papers

        seen: dict[str, dict] = {}
        for chunk in ctx.retrieved_chunks:
            name = chunk.get("document_name")
            if not name or name in seen:
                continue
            seen[name] = {
                "title": name,
                "authors": [],
                "year": chunk.get("year", ""),
                "published": "",
                "source": chunk.get("source") or "Uploaded document",
                "url": "",
                "document_id": chunk.get("document_id", ""),
            }
        return list(seen.values())

    # ------------------------------------------------------------------
    async def run(self, ctx: AgentContext) -> AgentContext:
        ctx.log(self.name, "Formatting APA references", self.stage)

        papers = self._collect_papers(ctx)
        if not papers:
            ctx.intermediate_results["references"] = []
            ctx.log(self.name, "No sources to cite", self.stage)
            return ctx

        deterministic = [fallback_apa(p) for p in papers]

        if self.llm is None:
            ctx.intermediate_results["references"] = deterministic
            ctx.log(self.name, f"Formatted {len(deterministic)} references", self.stage)
            return ctx

        payload = json.dumps(
            [
                {
                    "title": p.get("title"),
                    "authors": p.get("authors", []),
                    "published": p.get("published", ""),
                    "year": p.get("year", ""),
                    "url": p.get("url", ""),
                    "doi": p.get("doi", ""),
                    "venue": p.get("venue", ""),
                    "source": p.get("source", ""),
                }
                for p in papers
            ],
            indent=2,
        )

        try:
            raw = self.invoke_llm(CITATION_PROMPT.format(papers=payload))
            parsed = extract_json(raw, default=None)

            if isinstance(parsed, list) and parsed:
                references = [str(r).strip() for r in parsed if str(r).strip()]
            elif isinstance(parsed, dict) and isinstance(parsed.get("citations"), list):
                references = [str(r).strip() for r in parsed["citations"]]
            else:
                # Model returned prose — salvage line-per-reference output.
                lines = [
                    re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", ln).strip()
                    for ln in raw.splitlines()
                ]
                references = [ln for ln in lines if len(ln) > 25]

            if len(references) < len(papers):
                references = deterministic
                ctx.log(
                    self.name,
                    "LLM output incomplete — used the deterministic APA formatter",
                    self.stage,
                )
        except Exception as exc:
            references = deterministic
            ctx.log(self.name, f"LLM formatting failed ({exc}); used fallback", self.stage)

        ctx.intermediate_results["references"] = references
        ctx.intermediate_results.setdefault("cited_papers", papers)
        ctx.log(self.name, f"Generated {len(references)} APA references", self.stage)
        return ctx
