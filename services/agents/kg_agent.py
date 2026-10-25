"""Knowledge Graph Agent — turns processed text into nodes and edges."""

from __future__ import annotations

from services.knowledge_graph.entity_extractor import EntityRelationExtractor
from services.knowledge_graph.networkx_store import kg_store

from .base import AgentContext, BaseAgent


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

        if text.strip() and self.llm is not None:
            result = self.extractor.extract(text)
            if result.problem:
                # Recorded as its own event so a run that adds less than it
                # should to the graph says why, rather than only "+0 nodes".
                summary = "was incomplete" if result.entities else "produced nothing"
                ctx.log(self.name, f"Entity extraction {summary}: {result.problem}", self.stage)

            # Link entities back to the chunks they came from, so graph hits can
            # boost vector retrieval later.
            chunk_ids = [c.get("chunk_id") for c in ctx.retrieved_chunks if c.get("chunk_id")]

            for entity in result.entities:
                added = graph.add_entity(
                    entity.name,
                    entity.type,
                    entity.description,
                    source_chunk_ids=chunk_ids[:10],
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

        # 3. Connect each paper node to the concepts found in this run.
        for paper in papers:
            for concept in added_concepts[:6]:
                graph.add_relation(paper["title"], "PART_OF", concept, 0.6, save=False)

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
