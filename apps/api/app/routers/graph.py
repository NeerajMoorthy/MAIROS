"""Graph router — expose the knowledge graph as JSON for the frontend."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.store import metadata_store
from schemas import GraphResponse
from services.knowledge_graph.networkx_store import kg_store

router = APIRouter(tags=["graph"])


@router.get("/projects/{project_id}/graph", response_model=GraphResponse)
async def get_project_graph(project_id: str, min_mentions: int = 1) -> GraphResponse:
    """Return this project's knowledge graph in react-force-graph shape.

    Args:
        min_mentions: Drop nodes mentioned fewer times than this (declutters
            a large graph without rebuilding it).
    """
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    data = kg_store.for_project(project_id).to_json()

    if min_mentions > 1:
        keep = {n["id"] for n in data["nodes"] if n.get("mentions", 1) >= min_mentions}
        data["nodes"] = [n for n in data["nodes"] if n["id"] in keep]
        data["links"] = [
            l for l in data["links"] if l["source"] in keep and l["target"] in keep
        ]

    return GraphResponse(**data)


@router.get("/projects/{project_id}/graph/neighbors/{entity}")
async def get_neighbors(project_id: str, entity: str, depth: int = 1) -> dict:
    """Entities within *depth* hops of a node — powers node click-through."""
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    graph = kg_store.for_project(project_id)
    if not graph.graph.has_node(entity):
        raise HTTPException(status_code=404, detail="Entity not found in graph")

    return {
        "entity": entity,
        "type": graph.graph.nodes[entity].get("type", "Concept"),
        "description": graph.graph.nodes[entity].get("description", ""),
        "neighbors": sorted(graph.neighbors(entity, depth=depth)),
    }


@router.delete("/projects/{project_id}/graph", status_code=204)
async def clear_graph(project_id: str) -> None:
    """Reset a project's graph (handy between demo runs)."""
    if not metadata_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    kg_store.for_project(project_id).clear()
