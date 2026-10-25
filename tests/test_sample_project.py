"""The sample project behind docs/SAMPLE_PROJECT_WALKTHROUGH.md.

The walkthrough tells a tester exactly what to expect: pages and chunks per
paper, the figures each answer must contain, the contributions MAIROS reads
from the description, how the patent's claims depend on each other, and which
files are refused. These tests pin the facts that do not depend on a model, so
a change to the generator, the extractor, the chunker or the intake rules that
would make the walkthrough wrong fails here first.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.config import settings
from services.agents.intake import ProjectIntakeAgent
from services.ingestion.extractor import PDFExtractor
from services.ingestion.pipeline import IngestionPipeline
from services.patents.segmentation import segment_patent

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_sample_project.py"
_spec = importlib.util.spec_from_file_location("generate_sample_project", _SCRIPT)
generate_sample_project = importlib.util.module_from_spec(_spec)
sys.modules["generate_sample_project"] = generate_sample_project
assert _spec.loader is not None
_spec.loader.exec_module(generate_sample_project)

# File -> (title MAIROS must read, figures the walkthrough's answers are checked against)
PAPERS = {
    "paper-a-camera-cnn.pdf": (
        "Lightweight CNN Crack Detection on Rail Heads",
        ["recall of 0.91", "precision of 0.88", "recall fell to 0.64"],
    ),
    "paper-b-ultrasonic-guided-waves.pdf": (
        "Ultrasonic Guided Waves for Rail Weld Flaws",
        ["38 of the 40", "about 40 minutes"],
    ),
    "paper-c-vibration-alerts.pdf": (
        "Vibration Monitoring and GPS Alerts for Track Defects",
        ["40 of the 46", "delayed 12% of alerts", "GSM module sends each alert"],
    ),
}
LIGATURES = "ﬀﬁﬂﬃﬄ"


@pytest.fixture(scope="module")
def sample_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("sample-project")
    generate_sample_project.build(out)
    return out


def _ingest(path: Path, chroma_store) -> dict:
    pipeline = IngestionPipeline(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        chroma_store=chroma_store,
    )
    return pipeline.ingest(pdf_path=path, project_id="sample", document_name=path.name)


class TestSamplePapers:
    @pytest.mark.parametrize("name", sorted(PAPERS))
    def test_pages_chunks_and_title_match_the_walkthrough(self, name, sample_dir, chroma_store):
        result = _ingest(sample_dir / name, chroma_store)

        assert result["num_pages"] == 2
        assert result["num_chunks"] == 4
        assert result["title"] == PAPERS[name][0]

    @pytest.mark.parametrize("name", sorted(PAPERS))
    def test_text_holds_the_figures_the_answers_are_checked_against(self, name, sample_dir):
        text = " ".join(PDFExtractor().extract_text(sample_dir / name).split())

        for figure in PAPERS[name][1]:
            assert figure in text
        # A ligature would store "flagged" as "ﬂagged", and a tester's
        # question would no longer match the word.
        assert not any(character in text for character in LIGATURES)

    @pytest.mark.parametrize("name", sorted(PAPERS))
    def test_each_paper_says_on_its_first_page_that_it_is_fictional(self, name, sample_dir):
        first_page = " ".join(PDFExtractor().extract(sample_dir / name)[0].text.split())

        assert "A fictional sample paper" in first_page
        assert "not published research" in first_page

    @pytest.mark.parametrize("name", sorted(PAPERS))
    def test_results_and_limitations_are_on_page_two(self, name, sample_dir):
        pages = PDFExtractor().extract(sample_dir / name)
        first, second = (" ".join(page.text.split()) for page in pages)

        assert "Results." in second and "Limitations." in second
        assert "Results." not in first and "limitation" not in first.lower()


class TestFilesThatMustBeRefused:
    def test_scanned_page_has_no_text_so_nothing_is_indexed(self, sample_dir, chroma_store):
        # The upload route answers 422 when ingestion yields no chunks.
        assert _ingest(sample_dir / "scanned-page.pdf", chroma_store)["num_chunks"] == 0

    def test_broken_file_is_not_a_pdf(self, sample_dir):
        assert not (sample_dir / "broken-file.pdf").read_bytes().startswith(b"%PDF")


class TestProjectDescription:
    def test_is_long_enough_for_the_review_button(self, sample_dir):
        text = (sample_dir / "project-description.txt").read_text(encoding="utf-8")

        assert len(text.strip()) >= 200

    def test_rules_read_two_contributions_and_keep_the_test_plan_as_a_goal(self, sample_dir):
        brief = ProjectIntakeAgent.rules_brief(
            (sample_dir / "project-description.txt").read_text(encoding="utf-8")
        )

        assert brief["title"] == "RailGuard Lite: a low-cost railway track crack detection robot"
        assert brief["contributions"] == [
            "We propose a camera and infrared crack detector that runs on a microcontroller.",
            "We build an alerting module that sends the GPS position of each crack over GSM.",
        ]
        assert brief["goals"] == [
            "We will test it on a 500 m test track with artificial cracks between 0.5 mm and 3 mm wide."
        ]


class TestPatentSample:
    def test_four_claims_with_the_dependencies_the_walkthrough_lists(self, sample_dir):
        pasted = (sample_dir / "patent-sample.txt").read_text(encoding="utf-8").split("-" * 72)[1]
        segmented = segment_patent(pasted.strip())
        claims = {claim.number: claim for claim in segmented.claims}

        assert segmented.segmented
        assert sorted(claims) == [1, 2, 3, 4]
        assert claims[1].independent is True and claims[1].depends_on == []
        assert claims[2].depends_on == [1]
        assert claims[3].depends_on == [1]
        assert claims[4].depends_on == [3]
        assert any(section.kind == "abstract" for section in segmented.sections)
