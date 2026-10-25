"""NetworkX-backed knowledge graph store.

One directed graph per project, persisted as JSON. NetworkX is more than
enough at mid-review scale and needs no external service; the store exposes a
narrow interface (``add_entity`` / ``add_relation`` / ``to_json`` / ``neighbors``)
so it can be swapped for Neo4j later without touching agent code.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Iterable

import networkx as nx

from services.common.text import normalize_name

# ---------------------------------------------------------------------------
# networkx >= 3.4 changed the default `edges` key in node_link_data/graph and
# emits a FutureWarning unless it is passed explicitly. Detect support once.
# ---------------------------------------------------------------------------
try:
    _NODE_LINK_KW = {"edges": "links"}
    nx.node_link_data(nx.DiGraph(), **_NODE_LINK_KW)
except TypeError:  # pragma: no cover - networkx < 3.4
    _NODE_LINK_KW = {}


def _slug(value: str) -> str:
    """Filesystem-safe identifier."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in value)[:64] or "default"


class ProjectGraph:
    """A single project's knowledge graph."""

    def __init__(self, project_id: str, persist_path: Path):
        self.project_id = project_id
        self.persist_path = Path(persist_path)
        self.graph = nx.DiGraph()
        self._lock = threading.Lock()
        self._load()

    # -- persistence ----------------------------------------------------
    def _load(self) -> None:
        if not self.persist_path.exists():
            return
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            self.graph = nx.node_link_graph(
                data, directed=True, multigraph=False, **_NODE_LINK_KW
            )
        except Exception as exc:  # corrupt file should never break startup
            print(f"[kg] could not load {self.persist_path}: {exc}")
            self.graph = nx.DiGraph()
            return
        self.graph = self._with_normalized_names(self.graph)

    @staticmethod
    def _with_normalized_names(graph: nx.DiGraph) -> nx.DiGraph:
        """Fold node names written before names were normalised.

        Graphs saved earlier can hold "retrieval‑augmented" (U+2011) beside
        "retrieval-augmented". Those are one concept, so they become one node:
        mentions are summed, source chunks merged, and the first non-empty
        description and type kept. Edges are carried over between the folded
        names; one that would now join a node to itself is dropped. A graph
        with nothing to fold is returned unchanged.
        """
        if all(normalize_name(node) == node for node in graph.nodes):
            return graph

        merged = nx.DiGraph()
        for node, data in graph.nodes(data=True):
            name = normalize_name(node)
            if not name:
                continue
            if not merged.has_node(name):
                merged.add_node(name, **dict(data))
                continue
            target = merged.nodes[name]
            target["mentions"] = target.get("mentions", 1) + data.get("mentions", 1)
            target["source_chunk_ids"] = sorted(
                set(target.get("source_chunk_ids", [])) | set(data.get("source_chunk_ids", []))
            )
            if not target.get("description") and data.get("description"):
                target["description"] = data["description"]
            if target.get("type") in (None, "", "Unknown") and data.get("type"):
                target["type"] = data["type"]

        for source, target, data in graph.edges(data=True):
            a, b = normalize_name(source), normalize_name(target)
            if a and b and a != b:
                merged.add_edge(a, b, **dict(data))
        return merged

    def save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self.graph, **_NODE_LINK_KW)
        tmp = self.persist_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.persist_path)

    # -- mutation -------------------------------------------------------
    def add_entity(
        self,
        name: str,
        type_: str = "Concept",
        description: str = "",
        source_chunk_ids: Iterable[str] | None = None,
        *,
        save: bool = True,
        count_mention: bool = True,
    ) -> str | None:
        """Add or merge an entity node. Returns the canonical node id.

        Args:
            count_mention: Increment ``mentions`` when the node already exists.
                Pass ``False`` for structural touches (auto-creating the
                endpoint of a relation, for example). ``mentions`` is supposed
                to mean "how often the corpus talks about this", and gap
                detection reads it that way — every internal touch that bumps
                it makes a thinly-covered concept look well covered.

        Names are normalised (``services/common/text.py``) so a model's
        typographic hyphen and an ASCII one name the same node.
        """
        name = normalize_name(name)
        if not name or len(name) > 120:
            return None

        with self._lock:
            if self.graph.has_node(name):
                node = self.graph.nodes[name]
                if count_mention:
                    node["mentions"] = node.get("mentions", 1) + 1
                if description and not node.get("description"):
                    node["description"] = description
                if type_ and node.get("type") in (None, "", "Unknown"):
                    node["type"] = type_
                if source_chunk_ids:
                    existing = set(node.get("source_chunk_ids", []))
                    existing.update(source_chunk_ids)
                    node["source_chunk_ids"] = sorted(existing)
            else:
                self.graph.add_node(
                    name,
                    type=type_ or "Concept",
                    description=description or "",
                    mentions=1,
                    source_chunk_ids=sorted(set(source_chunk_ids or [])),
                )

        if save:
            self.save()
        return name

    def add_relation(
        self,
        subject: str,
        relation: str,
        object_: str,
        confidence: float = 1.0,
        *,
        save: bool = True,
    ) -> bool:
        """Add a directed, typed edge between two entities."""
        subject = normalize_name(subject)
        object_ = normalize_name(object_)
        if not subject or not object_ or subject == object_:
            return False

        # Create the endpoints if they are new, but never inflate the mention
        # count of one that already exists — drawing an edge is not a mention.
        self.add_entity(subject, "Unknown", save=False, count_mention=False)
        self.add_entity(object_, "Unknown", save=False, count_mention=False)

        with self._lock:
            self.graph.add_edge(
                subject,
                object_,
                relation=(relation or "RELATED_TO").upper().replace(" ", "_"),
                confidence=float(confidence),
            )

        if save:
            self.save()
        return True

    def add_paper(self, title: str, authors: Iterable[str], url: str = "") -> None:
        """Add a paper node plus AUTHORED_BY edges — used by both flows."""
        title = (title or "").strip()
        if not title:
            return
        self.add_entity(title, "Paper", description=url, save=False)
        for author in list(authors or [])[:8]:
            self.add_entity(author, "Person", save=False)
            self.add_relation(title, "AUTHORED_BY", author, save=False)
        self.save()

    # -- queries --------------------------------------------------------
    def neighbors(self, name: str, depth: int = 1) -> set[str]:
        """Entities within *depth* hops of *name* (both directions)."""
        name = normalize_name(name)
        if not self.graph.has_node(name):
            return set()
        undirected = self.graph.to_undirected(as_view=True)
        try:
            lengths = nx.single_source_shortest_path_length(
                undirected, name, cutoff=depth
            )
        except Exception:
            return set()
        return {n for n in lengths if n != name}

    def match_entities(self, text: str, limit: int = 10) -> list[str]:
        """Entity names that literally appear in *text* (cheap linking)."""
        # Normalised too: a question pasted from a PDF carries the same
        # typographic hyphens a model writes.
        lowered = normalize_name(text).lower()
        hits = [n for n in self.graph.nodes if len(n) > 3 and n.lower() in lowered]
        hits.sort(key=lambda n: -self.graph.nodes[n].get("mentions", 1))
        return hits[:limit]

    def stats(self) -> dict:
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
        }

    def to_json(self) -> dict:
        """Export in react-force-graph shape: ``{nodes: [...], links: [...]}``."""
        data = nx.node_link_data(self.graph, **_NODE_LINK_KW)

        nodes = [
            {
                "id": n["id"],
                "name": n["id"],
                "group": n.get("type", "Concept"),
                "description": n.get("description", ""),
                "mentions": n.get("mentions", 1),
                "val": 1 + min(n.get("mentions", 1), 8),
            }
            for n in data.get("nodes", [])
        ]

        links = [
            {
                "source": link["source"],
                "target": link["target"],
                "label": link.get("relation", "RELATED_TO"),
                "confidence": link.get("confidence", 1.0),
            }
            for link in data.get("links", data.get("edges", []))
        ]

        return {"nodes": nodes, "links": links, "stats": self.stats()}

    def clear(self) -> None:
        with self._lock:
            self.graph = nx.DiGraph()
        self.save()


class KnowledgeGraphStore:
    """Registry of per-project graphs."""

    def __init__(self, base_dir: str | Path | None = None):
        self._base_dir = Path(base_dir) if base_dir else None
        self._graphs: dict[str, ProjectGraph] = {}
        self._lock = threading.Lock()

    @property
    def base_dir(self) -> Path:
        if self._base_dir is None:
            from app.config import settings

            self._base_dir = Path(settings.graph_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        return self._base_dir

    def for_project(self, project_id: str | None) -> ProjectGraph:
        """Get (or create) the graph belonging to *project_id*."""
        pid = project_id or "default"
        with self._lock:
            if pid not in self._graphs:
                path = self.base_dir / f"{_slug(pid)}.json"
                self._graphs[pid] = ProjectGraph(pid, path)
            return self._graphs[pid]

    # Convenience pass-throughs -----------------------------------------
    def add_entity(self, project_id: str, *args, **kwargs):
        return self.for_project(project_id).add_entity(*args, **kwargs)

    def add_relation(self, project_id: str, *args, **kwargs):
        return self.for_project(project_id).add_relation(*args, **kwargs)

    def to_json(self, project_id: str) -> dict:
        return self.for_project(project_id).to_json()

    def delete_project(self, project_id: str) -> None:
        """Remove a project's cached graph and its persisted JSON file."""
        if not project_id:
            raise ValueError("project_id is required")

        with self._lock:
            graph = self._graphs.pop(project_id, None)
            path = graph.persist_path if graph else self.base_dir / f"{_slug(project_id)}.json"

        path.unlink(missing_ok=True)
        path.with_suffix(".tmp").unlink(missing_ok=True)

    def reset(self) -> None:
        with self._lock:
            self._graphs.clear()


# Global registry shared by the API and the agents.
kg_store = KnowledgeGraphStore()
