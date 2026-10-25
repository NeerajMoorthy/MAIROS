"""ChromaDB-backed vector store for chunk indexing and retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RetrievedChunk:
    """A chunk returned from retrieval with its relevance score."""

    chunk_id: str
    document_id: str
    document_name: str
    text: str
    score: float
    page: int | None = None
    metadata: dict = field(default_factory=dict)


class ChromaStore:
    """Index and query text chunks using an embedded ChromaDB instance.

    Runs fully local — no server, no Docker. Embeddings are produced by
    sentence-transformers ``all-MiniLM-L6-v2``.

    Args:
        persist_dir: Directory for persistent storage.
        collection_name: Chroma collection to use.
        embedding_function: Override the embedder (tests inject a fake).
    """

    def __init__(
        self,
        persist_dir: str | Path | None = None,
        collection_name: str = "mairos_chunks",
        embedding_function=None,
    ):
        if persist_dir is None:
            from app.config import settings

            persist_dir = settings.chroma_persist_dir

        self.persist_dir = str(persist_dir)
        self.collection_name = collection_name
        self._client = None
        self._collection = None
        self._embedding_function = embedding_function

    # ------------------------------------------------------------------
    @property
    def embedding_function(self):
        """Lazily build the embedder (avoids a model download at import)."""
        if self._embedding_function is None:
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )

            # Explicit sentence-transformers avoids Chroma's ONNX download path,
            # which has been known to hang behind proxies on Windows.
            self._embedding_function = SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
        return self._embedding_function

    @property
    def client(self):
        """Lazy-initialise the persistent client."""
        if self._client is None:
            import chromadb

            Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self.persist_dir)
        return self._client

    @property
    def collection(self):
        """Get or create the target collection."""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=self.embedding_function,
            )
        return self._collection

    # ------------------------------------------------------------------
    def add_chunks(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
    ) -> int:
        """Upsert text chunks; ChromaDB embeds them automatically."""
        if not ids:
            return 0

        clean_meta = [
            {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))}
            for meta in metadatas
        ]

        # Chroma rejects oversized single batches; chunk the upsert.
        batch = 256
        for start in range(0, len(ids), batch):
            self.collection.upsert(
                ids=ids[start : start + batch],
                documents=documents[start : start + batch],
                metadatas=clean_meta[start : start + batch],
            )
        return len(ids)

    def add_texts(
        self,
        texts: list[str],
        metadatas: list[dict],
        id_prefix: str = "text",
    ) -> int:
        """Index arbitrary texts (e.g. fetched abstracts) with generated IDs."""
        ids = [f"{id_prefix}_{i}" for i in range(len(texts))]
        return self.add_chunks(ids, texts, metadatas)

    # ------------------------------------------------------------------
    def query(
        self,
        query_text: str,
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[RetrievedChunk]:
        """Return the *top_k* chunks most similar to *query_text*."""
        if not query_text or not query_text.strip():
            return []

        kwargs: dict = {
            "query_texts": [query_text],
            "n_results": max(1, top_k),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = self.collection.query(**kwargs)
        except Exception as exc:
            print(f"[chroma] query failed: {exc}")
            return []

        chunks: list[RetrievedChunk] = []
        if not results or not results.get("ids") or not results["ids"][0]:
            return chunks

        for idx, chunk_id in enumerate(results["ids"][0]):
            meta = (results.get("metadatas") or [[{}]])[0][idx] or {}
            distance = (results.get("distances") or [[0.0]])[0][idx]
            doc_text = (results.get("documents") or [[""]])[0][idx] or ""

            page_val = meta.get("page")
            try:
                page = int(page_val) if page_val is not None else None
            except (TypeError, ValueError):
                page = None
            if page is not None and page < 0:
                page = None

            chunks.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    document_id=str(meta.get("document_id", "")),
                    document_name=str(meta.get("document_name", "")),
                    text=doc_text,
                    score=round(1.0 - float(distance), 4),
                    page=page,
                    metadata=dict(meta),
                )
            )

        return chunks

    def get_document_text(self, document_id: str, limit: int = 60) -> list[dict]:
        """Return a document's chunks in original order (for analysis)."""
        try:
            got = self.collection.get(
                where={"document_id": document_id},
                include=["documents", "metadatas"],
                limit=limit,
            )
        except Exception as exc:
            print(f"[chroma] get failed: {exc}")
            return []

        rows = [
            {
                "chunk_id": cid,
                "text": doc,
                "document_name": (meta or {}).get("document_name", ""),
                "page": (meta or {}).get("page"),
                "chunk_index": (meta or {}).get("chunk_index", 0),
            }
            for cid, doc, meta in zip(
                got.get("ids", []),
                got.get("documents", []),
                got.get("metadatas", []),
            )
        ]
        rows.sort(key=lambda r: r.get("chunk_index") or 0)
        return rows

    def all_chunks(self, project_id: str | None = None, limit: int | None = 2000) -> list[dict]:
        """Every indexed chunk, optionally scoped to one project.

        Used by the evaluation harness to count how many passages actually
        satisfy a test case — Recall@k needs a true denominator, not a guess —
        and by the project export, which passes ``limit=None`` because an
        export that silently stopped at 2,000 chunks would be incomplete
        without saying so.
        """
        try:
            got = self.collection.get(
                where={"project_id": project_id} if project_id else None,
                include=["documents", "metadatas"],
                limit=limit,
            )
        except Exception as exc:
            print(f"[chroma] corpus scan failed: {exc}")
            return []

        return [
            {
                "chunk_id": cid,
                "text": doc or "",
                "document_id": (meta or {}).get("document_id", ""),
                "document_name": (meta or {}).get("document_name", ""),
                "page": (meta or {}).get("page"),
                "chunk_index": (meta or {}).get("chunk_index"),
                "source": (meta or {}).get("source", ""),
            }
            for cid, doc, meta in zip(
                got.get("ids", []),
                got.get("documents", []),
                got.get("metadatas", []),
            )
        ]

    # ------------------------------------------------------------------
    def count(self, project_id: str | None = None) -> int:
        """Number of indexed chunks, for one project or the whole collection.

        ``collection.count()`` cannot filter, so a project-scoped count has to
        fetch the matching ids. Without this, every project reports the same
        global total.
        """
        try:
            if project_id is None:
                return self.collection.count()
            got = self.collection.get(where={"project_id": project_id}, include=[])
            return len(got.get("ids", []))
        except Exception as exc:
            print(f"[chroma] count failed: {exc}")
            return 0

    def delete_documents(self, project_id: str, document_ids) -> None:
        """Remove one project's chunks for the given documents.

        Used before re-indexing a fetched paper, so its earlier copies in this
        project — under an older id scheme, or another of its identifiers — are
        replaced rather than kept beside the new one. Other projects' chunks
        are never touched. Failures escape, like :meth:`delete_project`.
        """
        ids = sorted({str(d) for d in document_ids if d})
        if not project_id or not ids:
            return
        self.collection.delete(
            where={"$and": [{"project_id": project_id}, {"document_id": {"$in": ids}}]}
        )

    def delete_project(self, project_id: str) -> None:
        """Remove every indexed chunk owned by a project.

        Unlike read helpers, this intentionally lets storage failures escape so
        the project deletion endpoint can keep the project record and report a
        retryable error instead of silently orphaning its indexed content.
        """
        if not project_id:
            raise ValueError("project_id is required")
        self.collection.delete(where={"project_id": project_id})

    def reset(self) -> None:
        """Delete and recreate the collection (tests / demo reset)."""
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = None
