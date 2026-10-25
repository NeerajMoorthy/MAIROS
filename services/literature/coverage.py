"""The coverage report: what a literature search actually looked at.

Every statement MAIROS makes from fetched papers — a gap, a comparison, "not
found in this project's sources" — is only as strong as the search behind it.
This report states that search's limits next to the results: which sources
answered, which failed, how many papers were found and kept, which years they
span, and warnings when the set is too small or too narrow for absence to mean
anything. It is computed from the search itself; no model writes any of it.
"""

from __future__ import annotations

from datetime import date

from .papers import SOURCE_NAMES

# Below this many papers, "no source mentions X" says almost nothing.
SMALL_CORPUS = 5
# The newest paper being older than this many years suggests a stale set.
STALE_YEARS = 3

SCOPE_NOTE = (
    "This is a targeted search of paper titles and abstracts, not a systematic "
    "review. Full texts were not read, and work outside these sources, or "
    "phrased differently from these queries, may be missing."
)


def build_coverage(
    queries: list[dict],
    runs: list,
    found: int,
    kept: list[dict],
    duplicates: int,
    *,
    query_note: str = "",
    ignored_sources: list[str] | None = None,
    today: date | None = None,
) -> dict:
    """Summarise one search. ``runs`` are the sources' ``SourceRun`` results.

    ``ignored_sources`` are configured source names MAIROS does not know.
    """
    today = today or date.today()
    answered = [run for run in runs if run.status == "ok"]
    years = sorted(int(p["year"]) for p in kept if str(p.get("year", "")).isdigit())
    by_source: dict[str, int] = {}
    for paper in kept:
        for name in paper.get("sources", []):
            by_source[name] = by_source.get(name, 0) + 1
    without_abstract = sum(1 for p in kept if not p.get("abstract"))

    warnings: list[str] = []
    if ignored_sources:
        warnings.append(
            f"Unknown source name(s) in LITERATURE_SOURCES were ignored: "
            f"{', '.join(ignored_sources)}. Known sources: arxiv, openalex, semantic_scholar."
        )
    if not runs:
        # Not an outage: nothing was asked. Saying "could not be reached" sent
        # the reader to check their network instead of the setting.
        warnings.append(
            "No literature source is configured, so nothing was searched. Set "
            "LITERATURE_SOURCES to one or more of arxiv, openalex, semantic_scholar."
        )
    elif not answered:
        warnings.append(
            "No literature source could be reached, so nothing was searched. "
            "Results below come only from documents already in this project."
        )
    else:
        failed = [run.name for run in runs if run.status != "ok"]
        if failed:
            warnings.append(
                f"{', '.join(failed)} did not answer, so this search covers "
                f"{', '.join(run.name for run in answered)} only."
            )
        if len(kept) < SMALL_CORPUS:
            warnings.append(
                f"Only {len(kept)} paper(s) were found. That is too few for a gap or "
                "'not found' result to say much about the field — broaden the topic "
                "or add papers by hand."
            )
        if years and years[-1] < today.year - STALE_YEARS:
            warnings.append(
                f"The newest paper found is from {years[-1]}; recent work may be missing."
            )
        if without_abstract:
            warnings.append(
                f"{without_abstract} paper(s) have no abstract in the source metadata "
                "and are represented by their title only."
            )

    return {
        "searched_on": today.isoformat(),
        "queries": queries,
        "query_note": query_note,
        "sources": [run.as_dict() for run in runs],
        "configured_sources": [run.name for run in runs],
        "records_returned": sum(run.returned for run in runs),
        "papers_found": found,
        "papers_kept": len(kept),
        "duplicates_merged": duplicates,
        "papers_by_source": by_source,
        "year_range": [years[0], years[-1]] if years else None,
        "full_text_read": False,
        "warnings": warnings,
        "scope_note": SCOPE_NOTE,
    }


def join_names(names: list[str]) -> str:
    """Join names as `A`, `A and B` or `A, B and C`; empty for none."""
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " and " + names[-1]


def describe_scope(coverage: dict | None) -> str:
    """One line saying which sources were searched and where the kept papers came from.

    These are two different facts and used to be one: a live run printed
    "8 abstract(s) from arXiv, OpenAlex" when arXiv had answered but every one
    of the 8 kept papers came from OpenAlex. A source that did not answer is
    not listed here; the coverage warnings name it.
    """
    if not coverage:
        return ""
    if not coverage.get("sources"):
        return "no literature source (none is configured)"
    answered = [s["name"] for s in coverage.get("sources", []) if s.get("status") == "ok"]
    if not answered:
        return "no literature source (none could be reached)"

    queries = len(coverage.get("queries", []))
    searched = (
        f"{join_names(answered)} ({queries} quer{'y' if queries == 1 else 'ies'}, "
        f"{coverage.get('searched_on')})"
    )
    kept = coverage.get("papers_kept", 0)
    if not kept:
        return f"{searched}; no paper was found"

    counts = {name: n for name, n in (coverage.get("papers_by_source") or {}).items() if n}
    origins = [name for name in SOURCE_NAMES.values() if name in counts]
    origins += sorted(name for name in counts if name not in origins)
    if len(origins) == 1:
        return f"{searched}; kept {kept} abstract(s), all from {origins[0]}"
    if origins:
        breakdown = ", ".join(f"{counts[name]} from {name}" for name in origins)
        if sum(counts.values()) > kept:
            breakdown += " (some found by more than one)"
        return f"{searched}; kept {kept} abstract(s): {breakdown}"
    return f"{searched}; kept {kept} abstract(s)"


__all__ = [
    "SCOPE_NOTE",
    "SMALL_CORPUS",
    "SOURCE_NAMES",
    "build_coverage",
    "describe_scope",
    "join_names",
]
