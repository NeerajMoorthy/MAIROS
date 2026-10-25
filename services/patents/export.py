"""Markdown and CSV exports of patent-awareness findings.

An exported file is read by people who never saw the app, so it must stand on
its own: the **full** disclaimer is written into the body of every export — the
first block of the Markdown, and a column on every CSV row (CSV has no comment
syntax that spreadsheet tools respect, and a disclaimer only in a header row is
lost the moment someone filters the sheet). An export with no findings still
carries the disclaimer and says plainly that absence of overlap is not a
clearance.

Each finding records: the project concept, the matched patent claim or section
(with its number and dependency), the matched terms, the score and its
components, and the project passage the concept came from.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from .sources import FULL_DISCLAIMER, NO_OVERLAP_NOTE

CSV_COLUMNS = (
    "patent_title",
    "publication_number",
    "family_id",
    "project_concept",
    "matched_section",
    "section_kind",
    "claim_number",
    "claim_type",
    "depends_on_claims",
    "matched_terms",
    "similarity_score",
    "term_rarity",
    "phrase_length",
    "section_weight",
    "corpus_chunks",
    "chunks_containing_term",
    "patent_excerpt",
    "project_source",
    "project_page",
    "project_passage",
    "disclaimer",
)


def _claim_type(section: dict) -> str:
    if section.get("kind") != "claim" or section.get("number") is None:
        return ""
    return "independent" if section.get("independent") else "dependent"


def _md_cell(value) -> str:
    """Escape a value for a Markdown table cell."""
    return " ".join(str(value if value is not None else "").split()).replace("|", "\\|")


def _location(section: dict) -> str:
    label = section.get("label") or "Unknown section"
    claim_type = _claim_type(section)
    if not claim_type:
        return label
    if section.get("depends_on"):
        parents = ", ".join(str(n) for n in section["depends_on"])
        return f"{label} (dependent on claim {parents})"
    return f"{label} (independent)"


def findings_to_markdown(result: dict, project_name: str, generated_at: datetime | None = None) -> str:
    generated = (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    overlaps = result.get("overlaps", [])
    lines = [
        f"# Patent wording overlaps — {project_name}",
        "",
        f"> **Disclaimer.** {FULL_DISCLAIMER}",
        "",
        f"Generated {generated} by MAIROS. "
        f"{result.get('patents_checked', 0)} patent text(s) checked against "
        f"{result.get('concepts_checked', 0)} project concept(s) and "
        f"{result.get('corpus_chunks', 0)} indexed project passage(s).",
        "",
        f"**{result.get('score_label', 'Similarity score')}.** {result.get('score_explanation', '')}",
        "",
    ]

    for note in result.get("notes", []):
        lines.append(f"- {note}")
    if result.get("notes"):
        lines.append("")

    if not overlaps:
        lines += ["## Findings", "", NO_OVERLAP_NOTE, ""]
    else:
        lines += [
            "## Findings",
            "",
            "| # | Project concept | Patent | Matched claim / section | Matched terms | Score | Rarity | Length | Section weight |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for index, item in enumerate(overlaps, start=1):
            components = item.get("components", {})
            patent = item.get("patent_title", "")
            if item.get("patent_number"):
                patent += f" ({item['patent_number']})"
            lines.append(
                "| "
                + " | ".join(
                    _md_cell(value)
                    for value in (
                        index,
                        item.get("concept"),
                        patent,
                        _location(item.get("section") or {}),
                        ", ".join(item.get("matched_terms", [])),
                        f"{item.get('score', 0):.3f}",
                        components.get("term_rarity"),
                        components.get("phrase_length"),
                        components.get("section_weight"),
                    )
                )
                + " |"
            )
        lines.append("")

        lines += ["## Evidence", ""]
        for index, item in enumerate(overlaps, start=1):
            section = item.get("section") or {}
            citation = item.get("citation") or {}
            lines += [
                f"### {index}. {item.get('concept')} — {_location(section)}",
                "",
                f"- **Patent excerpt:** {section.get('excerpt', '')}",
            ]
            if citation:
                page = f", p. {citation['page']}" if citation.get("page") is not None else ""
                lines.append(
                    f"- **Project passage** ({citation.get('document_name') or 'source'}{page}): "
                    f"{citation.get('quote', '')}"
                )
            else:
                lines.append("- **Project passage:** no project passage mentions this wording verbatim.")
            if item.get("also_in"):
                lines.append(f"- Also appears in: {', '.join(item['also_in'])}")
            lines.append("")

    lines += ["---", "", f"*{FULL_DISCLAIMER}*", ""]
    return "\n".join(lines)


def findings_to_csv(result: dict) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()

    overlaps = result.get("overlaps", [])
    if not overlaps:
        row = {column: "" for column in CSV_COLUMNS}
        row["project_concept"] = NO_OVERLAP_NOTE
        row["disclaimer"] = FULL_DISCLAIMER
        writer.writerow(row)
        return buffer.getvalue()

    for item in overlaps:
        section = item.get("section") or {}
        components = item.get("components", {})
        citation = item.get("citation") or {}
        writer.writerow(
            {
                "patent_title": item.get("patent_title", ""),
                "publication_number": item.get("patent_number", ""),
                "family_id": item.get("patent_family_id", ""),
                "project_concept": item.get("concept", ""),
                "matched_section": section.get("label", ""),
                "section_kind": section.get("kind", ""),
                "claim_number": section.get("number") if section.get("number") is not None else "",
                "claim_type": _claim_type(section),
                "depends_on_claims": " ".join(str(n) for n in section.get("depends_on", [])),
                "matched_terms": "; ".join(item.get("matched_terms", [])),
                "similarity_score": f"{item.get('score', 0):.4f}",
                "term_rarity": components.get("term_rarity", ""),
                "phrase_length": components.get("phrase_length", ""),
                "section_weight": components.get("section_weight", ""),
                "corpus_chunks": components.get("corpus_chunks", ""),
                "chunks_containing_term": components.get("chunks_containing_term", ""),
                "patent_excerpt": section.get("excerpt", ""),
                "project_source": citation.get("document_name", ""),
                "project_page": citation.get("page") if citation.get("page") is not None else "",
                "project_passage": citation.get("quote", ""),
                "disclaimer": FULL_DISCLAIMER,
            }
        )
    return buffer.getvalue()


__all__ = ["CSV_COLUMNS", "findings_to_csv", "findings_to_markdown"]
