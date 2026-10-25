"""Typographic hyphens and spaces in graph names.

The live confirmation run (22 October 2026, `openai/gpt-oss-120b`) produced
nodes such as "retrieval‑augmented approach" and "parametric‑only baseline"
with U+2011 (non-breaking hyphen). Those never matched "retrieval-augmented" in
a document or a question, so graph-boosted retrieval could not find them. The
names below are taken from that run.
"""

from __future__ import annotations

import json

import pytest

from services.common.text import normalize_name
from services.knowledge_graph.entity_extractor import EntityRelationExtractor
from services.knowledge_graph.networkx_store import ProjectGraph

NBH = "‑"  # non-breaking hyphen, as the live model wrote it
LIVE_NAME = f"retrieval{NBH}augmented approach"


@pytest.fixture()
def graph(tmp_path):
    return ProjectGraph("p1", tmp_path / "p1.json")


class TestNormalizeName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (LIVE_NAME, "retrieval-augmented approach"),
            (f"parametric{NBH}only baseline", "parametric-only baseline"),
            (f"SYN{NBH}A", "SYN-A"),
            ("self‐attention", "self-attention"),  # hyphen
            ("text–image retrieval", "text-image retrieval"),  # en dash
            ("BLEU−score", "BLEU-score"),  # minus sign
            ("dense retrieval", "dense retrieval"),  # no-break space
            ("dense retrieval", "dense retrieval"),  # narrow no-break space
            ("re­trieval", "retrieval"),  # soft hyphen
            ("dense​retrieval", "denseretrieval"),  # zero-width space
            ("  many   spaces  ", "many spaces"),
            ("plain-ascii name", "plain-ascii name"),
        ],
    )
    def test_folding(self, raw, expected):
        assert normalize_name(raw) == expected

    def test_em_dashes_are_left_alone(self):
        # An em dash separates clauses rather than joining a compound word.
        assert normalize_name("BERT — large") == "BERT — large"

    def test_none_and_empty(self):
        assert normalize_name(None) == ""
        assert normalize_name(" ​") == ""


class TestExtractor:
    def test_names_and_relation_endpoints_come_back_in_ascii(self):
        reply = json.dumps(
            {
                "entities": [
                    {"name": LIVE_NAME, "type": "Method"},
                    {"name": f"parametric{NBH}only baseline", "type": "Method"},
                ],
                "relations": [
                    {
                        "subject": f"parametric{NBH}only baseline",
                        "relation": "COMPARES_TO",
                        "object": LIVE_NAME,
                    }
                ],
            }
        )
        result = EntityRelationExtractor(llm=lambda prompt: reply).extract("text")

        assert [e.name for e in result.entities] == [
            "retrieval-augmented approach",
            "parametric-only baseline",
        ]
        # The relation's endpoints match the entities, so none was promoted
        # into a second, look-alike entity.
        assert len(result.entities) == 2
        assert (result.relations[0].subject, result.relations[0].object) == (
            "parametric-only baseline",
            "retrieval-augmented approach",
        )


class TestGraphStore:
    def test_both_spellings_are_one_node(self, graph):
        assert graph.add_entity(LIVE_NAME, "Method") == "retrieval-augmented approach"
        graph.add_entity("retrieval-augmented approach", "Method")
        assert list(graph.graph.nodes) == ["retrieval-augmented approach"]
        assert graph.graph.nodes["retrieval-augmented approach"]["mentions"] == 2

    def test_relations_land_on_the_normalised_nodes(self, graph):
        graph.add_relation(f"parametric{NBH}only baseline", "COMPARES_TO", LIVE_NAME)
        assert graph.graph.has_edge("parametric-only baseline", "retrieval-augmented approach")
        assert all(NBH not in node for node in graph.graph.nodes)

    def test_a_typed_question_now_finds_the_extracted_entity(self, graph):
        """The user-visible bug: graph linking missed every hyphenated concept."""
        graph.add_entity(LIVE_NAME, "Method")
        assert graph.match_entities("How does the retrieval-augmented approach compare?") == [
            "retrieval-augmented approach"
        ]
        # A question pasted with the typographic hyphen matches too.
        assert graph.match_entities(f"Explain the {LIVE_NAME}") == ["retrieval-augmented approach"]

    def test_neighbours_accept_either_spelling(self, graph):
        # Written with one spelling, looked up with the other — both ways.
        graph.add_relation(LIVE_NAME, "USES", "top five relevant passages")
        assert graph.neighbors("retrieval-augmented approach") == {"top five relevant passages"}
        graph.add_relation("dense retriever", "USES", f"embedding{NBH}index")
        assert graph.neighbors("dense retriever") == {"embedding-index"}  # no-break space
        assert graph.neighbors("embedding‐index") == {"dense retriever"}

    def test_graph_retrieval_follows_a_typographic_seed(self, tmp_path):
        from services.knowledge_graph.networkx_store import KnowledgeGraphStore
        from services.retrieval.graph_retriever import GraphRetriever

        store = KnowledgeGraphStore(base_dir=tmp_path)
        store.for_project("p1").add_relation(LIVE_NAME, "USES", "top five relevant passages")
        retriever = GraphRetriever(project_id="p1", store=store)

        results = retriever.search(entities=[LIVE_NAME])
        assert results and results[0].entity == "retrieval-augmented approach"


class TestGraphsSavedBeforeTheFix:
    def test_look_alike_nodes_are_merged_on_load(self, tmp_path):
        """A graph file written by the earlier build holds both spellings."""
        path = tmp_path / "old.json"
        old = ProjectGraph("old", path)
        # Write the pre-fix state directly, bypassing normalisation.
        old.graph.add_node(LIVE_NAME, type="Method", description="", mentions=2, source_chunk_ids=["c1"])
        old.graph.add_node(
            "retrieval-augmented approach", type="Unknown", description="uses passages", mentions=1,
            source_chunk_ids=["c2"],
        )
        old.graph.add_node("top five relevant passages", type="Concept", mentions=1, source_chunk_ids=[])
        old.graph.add_edge(LIVE_NAME, "top five relevant passages", relation="USES", confidence=0.9)
        old.graph.add_edge("retrieval-augmented approach", LIVE_NAME, relation="RELATED_TO", confidence=0.5)
        old.save()

        loaded = ProjectGraph("old", path)
        node = loaded.graph.nodes["retrieval-augmented approach"]
        assert sorted(loaded.graph.nodes) == ["retrieval-augmented approach", "top five relevant passages"]
        assert node["mentions"] == 3
        assert node["source_chunk_ids"] == ["c1", "c2"]
        assert node["type"] == "Method"
        assert node["description"] == "uses passages"
        assert loaded.graph.has_edge("retrieval-augmented approach", "top five relevant passages")
        # The edge between the two spellings would now be a self-loop: dropped.
        assert loaded.graph.number_of_edges() == 1

    def test_a_clean_graph_is_loaded_untouched(self, tmp_path):
        path = tmp_path / "clean.json"
        clean = ProjectGraph("clean", path)
        clean.add_relation("dense retriever", "USES", "embedding index")
        before = path.read_text(encoding="utf-8")

        loaded = ProjectGraph("clean", path)
        assert sorted(loaded.graph.nodes) == ["dense retriever", "embedding index"]
        loaded.save()
        assert path.read_text(encoding="utf-8") == before
