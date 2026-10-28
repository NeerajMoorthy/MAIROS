"""Deterministic concept extraction: the graph's fallback when no model can help.

Entity extraction normally asks the language model. When there is no model, or
the call fails (Groq's free tier refuses with HTTP 429 once its per-minute
token budget is spent), or the reply holds nothing usable, a paper would
otherwise add no concepts to the graph — and patent awareness, which matches
patent text against the graph's concepts, would find almost nothing.

This extractor needs no model. It keeps runs of content words between
punctuation and function words, counts every 1–3 word phrase inside those
runs, and keeps the phrases and acronyms ("CNN", "GSM") a text repeats.
Longer phrases are preferred over their own parts, and a plural is merged with
its singular. On the sample papers it yields "rail heads", "single-board
computer", "guided waves", "weld flaws", "track defects", "GSM", "GPS".
"""

from __future__ import annotations

import re

from services.literature.queries import SEARCH_STOPWORDS

# Words that are never a concept, or never part of one: section headings,
# hedges, reporting verbs and measurement units, on top of the search
# stopwords.
_NOT_CONCEPT = frozenset({
    "abstract", "method", "methods", "data", "results", "result", "conclusion", "conclusions",
    "limitations", "limitation", "open", "questions", "question", "note", "paper", "study",
    "studies", "work", "future", "whether", "unclear", "unknown", "may", "might", "could",
    "should", "would", "also", "only", "about", "more", "most", "less", "each", "every", "one",
    "two", "three", "four", "five", "first", "second", "new", "used", "using", "show", "shows",
    "shown", "found", "find", "finding", "test", "tested", "tests", "testing", "per", "via",
    "within", "without", "between", "into", "over", "under", "after", "before", "during",
    "while", "where", "when", "who", "than", "here", "its", "it", "they", "is", "are", "was",
    "be", "being", "had", "can", "not", "all", "any", "some", "same", "other", "both", "very",
    "much", "many", "few", "known", "invented", "fictional", "sample", "published", "research",
    "written", "case", "cases", "set", "sets", "part", "time", "times", "way", "ways", "need",
    "needs", "needed", "remains", "pair", "tell", "hold", "cut", "fell", "reached", "raised",
    "missed", "detected", "inspected", "compares", "sends", "trigger", "flagged", "flag",
    "report", "reports", "send", "clamped", "mounted", "captured", "pushed", "measured",
    "evaluate", "evaluated", "collected", "split", "classified", "runs", "run", "locates",
    "reflects", "contained", "including", "delayed", "arriving", "passing", "main", "et", "al",
    "mm", "cm", "km", "khz", "hz", "mhz", "ghz", "ms", "kb", "mb", "gb", "fig", "figure",
    "table", "section", "proposed", "propose", "present", "presents", "approach", "based",
    # The labels the Literature agent writes above each fetched abstract.
    "title", "authors", "author", "published", "venue", "year",
})
_STOP = SEARCH_STOPWORDS | _NOT_CONCEPT
_TOKEN = re.compile(r"[A-Za-z][A-Za-z\-]*[A-Za-z]|[A-Za-z]|\d+(?:\.\d+)?|[.,;:!?()\[\]\"]")
_WORD = re.compile(r"[A-Za-z][A-Za-z\-]*[A-Za-z]|[A-Za-z]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _runs(text: str) -> list[list[str]]:
    """Runs of content words, broken at punctuation, numbers and stopwords."""
    runs: list[list[str]] = []
    current: list[str] = []
    for token in _TOKEN.findall(text):
        if _WORD.fullmatch(token) and len(token) > 1 and token.lower() not in _STOP:
            current.append(token)
            continue
        if current:
            runs.append(current)
        current = []
    if current:
        runs.append(current)
    return runs


def _singular(key: str) -> str:
    return key[:-1] if key.endswith("s") and not key.endswith("ss") and len(key) > 3 else key


def concept_phrases(text: str, limit: int = 10) -> list[str]:
    """The concepts *text* repeats, best first."""
    counts: dict[str, int] = {}
    shown: dict[str, str] = {}
    for run in _runs(text):
        for size in (1, 2, 3):
            for start in range(len(run) - size + 1):
                gram = run[start : start + size]
                key = " ".join(word.lower() for word in gram)
                counts[key] = counts.get(key, 0) + 1
                shown.setdefault(key, " ".join(w if w.isupper() else w.lower() for w in gram))

    def is_acronym(key: str) -> bool:
        return shown[key].isupper() and 2 <= len(key) <= 6

    ranked: list[tuple[float, str]] = []
    for key, count in counts.items():
        words = key.count(" ") + 1
        if count >= 2 and (words > 1 or is_acronym(key)) or (words == 1 and count >= 4 and len(key) > 4):
            ranked.append((count * (1 + 0.6 * (words - 1)), key))
    ranked.sort(key=lambda item: (-item[0], item[1]))

    def left_fragment(key: str) -> bool:
        """'lightweight convolutional neural' beside 'convolutional neural
        network': a longer term cut by the three-word window. Noun phrases end
        with their head noun, so the window that reaches further keeps it."""
        words = key.split()
        if len(words) < 3:
            return False
        tail = " ".join(words[1:]) + " "
        return any(
            other.startswith(tail) and other.count(" ") == key.count(" ") and counts[other] == counts[key]
            for other in counts
        )

    kept: list[str] = []
    seen_singular: set[str] = set()
    for _, key in ranked:
        if _singular(key) in seen_singular or left_fragment(key):
            continue
        # A part of a kept phrase adds nothing unless it stands alone more often.
        if any(f" {key} " in f" {other} " and counts[other] >= counts[key] for other in kept):
            continue
        kept.append(key)
        seen_singular.add(_singular(key))
        if len(kept) == limit:
            break
    return [shown[key] for key in kept]


def co_occurring(names: list[str], text: str, limit: int = 12) -> list[tuple[str, str]]:
    """Pairs of *names* that appear in the same sentence of *text*, first seen first."""
    pairs: list[tuple[str, str]] = []
    lowered = [(name, name.lower()) for name in names]
    for sentence in _SENTENCE.split(text):
        present = [name for name, low in lowered if low in sentence.lower()]
        for i, first in enumerate(present):
            for second in present[i + 1 :]:
                # "guided waves" inside "ultrasonic guided waves" is not a relation.
                if first.lower() in second.lower() or second.lower() in first.lower():
                    continue
                if (first, second) not in pairs and (second, first) not in pairs:
                    pairs.append((first, second))
                    if len(pairs) == limit:
                        return pairs
    return pairs


__all__ = ["co_occurring", "concept_phrases"]
