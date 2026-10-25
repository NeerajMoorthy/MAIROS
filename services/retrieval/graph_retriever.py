"""Knowledge-graph retrieval over the NetworkX store.

Replaces the earlier Neo4j/Cypher implementation: mid-review MAIROS has no
graph server, and the previous class silently failed on every call. The public
surface (``search``) is unchanged so a Neo4j backend can be reinstated later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.common.text import normalize_name
from services.knowledge_graph.networkx_store import kg_store


@dataclass
class GraphResult:
    """A relation found by traversing the knowledge graph."""

    entity: str
    relation: str
    related_entity: str
    chunk_ids: list[str] = field(default_factory=list)
    score: float = 1.0


class GraphRetriever:
    """Find entities and relations related to a query.

    Args:
        project_id: Which project's graph to traverse.
        store: Override the graph registry (used in tests).
    """

    def __init__(self, project_id: str | None = None, store=None):
        self.project_id = project_id
        self.store = store or kg_store

    # ------------------------------------------------------------------
    def link_entities(self, query: str, limit: int = 8) -> list[str]:
        """Entities from the graph that appear in the query text."""
        return self.store.for_project(self.project_id).match_entities(query, limit)

    def search(
        self,
        entities: list[str] | None = None,
        query: str | None = None,
        depth: int = 2,
        limit: int = 50,
    ) -> list[GraphResult]:
        """Return relations reachable from *entities* (or linked from *query*)."""
        graph_obj = self.store.for_project(self.project_id)
        graph = graph_obj.graph

        # Caller-supplied names are normalised the way the graph stores them,
        # or a typographic hyphen would make a known entity look unknown.
        seeds = [normalize_name(entity) for entity in entities or [] if normalize_name(entity)]
        if not seeds and query:
            seeds = self.link_entities(query)
        if not seeds:
            return []

        results: list[GraphResult] = []
        seen: set[tuple[str, str, str]] = set()

        for seed in seeds:
            if not graph.has_node(seed):
                continue
            for related in graph_obj.neighbors(seed, depth=depth):
                if graph.has_edge(seed, related):
                    data = graph.edges[seed, related]
                    subject, obj = seed, related
                elif graph.has_edge(related, seed):
                    data = graph.edges[related, seed]
                    subject, obj = related, seed
                else:
                    data, subject, obj = {}, seed, related

                relation = data.get("relation", "RELATED_TO")
                key = (subject, relation, obj)
                if key in seen:
                    continue
                seen.add(key)

                chunk_ids = list(graph.nodes[related].get("source_chunk_ids", []))
                chunk_ids += list(graph.nodes[seed].get("source_chunk_ids", []))

                results.append(
                    GraphResult(
                        entity=subject,
                        relation=relation,
                        related_entity=obj,
                        chunk_ids=sorted(set(chunk_ids)),
                        score=float(data.get("confidence", 1.0)),
                    )
                )
                if len(results) >= limit:
                    return results

        return results

    def close(self) -> None:  # API parity with the old Neo4j driver
        return None
