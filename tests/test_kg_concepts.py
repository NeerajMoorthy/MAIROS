"""The knowledge graph keeps working when the model cannot help.

Entity extraction asks the language model. Before these changes a failed call
(Groq answers HTTP 429 once its free per-minute budget is spent) left the
paper with no concepts at all; offline, the stand-in model named single words
("Heads", "Guided"); and an uploaded paper never became a node, so the graph
could not say where a concept came from. Patent awareness matches patents
against these concepts, so it inherited every one of those gaps.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from services.ingestion.extractor import PDFExtractor
from services.knowledge_graph.concepts import co_occurring, concept_phrases
from services.knowledge_graph.entity_extractor import EntityRelationExtractor

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_sample_project.py"
_spec = importlib.util.spec_from_file_location("generate_sample_project_kg", _SCRIPT)
generate_sample_project = importlib.util.module_from_spec(_spec)
sys.modules["generate_sample_project_kg"] = generate_sample_project
assert _spec.loader is not None
_spec.loader.exec_module(generate_sample_project)


@pytest.fixture(scope="module")
def sample_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("kg-sample")
    generate_sample_project.build(out)
    return out


def _text(sample_dir: Path, name: str) -> str:
    return PDFExtractor().extract_text(sample_dir / name)


class TestConceptPhrases:
    def test_the_concepts_a_paper_repeats_not_its_single_words(self, sample_dir):
        assert {"rail heads", "single-board computer", "CNN"} <= set(
            concept_phrases(_text(sample_dir, "paper-a-camera-cnn.pdf"))
        )
        assert {"guided waves", "weld flaws"} <= set(
            concept_phrases(_text(sample_dir, "paper-b-ultrasonic-guided-waves.pdf"))
        )
        assert {"track defects", "GSM", "GPS"} <= set(
            concept_phrases(_text(sample_dir, "paper-c-vibration-alerts.pdf"))
        )

    def test_an_acronym_named_once_and_header_labels_are_not_concepts(self, sample_dir):
        concepts = concept_phrases(_text(sample_dir, "paper-a-camera-cnn.pdf"))
        assert "MAIROS" not in concepts  # only in the one-line fictional note
        labelled = concept_phrases("Title: Graph retrieval\nAuthors: A. Rao\nAbstract: Graph retrieval. " * 3)
        assert not {"title", "authors", "abstract"} & {c.lower() for c in labelled}

    def test_a_term_cut_by_the_window_keeps_its_head_noun(self):
        text = "We train a lightweight convolutional neural network. " * 3
        concepts = concept_phrases(text)
        assert "convolutional neural network" in concepts
        assert "lightweight convolutional neural" not in concepts

    def test_a_plural_is_merged_with_its_singular(self):
        text = "Each alert has a delay. Alerts arrive by text. The alert system. Alerts matter. " * 2
        concepts = concept_phrases(text)
        assert not ({"alert", "alerts"} <= set(concepts))

    def test_concepts_sharing_a_sentence_are_linked_but_not_a_term_with_its_own_part(self):
        pairs = co_occurring(
            ["guided waves", "ultrasonic guided waves", "weld flaws"],
            "Ultrasonic guided waves find weld flaws. Guided waves travel far.",
        )
        assert ("ultrasonic guided waves", "weld flaws") in pairs
        assert not any({"guided waves", "ultrasonic guided waves"} == set(p) for p in pairs)


class TestExtractionFallback:
    TEXT = (
        "Ultrasonic guided waves locate weld flaws in continuous rail. Guided waves miss "
        "shallow weld flaws. Ultrasonic guided waves need a couplant. Weld flaws grow."
    )

    def test_a_failed_model_call_still_yields_concepts_and_says_why(self):
        class RateLimited:
            def invoke(self, prompt):
                raise RuntimeError("Error code: 429 - rate limit reached for model")

        result = EntityRelationExtractor(llm=RateLimited()).extract(self.TEXT)

        names = {e.name for e in result.entities}
        assert {"guided waves", "weld flaws"} <= names
        assert "model call failed" in result.problem and "429" in result.problem
        assert "key concepts were taken from the text" in result.problem

    def test_no_model_falls_back_to_the_text(self):
        result = EntityRelationExtractor(llm=None).extract(self.TEXT)
        assert result.entities and "no model is configured" in result.problem

    def test_a_reply_naming_no_entities_falls_back_to_the_passages(self):
        result = EntityRelationExtractor(llm=lambda prompt: '{"entities": [], "relations": []}').extract(
            "A short summary.", fallback_text=self.TEXT
        )
        assert "guided waves" in {e.name for e in result.entities}


class TestGraphAndPatentsOnTheSampleProject:
    def test_uploads_become_paper_nodes_and_patents_match_in_claims(self, client, sample_dir):
        project_id = client.post("/api/projects", json={"name": "RailGuard"}).json()["id"]
        for name in (
            "paper-a-camera-cnn.pdf",
            "paper-b-ultrasonic-guided-waves.pdf",
            "paper-c-vibration-alerts.pdf",
        ):
            with open(sample_dir / name, "rb") as handle:
                response = client.post(
                    f"/api/projects/{project_id}/documents",
                    files={"file": (name, handle, "application/pdf")},
                )
            assert response.status_code == 201, response.text

        graph = client.get(f"/api/projects/{project_id}/graph").json()
        papers = {n["name"] for n in graph["nodes"] if n.get("group", n.get("type")) == "Paper"}
        assert papers == {
            "Lightweight CNN Crack Detection on Rail Heads",
            "Ultrasonic Guided Waves for Rail Weld Flaws",
            "Vibration Monitoring and GPS Alerts for Track Defects",
        }
        edges = graph.get("links", graph.get("edges", []))
        linked = {e["source"] for e in edges} | {e["target"] for e in edges}
        assert all(node["id"] in linked for node in graph["nodes"]), "no concept floats unattached"

        pasted = (sample_dir / "patent-sample.txt").read_text(encoding="utf-8").split("-" * 72)[1]
        client.post(
            f"/api/projects/{project_id}/patents",
            json={"title": "Rail inspection trolley with camera and vibration sensing", "text": pasted.strip()},
        )
        findings = client.get(f"/api/projects/{project_id}/patents/findings").json()
        in_claims = {(o["concept"], o["section"]["label"]) for o in findings["overlaps"]}
        assert ("convolutional neural network", "Claim 2") in in_claims
        assert ("inspection trolley", "Claim 1") in in_claims
