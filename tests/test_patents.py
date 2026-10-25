"""Patent awareness, completed: segmentation, scoring, metadata, exports, wording.

These tests assert the feature's own guarantees rather than any model output:
claims are found where the text says they start, a score is the documented
product of its components, a no-match is never a clearance, a model cannot add
a finding, the disclaimer reaches every surface, and nothing the feature
renders reads as a legal conclusion.
"""

from __future__ import annotations

import csv
import io

import pytest

from schemas import Patent
from services.agents.patent_awareness import PatentAwarenessAgent
from services.generation.provider import OfflineChatModel
from services.patents.export import CSV_COLUMNS, findings_to_csv, findings_to_markdown
from services.patents.findings import cite_concept, compute_findings
from services.patents.metadata import PatentMetadataError, check_date_order, normalise_codes
from services.patents.scoring import (
    RARITY_FLOOR,
    SECTION_WEIGHTS,
    CorpusStats,
    corpus_stats,
    phrase_length_weight,
    score_concept_in_patent,
)
from services.patents.segmentation import segment_patent
from services.patents.sources import DISCLAIMER, FULL_DISCLAIMER, NO_OVERLAP_NOTE
from services.patents.wording import contains_legal_conclusion, legal_conclusion_terms

from test_workflows import FixedResponseModel, chunk, make_ctx


def patent(title: str, text: str, **fields) -> Patent:
    return Patent(id=fields.pop("id", title.lower().replace(" ", "-")), project_id="p1", title=title, text=text, **fields)


US_STYLE = """Abstract
A retrieval system ranks passages using dense embeddings.

Detailed Description
The system indexes documents for search. Dense retrieval is described here.

What is claimed is:
1. A retrieval system comprising:
   an embedding index; and
   a ranker that scores passages
   of 2.5 mm width.
2. The system of claim 1, wherein the ranker uses
claim 1, wherein the text wraps onto a new line.
3. The system according to any one of claims 1 to 2, further comprising a cache.
"""


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------
class TestSegmentation:
    def test_us_style_patent_splits_into_abstract_description_and_claims(self):
        seg = segment_patent(US_STYLE)
        kinds = [(s.kind, s.number) for s in seg.sections]
        assert seg.segmented is True
        assert kinds == [
            ("abstract", None),
            ("description", None),
            ("claim", 1),
            ("claim", 2),
            ("claim", 3),
        ]

    @pytest.mark.parametrize(
        "text",
        [
            "Claims\n1. A device comprising a widget.\n2. The device of claim 1.",
            "Claims\n1) A device comprising a widget.\n2) The device of claim 1.",
            "Claims\n(1) A device comprising a widget.\n(2) The device of claim 1.",
            "Claims\n[1] A device comprising a widget.\n[2] The device of claim 1.",
            "Claims\n[0001] A device comprising a widget.\n[0002] The device of claim 1.",
            "Claim 1: A device comprising a widget.\nClaim 2: The device of claim 1.",
            "[Claim 1] A device comprising a widget.\n[Claim 2] The device of claim 1.",
        ],
        ids=["dot", "paren-right", "paren-both", "bracket", "bracket-padded", "claim-colon", "claim-bracket"],
    )
    def test_numbering_variants(self, text):
        seg = segment_patent(text)
        claims = seg.claims
        assert [c.number for c in claims] == [1, 2]
        assert claims[0].text == "A device comprising a widget."
        assert claims[1].depends_on == [1]

    def test_wrapped_claims_keep_every_line_and_ignore_stray_numbers(self):
        claims = segment_patent(US_STYLE).claims
        # "2.5 mm" on a wrapped line is not claim 2, and claim 1 keeps it.
        assert "of 2.5 mm width" in claims[0].text
        # A wrapped line beginning "claim 1, wherein" is not a new claim.
        assert "claim 1, wherein the text wraps onto a new line" in claims[1].text
        assert len(claims) == 3

    def test_dependent_claims_record_their_parents(self):
        claims = {c.number: c for c in segment_patent(US_STYLE).claims}
        assert claims[1].independent is True and claims[1].depends_on == []
        assert claims[2].independent is False and claims[2].depends_on == [1]
        # "any one of claims 1 to 2" expands to a range.
        assert claims[3].depends_on == [1, 2]

    def test_reference_lists_and_ranges(self):
        text = (
            "Claims\n1. A method comprising a step.\n2. The method of claim 1.\n"
            "3. The method of claim 1 or 2.\n4. The method of any of claims 1, 2 and 3.\n"
            "5. The method of claims 2-4, wherein x."
        )
        claims = {c.number: c for c in segment_patent(text).claims}
        assert claims[3].depends_on == [1, 2]
        assert claims[4].depends_on == [1, 2, 3]
        assert claims[5].depends_on == [2, 3, 4]

    def test_forward_reference_is_unresolved_not_a_parent(self):
        seg = segment_patent("Claims\n1. A device comprising a part.\n2. The device of claim 5.")
        second = seg.claims[1]
        assert second.depends_on == []
        assert second.unresolved_references == [5]
        # Worded as dependent, so it is not promoted to independent.
        assert second.independent is False

    def test_unsegmentable_blob_falls_back_and_says_so(self):
        seg = segment_patent("Unstructured text about attention and dense retrieval, no structure.")
        assert seg.segmented is False
        assert [s.kind for s in seg.sections] == ["document"]
        assert any("whole text" in note for note in seg.notes)

    def test_numbered_section_titles_are_not_mistaken_for_claims(self):
        seg = segment_patent("1. Introduction to the field\n2. Related work in the area")
        assert seg.segmented is False

    def test_claims_heading_without_numbers_is_matched_as_one_block(self):
        seg = segment_patent("Claims\nA device comprising a widget, wherein the widget is blue.")
        assert seg.segmented is True
        assert seg.sections[0].label.startswith("Claims (not individually numbered)")
        assert any("could not be identified" in note for note in seg.notes)

    def test_original_offsets_point_back_into_the_pasted_text(self):
        seg = segment_patent(US_STYLE)
        for section in seg.sections:
            assert 0 <= section.start < section.end <= len(US_STYLE)
        claim_one = seg.claims[0]
        assert "A retrieval system comprising" in US_STYLE[claim_one.start : claim_one.end]

    def test_empty_text(self):
        seg = segment_patent("   ")
        assert seg.sections == [] and seg.segmented is False


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
class TestScoring:
    def test_score_is_the_product_of_its_components(self):
        seg = segment_patent(US_STYLE)
        stats = CorpusStats(total_chunks=10, chunks_containing={"embedding index": 1})
        found = score_concept_in_patent("embedding index", seg, stats)

        components = found["components"]
        expected = round(
            components["term_rarity"] * components["phrase_length"] * components["section_weight"], 4
        )
        assert found["score"] == expected
        assert components["section_weight"] == SECTION_WEIGHTS["independent_claim"]
        assert components["phrase_length"] == 0.5  # two words of four
        assert found["section"]["label"] == "Claim 1"

    def test_rare_terms_outrank_common_ones(self):
        stats = CorpusStats(total_chunks=100, chunks_containing={"rare": 1, "common": 100})
        assert stats.rarity("rare") > stats.rarity("common")
        # A term in every chunk keeps the floor rather than vanishing.
        assert stats.rarity("common") == pytest.approx(RARITY_FLOOR)

    def test_a_four_word_phrase_beats_scattered_single_words(self):
        assert phrase_length_weight("dense passage retrieval index") == 1.0
        assert phrase_length_weight("retrieval") == 0.25
        assert phrase_length_weight("one two three four five six") == 1.0  # capped

    def test_claims_outweigh_the_description(self):
        text = "Description\nA cache layer is described.\n\nClaims\n1. A system comprising a cache layer."
        seg = segment_patent(text)
        stats = CorpusStats(total_chunks=0, chunks_containing={})
        found = score_concept_in_patent("cache layer", seg, stats)
        assert found["section"]["kind"] == "claim"
        assert found["also_in"] == ["Description"]

    def test_independent_claims_outweigh_dependent_claims(self):
        assert SECTION_WEIGHTS["independent_claim"] > SECTION_WEIGHTS["dependent_claim"]
        assert SECTION_WEIGHTS["dependent_claim"] > SECTION_WEIGHTS["abstract"]
        assert SECTION_WEIGHTS["abstract"] > SECTION_WEIGHTS["description"]

    def test_repetition_inside_the_patent_is_reported_but_not_scored(self):
        stats = CorpusStats(total_chunks=10, chunks_containing={"widget": 5, "flux capacitor array": 1})
        repeated = segment_patent("Claims\n1. A widget comprising " + "widget " * 40 + "and a flux capacitor array.")
        common = score_concept_in_patent("widget", repeated, stats)
        rare = score_concept_in_patent("flux capacitor array", repeated, stats)
        assert common["components"]["occurrences_in_section"] > 40
        assert rare["score"] > common["score"], "a repeated common word must not outrank a rare phrase"

    def test_ordering_is_stable_and_explained(self):
        corpus = [chunk(f"c{i}", "Doc", "dense retrieval and embedding index" if i == 0 else "dense retrieval") for i in range(5)]
        concepts = ["dense retrieval", "embedding index", "cache"]
        first = compute_findings([patent("P", US_STYLE)], concepts, corpus)
        second = compute_findings([patent("P", US_STYLE)], list(reversed(concepts)), corpus)

        assert [o["concept"] for o in first["overlaps"]] == [o["concept"] for o in second["overlaps"]]
        scores = [o["score"] for o in first["overlaps"]]
        assert scores == sorted(scores, reverse=True)
        # "embedding index" is rarer in the corpus and sits in a claim.
        assert first["overlaps"][0]["concept"] == "embedding index"

    def test_whole_word_matching(self):
        seg = segment_patent("Claims\n1. An attentional mechanism comprising a gate.")
        assert score_concept_in_patent("attention", seg, CorpusStats(0, {})) is None

    def test_hyphen_and_space_spellings_match_each_other(self):
        seg = segment_patent("Claims\n1. A model comprising self-attention layers.")
        assert score_concept_in_patent("self attention", seg, CorpusStats(0, {})) is not None

    def test_corpus_stats_count_chunks_not_occurrences(self):
        stats = corpus_stats(["cache"], [chunk("a", "D", "cache cache cache"), chunk("b", "D", "none")])
        assert stats.chunks_containing["cache"] == 1
        assert stats.total_chunks == 2


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------
class TestFindings:
    def test_no_match_is_never_a_clearance(self):
        result = compute_findings([patent("Brakes", "A brake caliper for bicycles.")], ["dense retrieval"], [])
        assert result["overlaps"] == []
        assert result["note"] == NO_OVERLAP_NOTE
        assert "not a legal clearance" in result["note"]
        assert result["disclaimer"] == DISCLAIMER
        assert result["full_disclaimer"] == FULL_DISCLAIMER

    def test_overlapping_families_are_all_reported_and_noted(self):
        patents = [
            patent("Parent", US_STYLE, id="a", family_id="FAM-1"),
            patent("Continuation", US_STYLE, id="b", family_id="FAM-1"),
        ]
        result = compute_findings(patents, ["embedding index"], [])
        assert {o["patent_id"] for o in result["overlaps"]} == {"a", "b"}
        assert all(o["patent_family_id"] == "FAM-1" for o in result["overlaps"])
        assert any("share family 'FAM-1'" in note for note in result["notes"])

    def test_unsegmented_patent_is_flagged_in_the_findings(self):
        result = compute_findings([patent("Blob", "dense retrieval everywhere")], ["dense retrieval"], [])
        assert result["overlaps"][0]["section"]["kind"] == "document"
        assert result["patents"][0]["segmented"] is False
        assert any("could not be segmented" in note for note in result["notes"])

    def test_concept_is_cited_from_the_passage_that_contains_it(self):
        chunks = [
            chunk("x", "Other", "nothing relevant here"),
            chunk("y", "Source Paper", "We build an embedding index over passages.", page=3),
        ]
        citation = cite_concept("embedding index", chunks)
        assert citation["chunk_id"] == "y"
        assert citation["page"] == 3
        assert "embedding index" in citation["quote"]

    def test_empty_corpus_is_stated(self):
        result = compute_findings([patent("P", US_STYLE)], ["embedding index"], [])
        assert any("no indexed passages" in note for note in result["notes"])


# ---------------------------------------------------------------------------
# The agent: a model cannot add a finding or a verdict
# ---------------------------------------------------------------------------
class TestAgentBoundary:
    @pytest.mark.asyncio
    async def test_a_fabricated_model_overlap_cannot_enter_the_results(self, client):
        project_id = client.post("/api/projects", json={"name": "Patents"}).json()["id"]
        client.post(
            f"/api/projects/{project_id}/patents",
            json={"title": "Bicycle brake", "text": "Claims\n1. A brake caliper comprising pads."},
        )

        model = FixedResponseModel()
        model.payload = (
            '{"overlaps": [{"concept": "self attention", "score": 0.99, "section": "Claim 1"}],'
            ' "summary": "The project clearly infringes claim 1."}'
        )
        ctx = make_ctx([chunk("t1", "Paper", "self attention computes query key value")])
        ctx.project_id = project_id
        ctx = await PatentAwarenessAgent(llm=model).run(ctx)

        result = ctx.intermediate_results["patent_awareness"]
        assert result["overlaps"] == []
        assert "infring" not in result["summary"].lower()
        assert result["note"] == NO_OVERLAP_NOTE

    @pytest.mark.asyncio
    async def test_a_legal_sounding_summary_is_replaced(self, client):
        project_id = client.post("/api/projects", json={"name": "Patents"}).json()["id"]
        client.post(
            f"/api/projects/{project_id}/patents",
            json={"title": "Attention", "text": "Claims\n1. A system comprising self attention layers."},
        )
        model = FixedResponseModel()
        model.payload = '{"summary": "Your work is safe to commercialise; there is no risk."}'

        ctx = make_ctx([chunk("t1", "Paper", "self attention computes query key value")])
        ctx.project_id = project_id
        ctx = await PatentAwarenessAgent(llm=model).run(ctx)

        result = ctx.intermediate_results["patent_awareness"]
        assert result["overlaps"], "the computed overlap is still reported"
        assert not contains_legal_conclusion(result["summary"])
        assert result["summary"].startswith(f"{len(result['overlaps'])} wording overlap")

    @pytest.mark.asyncio
    async def test_offline_model_findings_point_at_a_claim(self, client):
        project_id = client.post("/api/projects", json={"name": "Patents"}).json()["id"]
        client.post(
            f"/api/projects/{project_id}/patents",
            json={"title": "Attention", "text": "Claims\n1. A system comprising self attention layers."},
        )
        ctx = make_ctx([chunk("t1", "Paper", "self attention computes query key value")])
        ctx.project_id = project_id
        ctx = await PatentAwarenessAgent(llm=OfflineChatModel()).run(ctx)

        overlaps = ctx.intermediate_results["patent_awareness"]["overlaps"]
        assert overlaps
        assert all(o["section"]["label"] == "Claim 1" for o in overlaps)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
class TestMetadata:
    def test_classification_codes_are_normalised(self):
        assert normalise_codes(["g06f16/3347", "G06N", " h04l 9/32 ", "G06N"], "CPC") == [
            "G06F 16/3347",
            "G06N",
            "H04L 9/32",
        ]

    def test_a_malformed_code_is_rejected_with_the_expected_shape(self):
        with pytest.raises(PatentMetadataError) as excinfo:
            normalise_codes(["not-a-code"], "IPC")
        assert "G06F 16/3347" in str(excinfo.value)

    def test_impossible_date_order_is_rejected(self):
        from datetime import date

        with pytest.raises(PatentMetadataError):
            check_date_order(date(2021, 1, 1), date(2020, 1, 1), None)
        check_date_order(date(2019, 1, 1), date(2020, 1, 1), date(2021, 6, 1))
        check_date_order(None, date(2020, 1, 1), date(2020, 1, 1))  # same day is fine

    def test_full_metadata_round_trip_through_the_api(self, client):
        project_id = client.post("/api/projects", json={"name": "Meta"}).json()["id"]
        response = client.post(
            f"/api/projects/{project_id}/patents",
            json={
                "title": "Retrieval apparatus",
                "number": "US1234567B2",
                "application_number": "US 16/123,456",
                "family_id": "FAM-7",
                "cpc_codes": ["g06f16/3347"],
                "ipc_codes": ["G06F 16/33"],
                "assignee": "Example Labs",
                "inventors": ["Ada Lovelace", "ada lovelace", "Alan Turing"],
                "priority_date": "2019-03-01",
                "filing_date": "2020-03-01",
                "publication_date": "2021-09-14",
                "text": US_STYLE,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["cpc_codes"] == ["G06F 16/3347"]
        assert body["inventors"] == ["Ada Lovelace", "Alan Turing"]
        assert body["filing_date"] == "2020-03-01"
        assert body["claim_count"] == 3 and body["segmented"] is True
        assert body["warnings"] == []
        assert body["disclaimer"] == DISCLAIMER

        detail = client.get(f"/api/projects/{project_id}/patents/{body['id']}").json()
        assert detail["patent"]["family_id"] == "FAM-7"
        assert detail["segmentation"]["independent_claims"] == [1]
        assert detail["segmentation"]["dependent_claims"] == [2, 3]

    def test_date_order_and_format_errors_are_explained(self, client):
        project_id = client.post("/api/projects", json={"name": "Meta"}).json()["id"]
        order = client.post(
            f"/api/projects/{project_id}/patents",
            json={"title": "X", "text": "t", "filing_date": "2022-01-01", "publication_date": "2021-01-01"},
        )
        assert order.status_code == 422
        assert "priority → filing → publication" in order.json()["detail"]

        fmt = client.post(
            f"/api/projects/{project_id}/patents",
            json={"title": "X", "text": "t", "filing_date": "01/02/2020"},
        )
        assert fmt.status_code == 422
        assert "YYYY-MM-DD" in fmt.json()["detail"]

    def test_unfamiliar_number_is_accepted_with_a_warning(self, client):
        project_id = client.post("/api/projects", json={"name": "Meta"}).json()["id"]
        response = client.post(
            f"/api/projects/{project_id}/patents",
            json={"title": "X", "text": "t", "number": "my internal ref 42"},
        )
        assert response.status_code == 201
        assert response.json()["number"] == "my internal ref 42"
        assert response.json()["warnings"]

    def test_patch_updates_and_clears_fields(self, client):
        project_id = client.post("/api/projects", json={"name": "Meta"}).json()["id"]
        created = client.post(
            f"/api/projects/{project_id}/patents",
            json={"title": "X", "text": "t", "filing_date": "2020-01-01"},
        ).json()

        patched = client.patch(
            f"/api/projects/{project_id}/patents/{created['id']}",
            json={"assignee": "New Co", "filing_date": "", "cpc_codes": ["G06N 3/08"]},
        )
        assert patched.status_code == 200, patched.text
        body = patched.json()
        assert body["assignee"] == "New Co"
        assert body["filing_date"] is None
        assert body["cpc_codes"] == ["G06N 3/08"]
        assert body["title"] == "X"  # untouched

        bad = client.patch(
            f"/api/projects/{project_id}/patents/{created['id']}",
            json={"priority_date": "2030-01-01", "filing_date": "2020-01-01"},
        )
        assert bad.status_code == 422

    def test_records_stored_before_metadata_existed_still_load(self, tmp_path):
        """The SQLite migration path: an old payload has none of the new fields."""
        from app.db import Database
        from app.store import MetadataStore

        db = Database(tmp_path / "old.db")
        db.upsert(
            "projects",
            record_id="proj",
            payload={"id": "proj", "name": "Old", "created_at": "2025-01-01T00:00:00+00:00"},
            project_id=None,
            created_at="2025-01-01T00:00:00+00:00",
        )
        db.upsert(
            "patents",
            record_id="old-patent",
            payload={
                "id": "old-patent",
                "project_id": "proj",
                "title": "Legacy",
                "number": "US1B2",
                "text": "Claims\n1. A thing comprising a part.",
                "source": "manual entry",
                "added_at": "2025-01-02T00:00:00+00:00",
            },
            project_id="proj",
            created_at="2025-01-02T00:00:00+00:00",
        )
        db.close()

        store = MetadataStore(state_file=tmp_path / "none.json", database_file=tmp_path / "old.db")
        store.load()
        legacy = store.get_patent("old-patent")
        assert legacy is not None
        assert legacy.cpc_codes == [] and legacy.filing_date is None and legacy.family_id == ""
        assert store.get_project("proj").owner_id == ""

        # And it can be updated with metadata afterwards.
        updated = store.update_patent("old-patent", family_id="FAM-9")
        assert updated.family_id == "FAM-9" and updated.updated_at is not None


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------
class TestExports:
    def _result(self):
        corpus = [chunk("c1", "Source Paper", "We build an embedding index over passages.", page=2)]
        return compute_findings([patent("Retrieval", US_STYLE, number="US1B2")], ["embedding index"], corpus)

    def test_markdown_carries_finding_location_terms_score_and_passage(self):
        markdown = findings_to_markdown(self._result(), "Demo")
        assert markdown.count(FULL_DISCLAIMER) == 2  # top and bottom of the body
        assert "Claim 1 (independent)" in markdown
        assert "embedding index" in markdown
        assert "Source Paper, p. 2" in markdown
        assert "| Score |" in markdown

    def test_csv_has_one_row_per_finding_each_with_the_disclaimer(self):
        rows = list(csv.DictReader(io.StringIO(findings_to_csv(self._result()))))
        assert rows and set(rows[0]) == set(CSV_COLUMNS)
        for row in rows:
            assert row["disclaimer"] == FULL_DISCLAIMER
        assert rows[0]["claim_number"] == "1" and rows[0]["claim_type"] == "independent"
        assert float(rows[0]["similarity_score"]) > 0
        assert rows[0]["project_page"] == "2"

    def test_exports_with_no_findings_still_carry_the_disclaimer(self):
        empty = compute_findings([patent("Brakes", "A brake caliper.")], ["embedding index"], [])
        assert NO_OVERLAP_NOTE in findings_to_markdown(empty, "Demo")
        assert FULL_DISCLAIMER in findings_to_markdown(empty, "Demo")
        rows = list(csv.DictReader(io.StringIO(findings_to_csv(empty))))
        assert rows[0]["disclaimer"] == FULL_DISCLAIMER
        assert rows[0]["project_concept"] == NO_OVERLAP_NOTE

    def test_export_endpoints_return_downloadable_files(self, client):
        project_id = client.post("/api/projects", json={"name": "Export Me"}).json()["id"]
        client.post(f"/api/projects/{project_id}/patents", json={"title": "P", "text": US_STYLE})

        md = client.get(f"/api/projects/{project_id}/patents/findings/export?format=markdown")
        assert md.status_code == 200
        assert "export-me-patent-findings.md" in md.headers["content-disposition"]
        assert FULL_DISCLAIMER in md.text

        csv_response = client.get(f"/api/projects/{project_id}/patents/findings/export?format=csv")
        assert csv_response.status_code == 200
        assert csv_response.headers["content-type"].startswith("text/csv")
        assert FULL_DISCLAIMER in csv_response.text

        assert client.get(f"/api/projects/{project_id}/patents/findings/export?format=pdf").status_code == 422


# ---------------------------------------------------------------------------
# Every surface carries the disclaimer, and nothing reads as a legal conclusion
# ---------------------------------------------------------------------------
def _patent_route_calls(client, project_id: str, patent_id: str) -> dict[tuple[str, str], object]:
    """How to exercise every patent route. A new route must be added here."""
    base = f"/api/projects/{project_id}/patents"
    return {
        ("GET", "/api/patents/sources"): lambda: client.get("/api/patents/sources"),
        ("GET", "/api/projects/{project_id}/patents"): lambda: client.get(base),
        ("POST", "/api/projects/{project_id}/patents"): lambda: client.post(
            base, json={"title": "Another", "text": "Claims\n1. A cache comprising memory."}
        ),
        ("GET", "/api/projects/{project_id}/patents/findings"): lambda: client.get(f"{base}/findings"),
        ("GET", "/api/projects/{project_id}/patents/findings/export"): lambda: client.get(
            f"{base}/findings/export?format=csv"
        ),
        ("GET", "/api/projects/{project_id}/patents/{patent_id}"): lambda: client.get(f"{base}/{patent_id}"),
        ("PATCH", "/api/projects/{project_id}/patents/{patent_id}"): lambda: client.patch(
            f"{base}/{patent_id}", json={"assignee": "Example"}
        ),
        # 204 has no body to carry anything; listed so the enumeration is complete.
        ("DELETE", "/api/projects/{project_id}/patents/{patent_id}"): None,
    }


class TestDisclaimerSurface:
    def _setup(self, client, sample_pdf):
        project_id = client.post("/api/projects", json={"name": "Surface"}).json()["id"]
        with open(sample_pdf, "rb") as handle:
            client.post(
                f"/api/projects/{project_id}/documents",
                files={"file": ("paper.pdf", handle, "application/pdf")},
            )
        patent_id = client.post(
            f"/api/projects/{project_id}/patents",
            json={
                "title": "Attention apparatus",
                "text": "Abstract\nDense retrieval over an embedding index.\n\nClaims\n"
                "1. A system comprising self attention and an embedding index.\n"
                "2. The system of claim 1, wherein retrieval is dense.",
            },
        ).json()["id"]
        return project_id, patent_id

    def test_every_patent_route_is_enumerated_and_carries_the_disclaimer(self, client, sample_pdf):
        from main import app

        project_id, patent_id = self._setup(client, sample_pdf)
        calls = _patent_route_calls(client, project_id, patent_id)

        # The OpenAPI schema is the public, version-stable list of every route
        # (newer FastAPI wraps included routers, so `app.routes` is not).
        registered = {
            (method.upper(), path)
            for path, operations in app.openapi()["paths"].items()
            if "patent" in path
            for method in operations
        }
        assert registered == set(calls), (
            "A patent route was added or removed without updating this test — "
            "decide how it carries the disclaimer, then list it here."
        )

        for key, call in calls.items():
            if call is None:
                continue
            response = call()
            assert response.status_code < 300, (key, response.text)
            assert DISCLAIMER in response.text, f"{key} returned no disclaimer"

    def test_error_states_name_no_legal_conclusion(self, client):
        project_id = client.post("/api/projects", json={"name": "Errors"}).json()["id"]
        base = f"/api/projects/{project_id}/patents"
        responses = [
            client.post(base, json={"title": "X"}),
            client.post(base, json={"title": "X", "text": "t", "url": "https://evil.example.com"}),
            client.post(base, json={"title": "X", "text": "t", "cpc_codes": ["nope"]}),
            client.post(base, json={"title": "X", "text": "t", "filing_date": "yesterday"}),
            client.get(f"{base}/missing"),
            client.get("/api/projects/missing/patents/findings"),
        ]
        for response in responses:
            assert response.status_code >= 400
            assert not legal_conclusion_terms(response.text), response.text

    def test_flow_output_and_exports_name_no_legal_conclusion(self, client, sample_pdf):
        project_id, _ = self._setup(client, sample_pdf)
        task = client.post(
            f"/api/projects/{project_id}/tasks", json={"question": "any overlap?", "flow": "patent"}
        ).json()
        result = client.get(f"/api/tasks/{task['id']}").json()["result"]

        rendered = [
            str(result["patent_awareness"]),
            client.get(f"/api/projects/{project_id}/patents/findings").text,
            client.get(f"/api/projects/{project_id}/patents/findings/export?format=markdown").text,
            client.get(f"/api/projects/{project_id}/patents/findings/export?format=csv").text,
            client.get("/api/patents/sources").text,
        ]
        for text in rendered:
            assert not legal_conclusion_terms(text), legal_conclusion_terms(text)


class TestFrontendCopyMatchesTheBackend:
    """The UI shows these in states with no API response (loading, errors)."""

    def _frontend_constant(self, name: str) -> str:
        """Evaluate a `"a" + "b" + OTHER_CONSTANT` declaration from patentCopy.ts."""
        import re
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "apps/web/src/lib/patentCopy.ts").read_text(
            encoding="utf-8"
        )
        match = re.search(rf"export const {name} =(.*?);\n", source, re.DOTALL)
        assert match, f"{name} missing from patentCopy.ts"

        parts = []
        for literal, identifier in re.findall(r'"([^"]*)"|\b([A-Z_]+)\b', match.group(1)):
            parts.append(literal if not identifier else self._frontend_constant(identifier))
        return "".join(parts)

    def test_disclaimers_are_identical(self):
        assert self._frontend_constant("PATENT_DISCLAIMER") == DISCLAIMER
        assert self._frontend_constant("PATENT_FULL_DISCLAIMER") == FULL_DISCLAIMER
        assert self._frontend_constant("PATENT_NO_OVERLAP_NOTE") == NO_OVERLAP_NOTE

    def test_score_label_is_identical(self):
        from services.patents.scoring import SCORE_LABEL

        assert self._frontend_constant("PATENT_SCORE_LABEL") == SCORE_LABEL


class TestWordingAudit:
    @pytest.mark.parametrize(
        "text",
        [
            "This product may infringe claim 1.",
            "There is a violation of the patent.",
            "You are clear to proceed.",
            "It is safe to launch.",
            "The idea is patentable.",
            "Claim 2 looks invalid.",
            "We assessed freedom to operate.",
            "Low risk overall.",
        ],
    )
    def test_legal_conclusions_are_caught(self, text):
        assert contains_legal_conclusion(text)

    def test_the_reviewed_explanations_are_permitted(self):
        # These name conclusions only to disclaim them.
        assert legal_conclusion_terms(FULL_DISCLAIMER) == []
        assert legal_conclusion_terms(NO_OVERLAP_NOTE) == []
        assert legal_conclusion_terms(f"Header. {FULL_DISCLAIMER} Footer.") == []

    def test_a_negation_is_not_a_blanket_pass(self):
        # Only the exact reviewed sentences are exempt — any other wording that
        # names a conclusion, even negated, is flagged for review.
        assert contains_legal_conclusion("This does not infringe anything.")
