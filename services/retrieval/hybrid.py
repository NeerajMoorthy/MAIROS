"""Hybrid retrieval — dense vector search fused with graph traversal."""

from __future__ import annotations

from .graph_retriever import GraphRetriever, GraphResult
from .vector_store import ChromaStore, RetrievedChunk


class HybridRetriever:
    """Combine ChromaDB dense search with knowledge-graph expansion.

    Vector hits are scored by Reciprocal Rank Fusion; a chunk that is also
    reachable in the knowledge graph gets a multiplicative boost. An optional
    cross-encoder re-ranks the fused list.
    """

    def __init__(
        self,
        vector: ChromaStore | None = None,
        graph: GraphRetriever | None = None,
        reranker=None,
        rrf_k: int = 60,
        graph_boost: float = 1.5,
    ):
        self.vector = vector or ChromaStore()
        self.graph = graph
        self.reranker = reranker
        self.rrf_k = rrf_k
        self.graph_boost = graph_boost

    def retrieve(
        self,
        query: str,
        project_id: str | None = None,
        entities: list[str] | None = None,
        top_k: int = 5,
    ) -> tuple[list[RetrievedChunk], list[GraphResult]]:
        """Return ``(fused_chunks, graph_relations)`` for *query*."""
        where = {"project_id": project_id} if project_id else None
        vector_results = self.vector.query(query, top_k=max(top_k * 2, 10), where=where)

        graph_results: list[GraphResult] = []
        graph_chunk_ids: set[str] = set()

        retriever = self.graph or (GraphRetriever(project_id) if project_id else None)
        if retriever is not None:
            graph_results = retriever.search(entities=entities, query=query)
            for gr in graph_results:
                graph_chunk_ids.update(gr.chunk_ids)

        for rank, chunk in enumerate(vector_results):
            score = 1.0 / (self.rrf_k + rank + 1)
            # A graph source id is usually a chunk id. For a fetched abstract
            # it is the document id: the Literature agent hands the graph each
            # abstract whole, under its document id, while the Indexer stores
            # it split into `<document id>_0`, `_1`, … — so a chunk-id match
            # alone never fired, and a live run used 21 graph relations to
            # boost 0 passages. Citing the document boosts each of its chunks.
            if chunk.chunk_id in graph_chunk_ids or chunk.document_id in graph_chunk_ids:
                score *= self.graph_boost
                chunk.metadata = {**chunk.metadata, "graph_hit": True}
            chunk.score = round(score, 6)

        fused = sorted(vector_results, key=lambda c: c.score, reverse=True)

        if self.reranker:
            fused = self.reranker.rerank(query, fused, top_k=top_k)

        return fused[:top_k], graph_results
