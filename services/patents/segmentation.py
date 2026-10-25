"""Split pasted patent text into abstract, description and numbered claims.

Overlap used to be matched against a patent's whole text, so a finding pointed
at a document rather than at anything a reader could look up. Segmenting first
lets every finding name the claim or section it came from — and an overlap with
a dependent claim reads differently from one with an independent claim, so the
dependency is recorded too.

Claim text in the wild is messy, and the parser is deliberately conservative
about it:

* **Numbering styles** — ``1.``, ``1)``, ``(1)``, ``[1]``, ``[0001]``,
  ``Claim 1:``, ``[Claim 1]`` — are all accepted, but a marker only counts when
  it carries the *next* expected number. A wrapped line that happens to start
  with ``2.5 mm`` or ``claim 1, wherein`` is therefore never mistaken for a new
  claim.
* **Wrapped claims** keep everything up to the next accepted marker.
* **Dependencies** come from "of claim 1", "according to any one of claims 1
  to 3" and similar. Only references to *earlier* claims are accepted as
  parents; anything else is kept as an unresolved reference rather than guessed.
* **Failure is reported, not hidden.** When no structure can be found the whole
  text becomes one section and ``segmented`` is ``False`` with a reason — the
  caller says "matched against the whole text" instead of pretending a claim
  structure exists.

Nothing here interprets what a claim *means*. It finds where the text says each
claim starts and which earlier claims it names; that is all.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

# Section kinds. "document" is the whole-text fallback.
ABSTRACT = "abstract"
DESCRIPTION = "description"
CLAIM = "claim"
DOCUMENT = "document"

# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------
_HEADING_NAMES: tuple[tuple[str, str], ...] = (
    (ABSTRACT, r"abstract(?:\s+of\s+the\s+disclosure)?"),
    (
        CLAIM,
        r"claims|claim|what\s+is\s+claimed\s+is|what\s+we\s+claim\s+is|we\s+claim|i\s+claim|"
        r"the\s+invention\s+claimed\s+is|patent\s+claims",
    ),
    (
        DESCRIPTION,
        r"(?:detailed\s+)?description(?:\s+of\s+(?:the\s+)?(?:preferred\s+)?"
        r"(?:embodiments?|invention|drawings))?|background(?:\s+of\s+the\s+invention)?|"
        r"summary(?:\s+of\s+the\s+invention)?|(?:technical\s+)?field(?:\s+of\s+the\s+invention)?|"
        r"brief\s+description\s+of\s+(?:the\s+)?drawings|specification",
    ),
)

# A heading is a line that is nothing but the heading word(s), or the heading
# followed by an explicit separator and inline text ("Abstract: A system...").
# Requiring the separator is what stops "Claim 1: A system" or a sentence that
# merely begins "Description of the prior art is..." from being read as one.
_HEADING_RE = re.compile(
    r"^[ \t]*(?:[IVX]+\.|\d{1,2}\.)?[ \t]*(?P<name>"
    + "|".join(f"(?P<{kind}>{pattern})" for kind, pattern in _HEADING_NAMES)
    + r")[ \t]*(?:(?P<sep>[:\-–—])[ \t]*(?P<rest>.*?))?[ \t]*$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Claim markers
# ---------------------------------------------------------------------------
_CLAIM_MARKER_RE = re.compile(
    r"^[ \t]*(?:"
    r"\[\s*claim\s+(?P<n1>\d{1,3})\s*\]"  # [Claim 1]
    r"|claim\s+(?P<n2>\d{1,3})(?!\s*[,;])(?!\s+(?:wherein|or|and|to|through)\b)\s*[:.)\-–—]?"  # Claim 1:
    r"|\[\s*(?P<n3>\d{1,4})\s*\]"  # [1] or [0001]
    r"|\(\s*(?P<n4>\d{1,3})\s*\)"  # (1)
    r"|(?P<n5>\d{1,3})\s*[.)](?=\s)"  # 1.  1)   — but not "2.5 mm"
    r")[ \t]*",
    re.IGNORECASE | re.MULTILINE,
)

# Words that appear in claims and almost never in a numbered list of section
# titles. Used only when there is no "Claims" heading to go on.
_CLAIM_LANGUAGE_RE = re.compile(
    r"\b(comprising|comprises|wherein|consisting|characteri[sz]ed|including|"
    r"of\s+claim|according\s+to\s+claim)\b",
    re.IGNORECASE,
)

# "of claim 1", "claims 1 to 3", "any one of claims 1, 2 or 5", "claim 1-4"
_REFERENCE_RE = re.compile(
    r"\bclaims?\s+(?P<refs>\d{1,3}(?:\s*(?:,|or|and|to|through|-|–)\s*(?:claims?\s+)?\d{1,3})*)",
    re.IGNORECASE,
)
_RANGE_RE = re.compile(r"(\d{1,3})\s*(?:to|through|-|–)\s*(?:claims?\s+)?(\d{1,3})", re.IGNORECASE)


@dataclass
class PatentSection:
    """One addressable part of a patent: the abstract, a description block, or a claim."""

    id: str
    kind: str
    label: str
    text: str
    start: int
    end: int
    number: int | None = None
    independent: bool | None = None
    depends_on: list[int] = field(default_factory=list)
    unresolved_references: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SegmentedPatent:
    """The result of segmentation, including whether it actually succeeded."""

    sections: list[PatentSection]
    segmented: bool
    notes: list[str] = field(default_factory=list)

    @property
    def claims(self) -> list[PatentSection]:
        return [s for s in self.sections if s.kind == CLAIM and s.number is not None]

    def as_dict(self) -> dict:
        claims = self.claims
        return {
            "segmented": self.segmented,
            "notes": list(self.notes),
            "claim_count": len(claims),
            "independent_claims": [c.number for c in claims if c.independent],
            "dependent_claims": [c.number for c in claims if c.independent is False],
            "sections": [s.as_dict() for s in self.sections],
        }


# ---------------------------------------------------------------------------
def _clean(text: str) -> str:
    """Collapse whitespace so wrapped lines read as one passage."""
    return " ".join(text.split())


def _expand_references(raw: str) -> list[int]:
    """Turn "1, 2 or 5" / "1 to 3" into an ordered list of claim numbers."""
    numbers: list[int] = []
    consumed: list[tuple[int, int]] = []
    for match in _RANGE_RE.finditer(raw):
        low, high = int(match.group(1)), int(match.group(2))
        if low <= high and high - low <= 200:  # a typo must not explode the list
            numbers.extend(range(low, high + 1))
        consumed.append(match.span())

    remainder = raw
    for begin, finish in reversed(consumed):
        remainder = remainder[:begin] + " " + remainder[finish:]
    numbers.extend(int(n) for n in re.findall(r"\d{1,3}", remainder))

    seen: set[int] = set()
    ordered: list[int] = []
    for number in numbers:
        if number not in seen:
            seen.add(number)
            ordered.append(number)
    return ordered


def _claim_references(number: int, text: str) -> tuple[list[int], list[int]]:
    """Parent claims named in *text*, split into (valid, unresolved).

    A claim can only depend on a claim that comes before it, so a reference to
    itself or to a later number is not treated as a parent — it is kept as
    unresolved so a reader can see it rather than having it silently dropped.
    """
    valid: list[int] = []
    unresolved: list[int] = []
    for match in _REFERENCE_RE.finditer(text):
        for ref in _expand_references(match.group("refs")):
            target = valid if 0 < ref < number else unresolved
            if ref not in target:
                target.append(ref)
    return sorted(valid), sorted(unresolved)


def _parse_claims(text: str, offset: int) -> list[PatentSection]:
    """Split a claims block into numbered claims.

    A marker is accepted only when it carries the next expected number
    (starting at 1), which is what keeps wrapped lines and stray numbers inside
    a claim from being read as the start of a new one.
    """
    accepted: list[tuple[int, int, int]] = []  # (number, marker_start, body_start)
    expected = 1
    for match in _CLAIM_MARKER_RE.finditer(text):
        raw = next(match.group(g) for g in ("n1", "n2", "n3", "n4", "n5") if match.group(g))
        number = int(raw)
        if number != expected:
            continue
        accepted.append((number, match.start(), match.end()))
        expected += 1

    claims: list[PatentSection] = []
    for index, (number, marker_start, body_start) in enumerate(accepted):
        body_end = accepted[index + 1][1] if index + 1 < len(accepted) else len(text)
        body = _clean(text[body_start:body_end])
        if not body:
            continue
        parents, unresolved = _claim_references(number, body)
        claims.append(
            PatentSection(
                id=f"claim-{number}",
                kind=CLAIM,
                label=f"Claim {number}",
                text=body,
                start=offset + marker_start,
                end=offset + body_end,
                number=number,
                # A claim worded as dependent stays dependent even when the
                # claim it names cannot be resolved — calling it independent
                # would overstate it, and its weight would rise to match.
                independent=not parents and not unresolved,
                depends_on=parents,
                unresolved_references=unresolved,
            )
        )
    return claims


def _find_headings(text: str) -> list[tuple[str, str, int, int]]:
    """Every heading line as ``(kind, label, line_start, content_start)``."""
    headings: list[tuple[str, str, int, int]] = []
    position = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        match = _HEADING_RE.match(stripped)
        if match and (match.group("rest") is None or match.group("sep")):
            kind = next(k for k, _ in _HEADING_NAMES if match.group(k))
            label = _clean(match.group("name")).capitalize()
            rest = match.group("rest")
            content_start = position + (match.start("rest") if rest else len(line))
            headings.append((kind, label, position, content_start))
        position += len(line)
    return headings


def _looks_like_claims(claims: list[PatentSection]) -> bool:
    """Without a heading, numbered text counts as claims only if it reads like them."""
    if not claims:
        return False
    worded = sum(1 for claim in claims if _CLAIM_LANGUAGE_RE.search(claim.text))
    return worded * 2 >= len(claims)


# ---------------------------------------------------------------------------
def segment_patent(text: str) -> SegmentedPatent:
    """Segment pasted patent text.

    Args:
        text: Whatever the user pasted — an abstract, a claims list, a full
            specification, or an unstructured blob.

    Returns:
        A :class:`SegmentedPatent`. ``segmented`` is ``False`` when no structure
        was found, in which case there is exactly one ``document`` section
        covering the whole text and ``notes`` says so.
    """
    original = text or ""
    if not original.strip():
        return SegmentedPatent(sections=[], segmented=False, notes=["No patent text was supplied."])

    sections: list[PatentSection] = []
    notes: list[str] = []
    headings = _find_headings(original)

    if headings:
        lead = original[: headings[0][2]]
        if lead.strip():
            sections.append(
                PatentSection(
                    id="unlabelled",
                    kind=DESCRIPTION,
                    label="Text before the first heading",
                    text=_clean(lead),
                    start=0,
                    end=headings[0][2],
                )
            )

        counters: dict[str, int] = {}
        for index, (kind, label, _line_start, content_start) in enumerate(headings):
            end = headings[index + 1][2] if index + 1 < len(headings) else len(original)
            body = original[content_start:end]
            if not body.strip():
                continue

            if kind == CLAIM:
                claims = _parse_claims(body, content_start)
                if claims:
                    sections.extend(claims)
                else:
                    notes.append(
                        "A claims heading was found, but individual numbered claims "
                        "could not be identified; the claims text is matched as one block."
                    )
                    sections.append(
                        PatentSection(
                            id="claims-block",
                            kind=CLAIM,
                            label="Claims (not individually numbered)",
                            text=_clean(body),
                            start=content_start,
                            end=end,
                        )
                    )
                continue

            counters[kind] = counters.get(kind, 0) + 1
            suffix = f"-{counters[kind]}" if counters[kind] > 1 else ""
            sections.append(
                PatentSection(
                    id=f"{kind}{suffix}",
                    kind=kind,
                    label=label,
                    text=_clean(body),
                    start=content_start,
                    end=end,
                )
            )
    else:
        claims = _parse_claims(original, 0)
        if _looks_like_claims(claims):
            first_start = claims[0].start
            lead = original[:first_start]
            if lead.strip():
                sections.append(
                    PatentSection(
                        id="unlabelled",
                        kind=DESCRIPTION,
                        label="Text before the claims",
                        text=_clean(lead),
                        start=0,
                        end=first_start,
                    )
                )
            sections.extend(claims)
            notes.append("No section headings were found; numbered claims were identified from their wording.")

    if not sections:
        notes.append(
            "No abstract, description or numbered claims could be identified, so "
            "overlaps are matched against the whole text and cannot point at a "
            "specific claim."
        )
        return SegmentedPatent(
            sections=[
                PatentSection(
                    id="document",
                    kind=DOCUMENT,
                    label="Whole text (not segmented)",
                    text=_clean(original),
                    start=0,
                    end=len(original),
                )
            ],
            segmented=False,
            notes=notes,
        )

    return SegmentedPatent(sections=sections, segmented=True, notes=notes)


__all__ = [
    "ABSTRACT",
    "CLAIM",
    "DESCRIPTION",
    "DOCUMENT",
    "PatentSection",
    "SegmentedPatent",
    "segment_patent",
]
