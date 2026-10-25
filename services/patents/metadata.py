"""Local validation of hand-entered patent metadata.

Everything here is typed in by the user — nothing is fetched. The rule is to
validate what *can* be checked locally and accept what cannot, rather than
rejecting a legitimate entry because it did not match a pattern:

* **Dates** must parse and be in a possible order (priority ≤ filing ≤
  publication). An impossible order is an error.
* **CPC / IPC codes** have one international shape (``G06F 16/3347``, or a
  subclass such as ``G06N``). A code that does not fit is an error, with the
  expected shape in the message.
* **Publication and application numbers** follow many national formats, so an
  unfamiliar one is accepted with a *warning*, never rejected.
* Names (assignee, inventors) and family identifiers are free text.
"""

from __future__ import annotations

import re
from datetime import date

# Section letter, two-digit class, subclass letter, then optionally
# main group / subgroup. "G06F", "G06F 16/3347", "H04L9/32".
_CLASSIFICATION_RE = re.compile(r"^[A-HY]\d{2}[A-Z](?:\s?\d{1,4}/\d{1,6})?$")

# Two-letter office code, digits (optionally separated), optional kind code.
# "US1234567B2", "EP 3 456 789 A1", "WO2020/123456", "US 2021/0123456 A1".
_PUBLICATION_RE = re.compile(r"^[A-Z]{2}\s?[\d][\d\s/,.\-]*\s?(?:[A-Z]\d?)?$")


class PatentMetadataError(ValueError):
    """Raised when entered metadata is impossible rather than merely unfamiliar."""


def normalise_code(code: str) -> str:
    """Upper-case and collapse the optional space before the main group."""
    compact = re.sub(r"\s+", " ", code.strip().upper())
    return re.sub(r"^([A-HY]\d{2}[A-Z])\s?(\d)", r"\1 \2", compact)


def normalise_codes(codes: list[str], scheme: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in codes:
        if not str(raw).strip():
            continue
        code = normalise_code(str(raw))
        if not _CLASSIFICATION_RE.match(code):
            raise PatentMetadataError(
                f"'{raw}' does not look like a {scheme} code. Expected a section letter, "
                "a two-digit class and a subclass letter, optionally followed by "
                "group/subgroup — for example G06F or G06F 16/3347."
            )
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def number_warnings(publication_number: str, application_number: str) -> list[str]:
    """Warnings (never errors) for numbers in an unfamiliar format."""
    warnings: list[str] = []
    for label, value in (
        ("publication number", publication_number),
        ("application number", application_number),
    ):
        value = (value or "").strip().upper()
        if value and not _PUBLICATION_RE.match(value):
            warnings.append(
                f"The {label} '{value}' is not in a format MAIROS recognises "
                "(e.g. US1234567B2). It has been stored as entered."
            )
    return warnings


def check_date_order(
    priority_date: date | None,
    filing_date: date | None,
    publication_date: date | None,
) -> None:
    """Raise when the dates are in an order that cannot happen."""
    ordered = [
        ("priority date", priority_date),
        ("filing date", filing_date),
        ("publication date", publication_date),
    ]
    present = [(name, value) for name, value in ordered if value is not None]
    for (earlier_name, earlier), (later_name, later) in zip(present, present[1:]):
        if earlier > later:
            raise PatentMetadataError(
                f"The {earlier_name} ({earlier.isoformat()}) is after the {later_name} "
                f"({later.isoformat()}). Dates must run priority → filing → publication."
            )


def clean_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        cleaned = " ".join(str(name).split())
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            out.append(cleaned)
    return out


__all__ = [
    "PatentMetadataError",
    "check_date_order",
    "clean_names",
    "normalise_code",
    "normalise_codes",
    "number_warnings",
]
