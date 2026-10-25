"""Dependency injection for FastAPI routes.

Routers import these functions directly, so overrides must work *inside* the
function rather than by rebinding the name — hence the explicit override slots
used by the test suite.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import settings
from services.retrieval.vector_store import ChromaStore

# Test/bootstrap overrides. Set via ``set_chroma_store`` / ``set_orchestrator``.
_chroma_override: ChromaStore | None = None
_orchestrator_override = None


@lru_cache(maxsize=1)
def _build_chroma_store() -> ChromaStore:
    return ChromaStore(
        persist_dir=str(settings.chroma_persist_dir),
        collection_name=settings.chroma_collection,
    )


def get_chroma_store() -> ChromaStore:
    """Singleton ChromaDB store (loading the embedder is expensive)."""
    return _chroma_override or _build_chroma_store()


@lru_cache(maxsize=1)
def _build_generation_service():
    from services.generation.llm import GenerationService

    return GenerationService()


def get_generation_service():
    """Singleton grounded-answer generator."""
    return _build_generation_service()


@lru_cache(maxsize=1)
def _build_orchestrator():
    from services.agents.orchestrator import AgentOrchestrator

    return AgentOrchestrator(
        chroma_store=get_chroma_store(),
        top_k=settings.default_top_k,
    )


def get_orchestrator():
    """Singleton multi-agent orchestrator, wired to the vector store.

    Built once so every agent shares one LLM client and one embedding model
    instead of re-creating them per request.
    """
    return _orchestrator_override or _build_orchestrator()


# ---------------------------------------------------------------------------
# Test hooks
# ---------------------------------------------------------------------------
def set_chroma_store(store: ChromaStore | None) -> None:
    """Force a specific vector store (used by tests)."""
    global _chroma_override
    _chroma_override = store
    _build_orchestrator.cache_clear()


def set_orchestrator(orchestrator) -> None:
    """Force a specific orchestrator (used by tests)."""
    global _orchestrator_override
    _orchestrator_override = orchestrator


def reset_chroma_store() -> None:
    """Clear cached singletons and overrides."""
    global _chroma_override, _orchestrator_override
    _chroma_override = None
    _orchestrator_override = None
    _build_chroma_store.cache_clear()
    _build_generation_service.cache_clear()
    _build_orchestrator.cache_clear()


# Backwards-compatible alias
reset_singletons = reset_chroma_store
