"""Knowledge Graph Agent — turns processed text into nodes and edges."""

from __future__ import annotations

import re

from services.common.text import normalize_name
from services.knowledge_graph.entity_extractor import EntityRelationExtractor
from services.knowledge_graph.networkx_store import kg_store

from .base import AgentContext, BaseAgent

# Most chunks a concept is linked back to.
MAX_SOURCE_CHUNKS = 10
# Most concepts a paper node is linked to.
MAX_PAPER_CONCEPTS = 6
# An uploaded document's concepts were all extracted from it, so it links to
# every one this run added, up to the extractor's own limit.
MAX_DOCUMENT_CONCEPTS = 12


def mentions(name: str, text: str) -> bool:
    """Whether *text* mentions *name* as a whole word or phrase."""
    needle = normalize_name(name).lower()
    if not needle:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
    return re.search(pattern, normalize_name(text).lower()) is not None


class KnowledgeGraphAgent(BaseAgent):
    """Extract entities/relations and merge them into the project's graph.

    Runs after every paper is processed, so the graph accumulates across
    uploads and searches within a project.
    """

    name = "knowledge_graph"
    stage = "building_graph"

    def __init__(self, llm=None, store=None):
        super().__init__(llm=llm)
        self.store = store or kg_store
        from app.config import settings

        self.extractor = EntityRelationExtractor(
            llm=llm, max_tokens=settings.llm_extraction_max_tokens
        )

    async def run(self, ctx: AgentContext) -> AgentContext:
        ctx.log(self.name, "Extracting entities and relations", self.stage)

        graph = self.store.for_project(ctx.project_id)
        before = graph.stats()

        # 1. Structural facts we already know — papers and their authors.
        papers = ctx.intermediate_results.get("retrieved_papers", [])
        for paper in papers:
            graph.add_paper(paper["title"], paper.get("authors", []), paper.get("url", ""))

        # 2. Text to mine for concepts: prefer the analysis summary, else chunks.
        analysis = ctx.intermediate_results.get("analysis")
        text_parts: list[str] = []
        if isinstance(analysis, dict):
            text_parts.append(str(analysis.get("summary", "")))
            text_parts.extend(str(c) for c in analysis.get("contributions", []))
            text_parts.append(str(analysis.get("methodology", "")))
        if not any(p.strip() for p in text_parts):
            text_parts = [ctx.context_text(limit=6000)]

        text = "\n".join(p for p in text_parts if p and p.strip())

        entity_count = 0
        relation_count = 0
        # Names added by *this* run — the paper links below must use these
        # rather than slicing the tail of the graph's node list, which silently
        # picks up unrelated older concepts once a project has history.
        added_concepts: list[str] = []

        if text.strip():
            # The passages themselves, should the model not answer: richer
            # than a summary for picking out the concepts a paper repeats.
            result = self.extractor.extract(text, fallback_text=ctx.context_text(limit=6000))
            if result.problem:
                # Recorded as its own event so a run that adds less than it
                # should to the graph says why, rather than only "+0 nodes".
                summary = "was incomplete" if result.entities else "produced nothing"
                ctx.log(self.name, f"Entity extraction {summary}: {result.problem}", self.stage)

            # Link each entity back to the chunks that mention it, so a graph
            # hit boosts the passages about that concept. Every entity used to
            # get the same first ten chunks: each fetched abstract was then
            # boosted whenever any concept matched, and the boost meant nothing.
            chunks = [c for c in ctx.retrieved_chunks if c.get("chunk_id")]

            for entity in result.entities:
                sources = [
                    c["chunk_id"] for c in chunks if mentions(entity.name, c.get("text", ""))
                ]
                added = graph.add_entity(
                    entity.name,
                    entity.type,
                    entity.description,
                    source_chunk_ids=sources[:MAX_SOURCE_CHUNKS],
                    save=False,
                )
                if added:
                    entity_count += 1
                    if entity.type not in ("Paper", "Person"):
                        added_concepts.append(added)

            for relation in result.relations:
                if graph.add_relation(
                    relation.subject,
                    relation.relation,
                    relation.object,
                    relation.confidence,
                    save=False,
                ):
                    relation_count += 1

        # 3. Connect each paper node to the concepts found in this run that its
        #    own title or abstract mentions — not to the same first six for
        #    every paper, which made unrelated papers look connected.
        for paper in papers:
            own_text = f"{paper.get('title', '')}\n{paper.get('abstract', '')}"
            linked = [c for c in added_concepts if mentions(c, own_text)]
            for concept in linked[:MAX_PAPER_CONCEPTS]:
                graph.add_relation(paper["title"], "PART_OF", concept, 0.6, save=False)

        # 4. An uploaded document is a paper too. It used to add only its
        #    concepts, so the graph could not say which paper a concept came
        #    from, and a concept no other concept named floated unattached.
        if ctx.document_id and ctx.retrieved_chunks and added_concepts:
            first = ctx.retrieved_chunks[0]
            title = first.get("title") or first.get("document_name") or ""
            if title:
                graph.add_entity(title, "Paper", first.get("document_name", ""), save=False)
                for concept in added_concepts[:MAX_DOCUMENT_CONCEPTS]:
                    graph.add_relation(title, "PART_OF", concept, 0.8, save=False)

        graph.save()
        after = graph.stats()

        ctx.intermediate_results["graph_stats"] = after
        ctx.log(
            self.name,
            f"Graph now has {after['nodes']} nodes / {after['edges']} edges "
            f"(+{after['nodes'] - before['nodes']} nodes, "
            f"+{after['edges'] - before['edges']} edges)",
            self.stage,
        )
        return ctx
