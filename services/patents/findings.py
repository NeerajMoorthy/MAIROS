"""Compute patent-awareness findings — one function, every surface.

The Workflows tab (through the ``patent`` agent flow), the Patents page, the
Markdown and CSV exports and the printable view all report findings from
:func:`compute_findings`. Having exactly one implementation is what lets the
tests promise that an export says the same thing the screen did.

Everything here is computed in Python from the patent text the user pasted and
the passages the project already holds. No model is called, so no model can add
a finding, remove one, or move a score.
"""

from __future__ import annotations

import re

# `services.agents.evidence` is imported inside the functions that use it:
# importing anything under `services.agents` runs that package's __init__,
# which loads the orchestrator, which loads the patent agent, which loads this
# module — a cycle whenever this module is the first one imported.
from .scoring import (
    SCORE_EXPLANATION,
    SCORE_LABEL,
    SECTION_WEIGHTS,
    corpus_stats,
    phrase_pattern,
    score_concept_in_patent,
)
from .segmentation import segment_patent
from .sources import DISCLAIMER, FULL_DISCLAIMER, NO_OVERLAP_NOTE

MIN_CONCEPT_CHARS = 4
MAX_CONCEPTS = 40
MAX_FINDINGS_PER_PATENT = 25
MAX_FINDINGS = 100

_CONCEPT_TYPES = {"Concept", "Method", "Dataset", "Metric", "Task"}

OVERLAP_SENTENCE = (
    "This wording appears both in the project's sources and in the supplied patent text."
)


def project_concepts(project_id: str | None, chunks: list[dict]) -> list[str]:
    """The project's concept vocabulary: graph entities, else its passages' terms.

    Graph entities come first because they are multi-word concepts the project
    is actually about. Without a graph, the passages' own words are used, most
    frequent first. Counting occurrences (not distinct terms per chunk) is what
    makes that a ranking rather than a tie.
    """
    concepts: list[str] = []
    if project_id:
        try:
            from services.knowledge_graph.networkx_store import kg_store

            graph = kg_store.for_project(project_id).graph
            concepts = [
                name
                for name, data in graph.nodes(data=True)
                if data.get("type") in _CONCEPT_TYPES and len(name) >= MIN_CONCEPT_CHARS
            ]
        except Exception:
            concepts = []

    if not concepts:
        from services.agents.evidence import token_counts

        counts: dict[str, int] = {}
        for chunk in chunks:
            for token, occurrences in token_counts(chunk.get("text", "")).items():
                if len(token) >= MIN_CONCEPT_CHARS:
                    counts[token] = counts.get(token, 0) + occurrences
        concepts = [term for term, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    # Deduplicate while preserving that ranking, THEN cut. Sorting before the
    # cut would silently keep the alphabetically-first terms and throw the
    # frequency ordering away.
    seen: set[str] = set()
    ranked: list[str] = []
    for concept in concepts:
        key = concept.lower()
        if key in seen:
            continue
        seen.add(key)
        ranked.append(concept)
        if len(ranked) >= MAX_CONCEPTS:
            break

    return sorted(ranked)  # alphabetical only for stable display


def cite_concept(concept: str, *chunk_lists: list[dict]) -> dict | None:
    """The project passage a concept came from.

    A passage that contains the phrase verbatim is preferred, with the quote
    centred on it; only if none does is the closest wording used. ``None``
    means no passage in the project mentions it, and the UI says so.
    """
    pattern = phrase_pattern(concept)
    if pattern is not None:
        for chunks in chunk_lists:
            for chunk in chunks:
                text = " ".join(str(chunk.get("text", "")).split())
                match = pattern.search(text)
                if not match:
                    continue
                begin = max(0, match.start() - 140)
                quote = text[begin : begin + 320]
                return {
                    "chunk_id": chunk.get("chunk_id", ""),
                    "document_id": chunk.get("document_id", ""),
                    "document_name": chunk.get("document_name", ""),
                    "page": chunk.get("page"),
                    "quote": ("…" if begin else "") + quote,
                }

    from services.agents.evidence import citation_for

    for chunks in chunk_lists:
        citation = citation_for(concept, chunks)
        if citation:
            return citation
    return None


def _patent_summary(patent, segmented, finding_count: int) -> dict:
    return {
        "patent_id": patent.id,
        "title": patent.title,
        "number": patent.number,
        "family_id": getattr(patent, "family_id", "") or "",
        "segmented": segmented.segmented,
        "segmentation_notes": list(segmented.notes),
        "claim_count": len(segmented.claims),
        "findings": finding_count,
    }


def compute_findings(
    patents: list,
    concepts: list[str],
    corpus_chunks: list[dict],
    cite_chunks: list[dict] | None = None,
) -> dict:
    """Score every concept against every supplied patent.

    Args:
        patents: Stored :class:`schemas.Patent` records.
        concepts: The project's concept vocabulary (:func:`project_concepts`).
        corpus_chunks: Every indexed passage of the project — the denominator
            for term rarity.
        cite_chunks: Passages to prefer when citing a concept (the retrieved
            ones, inside an agent run). The corpus is used after them.

    Returns:
        The patent-awareness result, disclaimer included. With no overlap the
        result carries :data:`NO_OVERLAP_NOTE`, never anything resembling a
        clearance.
    """
    base = {
        "disclaimer": DISCLAIMER,
        "full_disclaimer": FULL_DISCLAIMER,
        "score_label": SCORE_LABEL,
        "score_explanation": SCORE_EXPLANATION,
        "section_weights": dict(SECTION_WEIGHTS),
        "patents_checked": len(patents),
        "concepts_checked": len(concepts),
        "corpus_chunks": len(corpus_chunks),
    }

    if not patents:
        return {
            **base,
            "overlaps": [],
            "patents": [],
            "notes": [],
            "note": (
                "Add a patent by pasting its abstract or claims text (optionally "
                "with a public registry link). MAIROS never downloads patent "
                "documents itself."
            ),
        }

    stats = corpus_stats(concepts, corpus_chunks)
    cite_from = [cite_chunks or [], corpus_chunks]

    overlaps: list[dict] = []
    patent_summaries: list[dict] = []
    notes: list[str] = []
    if not corpus_chunks:
        notes.append(
            "This project has no indexed passages, so term rarity could not be "
            "measured and every matched term is treated as rare."
        )

    for patent in patents:
        segmented = segment_patent(patent.text or "")
        found: list[dict] = []
        for concept in concepts:
            scored = score_concept_in_patent(concept, segmented, stats)
            if scored is None:
                continue
            found.append(
                {
                    "patent_id": patent.id,
                    "patent_title": patent.title,
                    "patent_number": patent.number,
                    "patent_url": patent.url,
                    "patent_family_id": getattr(patent, "family_id", "") or "",
                    "overlap": OVERLAP_SENTENCE,
                    "citation": cite_concept(concept, *cite_from),
                    **scored,
                }
            )

        found.sort(key=lambda item: (-item["score"], item["concept"].lower()))
        found = found[:MAX_FINDINGS_PER_PATENT]
        overlaps.extend(found)
        patent_summaries.append(_patent_summary(patent, segmented, len(found)))
        if not segmented.segmented and (patent.text or "").strip():
            notes.append(
                f"'{patent.title}' could not be segmented, so its findings point at "
                "the whole text rather than a specific claim."
            )

    # Stable global order: score, then the order patents were supplied, then
    # concept. Python's sort is stable, so equal scores keep patent order.
    order = {patent.id: index for index, patent in enumerate(patents)}
    overlaps.sort(key=lambda item: (-item["score"], order[item["patent_id"]], item["concept"].lower()))
    overlaps = overlaps[:MAX_FINDINGS]

    families: dict[str, list[str]] = {}
    for patent in patents:
        family = (getattr(patent, "family_id", "") or "").strip()
        if family:
            families.setdefault(family, []).append(patent.title)
    for family, titles in families.items():
        if len(titles) > 1:
            notes.append(
                f"{len(titles)} supplied patents share family '{family}' "
                f"({', '.join(titles)}); the same wording may appear once per family member."
            )

    result = {**base, "overlaps": overlaps, "patents": patent_summaries, "notes": notes}
    if not overlaps:
        result["note"] = NO_OVERLAP_NOTE
    return result


def deterministic_summary(result: dict) -> str:
    overlaps = result.get("overlaps", [])
    claims = sum(1 for item in overlaps if (item.get("section") or {}).get("kind") == "claim")
    return (
        f"{len(overlaps)} wording overlap(s) found across {result.get('patents_checked', 0)} "
        f"supplied patent text(s), {claims} of them located in a claim. "
        "Each is a computed match of shared wording, ranked by a similarity score."
    )


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "patent-findings"


__all__ = [
    "MAX_CONCEPTS",
    "MAX_FINDINGS",
    "MAX_FINDINGS_PER_PATENT",
    "MIN_CONCEPT_CHARS",
    "OVERLAP_SENTENCE",
    "cite_concept",
    "compute_findings",
    "deterministic_summary",
    "project_concepts",
    "slugify",
]
