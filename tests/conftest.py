"""Shared test fixtures.

Tests run fully offline: no LLM key, no model download, no network. The
embedding function and the LLM are both replaced with deterministic fakes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap — same one the app uses.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "apps" / "api"))
from app import bootstrap  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Deterministic embedding function (no HuggingFace download)
# ---------------------------------------------------------------------------
class HashingEmbeddingFunction:
    """Cheap bag-of-words hashing embedder.

    Unlike a constant vector, this preserves relative similarity, so retrieval
    tests actually assert on ranking rather than on arbitrary order.
    """

    DIM = 128

    def __call__(self, input: list[str]) -> list[list[float]]:
        vectors = []
        for text in input:
            vec = [0.0] * self.DIM
            for token in str(text).lower().split():
                vec[hash(token) % self.DIM] += 1.0
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    def name(self) -> str:  # Chroma >= 1.x requires this
        return "hashing-test-embedder"

    @staticmethod
    def build_from_config(config):
        return HashingEmbeddingFunction()

    def get_config(self):
        return {}

    def embed_query(self, input):
        return self(input if isinstance(input, list) else [input])

    def embed_documents(self, input):
        return self(input)


@pytest.fixture()
def embedding_function() -> HashingEmbeddingFunction:
    return HashingEmbeddingFunction()


# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    """Force the deterministic offline model everywhere, with no API key."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    from app.config import settings
    from services.generation import provider

    monkeypatch.setattr(settings, "groq_api_key", "", raising=False)
    monkeypatch.setattr(settings, "allow_offline_llm", True, raising=False)
    # Agent runs complete inside the request, so a test can read a finished
    # task on the next line (see `dispatch_pipeline`).
    monkeypatch.setattr(settings, "run_tasks_inline", True, raising=False)
    # Local single-user mode unless a test turns authentication on itself.
    monkeypatch.setattr(settings, "auth_jwks_url", "", raising=False)
    monkeypatch.setattr(settings, "database_url", "", raising=False)
    provider.reset_provider_cache()
    yield
    provider.reset_provider_cache()


class _NoNetworkClient:
    """Stands in for ``httpx.AsyncClient``: every request fails to connect.

    The literature sources degrade to "could not be reached" when this
    happens, which is exactly the offline behaviour the suite should see. A
    test that needs a response patches ``httpx.AsyncClient`` itself, which
    overrides this.
    """

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        import httpx

        raise httpx.ConnectError("network access is disabled in tests")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test reaches arXiv, OpenAlex or Semantic Scholar."""
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _NoNetworkClient)


# ---------------------------------------------------------------------------
# Sample PDF
# ---------------------------------------------------------------------------
@pytest.fixture()
def sample_pdf(tmp_path: Path) -> Path:
    """A real 2-page PDF with known content."""
    import fitz  # PyMuPDF

    pdf_path = tmp_path / "test_paper.pdf"
    doc = fitz.open()

    page1 = doc.new_page(width=595, height=842)
    page1.insert_text(
        (72, 100),
        "Transformers and Attention Mechanisms\n\n"
        "The transformer architecture relies on self-attention to process "
        "sequences in parallel. Unlike recurrent neural networks, transformers "
        "do not require sequential computation, enabling significantly faster "
        "training on modern hardware. Self-attention computes query, key, and "
        "value projections for each token, allowing the model to weigh the "
        "relevance of all positions simultaneously.",
        fontsize=11,
    )

    page2 = doc.new_page(width=595, height=842)
    page2.insert_text(
        (72, 100),
        "Retrieval-Augmented Generation\n\n"
        "Retrieval-augmented generation combines a retrieval component with a "
        "language model to ground responses in external knowledge. By retrieving "
        "relevant passages from a corpus before generating an answer, RAG systems "
        "reduce hallucination and improve factual accuracy. The retrieval step "
        "typically uses dense vector similarity search over an embedding index.",
        fontsize=11,
    )

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


# ---------------------------------------------------------------------------
# Isolated ChromaDB store
# ---------------------------------------------------------------------------
@pytest.fixture()
def chroma_store(tmp_path: Path, embedding_function):
    from services.retrieval.vector_store import ChromaStore

    return ChromaStore(
        persist_dir=str(tmp_path / "chroma_test"),
        collection_name="test_collection",
        embedding_function=embedding_function,
    )


# ---------------------------------------------------------------------------
# FastAPI TestClient with isolated storage
# ---------------------------------------------------------------------------
@pytest.fixture()
def client(tmp_path: Path, monkeypatch, embedding_function):
    from app import dependencies as deps
    from app.config import settings
    from app.store import metadata_store
    from services.knowledge_graph.networkx_store import kg_store

    monkeypatch.setattr(settings, "data_dir", tmp_path, raising=False)
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads", raising=False)
    monkeypatch.setattr(settings, "chroma_persist_dir", tmp_path / "chroma", raising=False)
    monkeypatch.setattr(settings, "graph_dir", tmp_path / "graphs", raising=False)
    monkeypatch.setattr(settings, "state_file", tmp_path / "state.json", raising=False)
    monkeypatch.setattr(settings, "database_file", tmp_path / "mairos.db", raising=False)

    deps.reset_chroma_store()
    metadata_store.clear()
    # Every test gets its own database file, so nothing leaks between tests and
    # the persistence path is genuinely exercised rather than stubbed out.
    metadata_store._state_file = tmp_path / "state.json"
    metadata_store.use_database(tmp_path / "mairos.db")
    metadata_store._loaded = True  # the fresh file has nothing to restore
    kg_store.reset()
    kg_store._base_dir = tmp_path / "graphs"

    # Inject the fake embedder into the singleton store.
    from services.retrieval.vector_store import ChromaStore

    deps.set_chroma_store(
        ChromaStore(
            persist_dir=str(tmp_path / "chroma"),
            collection_name="test_collection",
            embedding_function=embedding_function,
        )
    )

    from fastapi.testclient import TestClient

    from app.middleware import RateLimitMiddleware
    from main import app

    # Every test shares the "testclient" address, so without this the write
    # budget would be spent partway through the session and later tests would
    # fail on 429s that have nothing to do with what they assert. The limiter
    # itself is exercised deliberately in tests/test_security.py.
    RateLimitMiddleware.reset_all()

    with TestClient(app) as test_client:
        RateLimitMiddleware.reset_all()
        yield test_client

    deps.reset_chroma_store()
    metadata_store.clear()
    kg_store.reset()
