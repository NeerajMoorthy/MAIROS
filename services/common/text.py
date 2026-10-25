"""Text normalisation for names that are matched against other text.

Language models write typographic characters that look identical to ASCII but
are not: a live `gpt-oss-120b` extraction returned "retrieval‑augmented
approach" with U+2011 (non-breaking hyphen). As a graph node, that name never
matched "retrieval-augmented" in a document or a question, so the graph could
not boost the very passages it was extracted from.

Only characters that are *the same symbol* in practice are folded. Em dashes
and horizontal bars are left alone: they separate clauses rather than join a
compound word, so turning them into hyphens would change a name, not tidy it.
"""

from __future__ import annotations

import re

# Hyphen look-alikes inside compound words → "-".
_HYPHENS = {
    "‐": "-",  # hyphen
    "‑": "-",  # non-breaking hyphen (what gpt-oss produced)
    "‒": "-",  # figure dash
    "–": "-",  # en dash ("text–image", "2019–2021")
    "−": "-",  # minus sign
    "﹣": "-",  # small hyphen-minus
    "－": "-",  # full-width hyphen-minus
}

# Space look-alikes → " ".
_SPACES = {
    ch: " "
    for ch in (
        " ",  # no-break space
        " ", " ", " ", " ", " ",
        " ",  # figure space
        " ", " ", " ",  # punctuation / thin / hair spaces
        " ",  # narrow no-break space
        " ", "　",
    )
}

# Invisible characters that only break matching → removed.
_INVISIBLE = {ch: None for ch in ("­", "​", "‌", "‍", "⁠", "﻿")}

_TABLE = str.maketrans({**_HYPHENS, **_SPACES, **_INVISIBLE})


def normalize_name(value: str | None) -> str:
    """Fold typographic hyphens and spaces to ASCII and collapse whitespace."""
    return re.sub(r"\s+", " ", str(value or "").translate(_TABLE)).strip()


__all__ = ["normalize_name"]
