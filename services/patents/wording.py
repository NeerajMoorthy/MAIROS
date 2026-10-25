"""The compiled form of the patent feature's boundary: no legal conclusions.

Anything the patent feature puts in front of a person — agent output, API
responses, UI copy, exports, the printable view — must not read as a legal
opinion. This module lists the phrasing that would, and finds it.

Two kinds of text legitimately *name* those conclusions in order to disclaim
them: the standing disclaimers themselves, and the explanation of what the
similarity score is not. Those exact constants are removed before scanning, so
an exception is a specific, reviewed sentence — never a blanket pass for any
text that happens to contain the word "not".
"""

from __future__ import annotations

import re

from .scoring import SCORE_EXPLANATION
from .sources import DISCLAIMER, FULL_DISCLAIMER, NO_OVERLAP_NOTE

# Language implying a legal conclusion. Stems, so "infringe", "infringes",
# "infringing" and "infringement" are all caught by one entry.
LEGAL_CONCLUSION_PATTERNS: tuple[str, ...] = (
    r"infring\w*",
    r"violat\w*",
    r"clear\s+to",
    r"safe\s+to",
    r"patentable",
    r"invalid\w*",
    r"freedom[\s\-]+to[\s\-]+operate",
    r"(?:legally|legal)\s+(?:clear|safe|risk)\w*",
    r"(?:no|low|high|moderate)\s+(?:legal\s+)?risk",
)

_LEGAL_RE = re.compile(r"\b(?:" + "|".join(LEGAL_CONCLUSION_PATTERNS) + r")\b", re.IGNORECASE)

# Reviewed sentences that name a conclusion only to disclaim it.
PERMITTED_EXPLANATIONS: tuple[str, ...] = (
    FULL_DISCLAIMER,
    DISCLAIMER,
    NO_OVERLAP_NOTE,
    SCORE_EXPLANATION,
)


def legal_conclusion_terms(text: str) -> list[str]:
    """Every legal-conclusion phrase in *text*, after removing permitted sentences."""
    remaining = str(text or "")
    # Longest first, so the full disclaimer is removed before the short one
    # it contains.
    for allowed in sorted(PERMITTED_EXPLANATIONS, key=len, reverse=True):
        remaining = remaining.replace(allowed, " ")
    return [match.group(0) for match in _LEGAL_RE.finditer(remaining)]


def contains_legal_conclusion(text: str) -> bool:
    return bool(legal_conclusion_terms(text))


__all__ = [
    "LEGAL_CONCLUSION_PATTERNS",
    "PERMITTED_EXPLANATIONS",
    "contains_legal_conclusion",
    "legal_conclusion_terms",
]
