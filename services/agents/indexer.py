"""Indexer + Loader agents — the bridge between agents and the vector store.

``IndexerAgent`` writes freshly retrieved papers into ChromaDB so they become
answerable by the RAG pipeline (step 3 of the demo flow).
``LoaderAgent`` does the reverse: pulls an uploaded document's chunks back out
so the Analysis agent has text to work with.
``RetrieverAgent`` runs hybrid retrieval for the question-answering flow.
"""

from __future__ import annotations

from .base import AgentContext, BaseAgent


class IndexerAgent(BaseAgent):
    """Chunk and embed retrieved papers into ChromaDB."""

    name = "indexer"
    stage = "embedding"

    async def run(self, ctx: AgentContext) -> AgentContext:
        papers = ctx.intermediate_results.get("retrieved_papers", [])
        if not papers or ctx.chroma_store is None:
            ctx.log(self.name, "Nothing new to index", self.stage)
            return ctx

        from services.ingestion.chunker import RecursiveChunker
        from services.literature import document_id_for

        chunker = RecursiveChunker(chunk_size=512, chunk_overlap=64)
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []

        for paper in papers:
            doc_id = document_id_for(paper)
            body = (
                f"Title: {paper['title']}\n"
                f"Authors: {', '.join(paper.get('authors', []))}\n\n"
                f"{paper.get('abstract', '')}"
            )
            for chunk in chunker.chunk(
                body, page=1, document_id=doc_id, document_name=paper["title"]
            ):
                ids.append(f"{doc_id}_{chunk.index}")
                documents.append(chunk.text)
                metadatas.append(
                    {
                        "document_id": doc_id,
                        "document_name": paper["title"],
                        "project_id": ctx.project_id or "default",
                        "page": 1,
                        "chunk_index": chunk.index,
                        "source": paper.get("source") or "arXiv",
                        "url": paper.get("url", ""),
                        "year": paper.get("year", ""),
                    }
                )

        indexed = ctx.chroma_store.add_chunks(ids, documents, metadatas)
        ctx.intermediate_results["indexed_chunks"] = indexed
        ctx.log(
            self.name,
            f"Embedded {indexed} chunks from {len(papers)} papers into ChromaDB",
            self.stage,
        )
        return ctx


class LoaderAgent(BaseAgent):
    """Load an uploaded document's chunks out of ChromaDB."""

    name = "loader"
    stage = "extracting"

    async def run(self, ctx: AgentContext) -> AgentContext:
        if ctx.retrieved_chunks:
            ctx.log(self.name, "Document text already present in context", self.stage)
            return ctx

        if ctx.chroma_store is None or not ctx.document_id:
            ctx.log(self.name, "No document to load", self.stage, "failed")
            return ctx

        rows = ctx.chroma_store.get_document_text(ctx.document_id, limit=60)
        ctx.retrieved_chunks = rows
        ctx.log(
            self.name,
            f"Loaded {len(rows)} chunks for document {ctx.document_id[:8]}…",
            self.stage,
        )
        return ctx


class RetrieverAgent(BaseAgent):
    """Hybrid retrieval (vector + knowledge graph) for the RAG flow."""

    name = "retriever"
    stage = "retrieving"

    def __init__(self, llm=None, top_k: int = 5):
        super().__init__(llm=llm)
        self.top_k = top_k

    async def run(self, ctx: AgentContext) -> AgentContext:
        if ctx.chroma_store is None:
            ctx.log(self.name, "No vector store available", self.stage, "failed")
            return ctx

        from services.retrieval.hybrid import HybridRetriever

        retriever = HybridRetriever(vector=ctx.chroma_store)
        chunks, graph_results = retriever.retrieve(
            ctx.focus_text(), project_id=ctx.project_id, top_k=self.top_k
        )

        ctx.retrieved_chunks = [
            {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "document_name": c.document_name,
                "page": c.page,
                "text": c.text,
                "score": c.score,
                "graph_hit": bool(c.metadata.get("graph_hit")),
            }
            for c in chunks
        ]
        ctx.graph_results = [
            {
                "entity": g.entity,
                "relation": g.relation,
                "related_entity": g.related_entity,
            }
            for g in graph_results
        ]

        boosted = sum(1 for c in ctx.retrieved_chunks if c["graph_hit"])
        detail = f"{len(chunks)} chunks retrieved"
        if graph_results:
            detail += f"; {len(graph_results)} graph relations used ({boosted} chunks boosted)"
        ctx.log(self.name, detail, self.stage)
        return ctx
