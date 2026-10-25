"""Knowledge-graph service — entity/relation extraction and NetworkX storage."""

from .entity_extractor import (
    EntityRelationExtractor,
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
)
from .networkx_store import KnowledgeGraphStore, ProjectGraph, kg_store

__all__ = [
    "EntityRelationExtractor",
    "ExtractedEntity",
    "ExtractedRelation",
    "ExtractionResult",
    "KnowledgeGraphStore",
    "ProjectGraph",
    "kg_store",
]
