"""Computed, explainable overlap between project concepts and patent sections.

This replaces binary literal matching ("the term appears: yes/no") with a score
that says how much a shared term is worth — and shows its working, so a reader
can see why one finding ranks above another.

    similarity = term_rarity × phrase_length × section_weight      (0 – 1)

* **term_rarity** — how unusual the concept is *in this project's own corpus*.
  A term found in one indexed chunk out of a hundred is worth far more than one
  found in every chunk; a term in every chunk still keeps a small floor so it is
  ranked low rather than vanishing.
* **phrase_length** — a four-word phrase matched intact is stronger evidence of
  shared vocabulary than a single word. Capped at four words.
* **section_weight** — where in the patent the match sits. Claims weigh most
  (independent above dependent), then the abstract, then the description.

What it deliberately does **not** count: how many times a term repeats inside
the patent. Repetition is reported (``occurrences``) but never scored, so a
boilerplate word that a patent uses fifty times cannot outrank a rare phrase it
uses once.

**This is a similarity score over wording, nothing more.** It is not a
probability, a risk level, or an opinion of any kind about the patent. It is
computed entirely in Python from text the user supplied and passages the
project already holds; no model is asked for it and no model can change it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .segmentation import ABSTRACT, CLAIM, DESCRIPTION, DOCUMENT, PatentSection, SegmentedPatent

SCORE_LABEL = "Similarity score (shared wording only)"
SCORE_EXPLANATION = (
    "similarity = term rarity × phrase length × section weight, each between 0 and 1. "
    "Term rarity is measured against this project's own indexed passages; phrase "
    "length rewards multi-word matches (up to four words); section weight is higher "
    "for claims than for the abstract or description. Repetition inside the patent "
    "is shown but not scored. The score describes shared wording only."
)

# Section weights. Documented in SCORE_EXPLANATION and asserted in the tests, so
# changing one is a visible decision rather than a silent re-ranking.
SECTION_WEIGHTS: dict[str, float] = {
    "independent_claim": 1.0,
    "dependent_claim": 0.85,
    # A claims block that could not be split into numbered claims.
    "claims_block": 0.85,
    ABSTRACT: 0.6,
    DOCUMENT: 0.5,
    DESCRIPTION: 0.4,
}

MAX_PHRASE_WORDS = 4
# A term found in every chunk keeps this much rarity, so it ranks last rather
# than disappearing from the findings entirely.
RARITY_FLOOR = 0.1


def phrase_pattern(phrase: str) -> re.Pattern[str] | None:
    """Whole-word, case-insensitive pattern for *phrase*.

    Words may be separated by whitespace or hyphens, so "self-attention" and
    "self attention" match each other. Word boundaries stop "attention" from
    matching inside "attentional".
    """
    words = re.findall(r"[a-z0-9]+", phrase.lower())
    if not words:
        return None
    body = r"[\s\-]+".join(re.escape(word) for word in words)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])", re.IGNORECASE)


def section_weight_key(section: PatentSection) -> str:
    if section.kind == CLAIM:
        if section.number is None:
            return "claims_block"
        return "independent_claim" if section.independent else "dependent_claim"
    return section.kind


@dataclass(frozen=True)
class CorpusStats:
    """Document frequency of concepts across the project's indexed chunks."""

    total_chunks: int
    chunks_containing: dict[str, int]

    def rarity(self, concept: str) -> float:
        """Normalised inverse document frequency, floored at ``RARITY_FLOOR``.

        ``log((N+1)/(df+1)) / log(N+1)`` is 1.0 for a term no chunk contains and
        0.0 for a term every chunk contains; the floor then lifts that 0.0 so the
        term ranks low instead of vanishing. With no corpus at all there is
        nothing to compare against, and every term is treated as fully rare —
        the response says the corpus was empty, so this is never hidden.
        """
        n = self.total_chunks
        if n <= 0:
            return 1.0
        df = min(self.chunks_containing.get(concept.lower(), 0), n)
        raw = math.log((n + 1) / (df + 1)) / math.log(n + 1)
        return round(RARITY_FLOOR + (1 - RARITY_FLOOR) * raw, 4)


def corpus_stats(concepts: list[str], corpus_chunks: list[dict]) -> CorpusStats:
    counts: dict[str, int] = {}
    texts = [str(chunk.get("text", "")) for chunk in corpus_chunks]
    for concept in concepts:
        pattern = phrase_pattern(concept)
        if pattern is None:
            continue
        counts[concept.lower()] = sum(1 for text in texts if pattern.search(text))
    return CorpusStats(total_chunks=len(texts), chunks_containing=counts)


def phrase_length_weight(concept: str) -> float:
    words = len(re.findall(r"[a-z0-9]+", concept.lower()))
    return round(min(max(words, 1), MAX_PHRASE_WORDS) / MAX_PHRASE_WORDS, 4)


def score_concept_in_patent(
    concept: str,
    segmented: SegmentedPatent,
    stats: CorpusStats,
) -> dict | None:
    """Score *concept* against every section; return the best match, or ``None``.

    The finding names the single best-scoring section and lists the other
    sections the concept also appears in, so one concept produces one finding
    per patent rather than one per paragraph.
    """
    pattern = phrase_pattern(concept)
    if pattern is None:
        return None

    rarity = stats.rarity(concept)
    length = phrase_length_weight(concept)

    matches: list[tuple[float, int, PatentSection, int]] = []
    for order, section in enumerate(segmented.sections):
        occurrences = len(pattern.findall(section.text))
        if not occurrences:
            continue
        weight = SECTION_WEIGHTS[section_weight_key(section)]
        score = round(rarity * length * weight, 4)
        matches.append((score, order, section, occurrences))

    if not matches:
        return None

    # Highest score first; on a tie the earlier section wins, so the ordering is
    # stable from run to run.
    matches.sort(key=lambda item: (-item[0], item[1]))
    score, _order, best, occurrences = matches[0]

    return {
        "concept": concept,
        "score": score,
        "score_label": SCORE_LABEL,
        "components": {
            "term_rarity": rarity,
            "phrase_length": length,
            "section_weight": SECTION_WEIGHTS[section_weight_key(best)],
            "corpus_chunks": stats.total_chunks,
            "chunks_containing_term": stats.chunks_containing.get(concept.lower(), 0),
            "phrase_words": len(re.findall(r"[a-z0-9]+", concept.lower())),
            "occurrences_in_section": occurrences,
        },
        "section": {
            "id": best.id,
            "kind": best.kind,
            "label": best.label,
            "number": best.number,
            "independent": best.independent,
            "depends_on": list(best.depends_on),
            "excerpt": excerpt(best.text, pattern),
        },
        "also_in": [section.label for _s, _o, section, _n in matches[1:]],
        "matched_terms": sorted({m.group(0).lower() for m in pattern.finditer(best.text)}),
    }


def excerpt(text: str, pattern: re.Pattern[str], radius: int = 140) -> str:
    """The section text around the first match, so the reader sees it in context."""
    match = pattern.search(text)
    if not match:
        return text[: radius * 2]
    begin = max(0, match.start() - radius)
    finish = min(len(text), match.end() + radius)
    prefix = "…" if begin > 0 else ""
    suffix = "…" if finish < len(text) else ""
    return f"{prefix}{text[begin:finish].strip()}{suffix}"


__all__ = [
    "MAX_PHRASE_WORDS",
    "RARITY_FLOOR",
    "SCORE_EXPLANATION",
    "SCORE_LABEL",
    "SECTION_WEIGHTS",
    "CorpusStats",
    "corpus_stats",
    "excerpt",
    "phrase_length_weight",
    "phrase_pattern",
    "score_concept_in_patent",
    "section_weight_key",
]
