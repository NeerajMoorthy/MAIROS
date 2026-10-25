"""The paper record every literature source is normalised into.

Each source (arXiv, OpenAlex, Semantic Scholar) describes a paper differently.
They are all turned into one plain ``dict`` with the keys below, so the rest of
MAIROS — indexing, the knowledge graph, references, the Papers list — never
needs to know where a paper came from.

Links are allowlisted here, the same way patent links are: a URL is kept only
when it points at one of the public scholarly hosts the sources themselves
use. Anything else (a publisher mirror, a redirect, a malformed value) is
dropped rather than shown, so a link rendered in the UI is never something a
metadata record smuggled in.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Display name of each source, keyed by its short id.
SOURCE_NAMES: dict[str, str] = {
    "arxiv": "arXiv",
    "openalex": "OpenAlex",
    "semantic_scholar": "Semantic Scholar",
}

# Document-id prefix for each kind of identifier a fetched paper can be indexed
# under. The Novelty agent reads these back to tell fetched abstracts apart from
# the user's own uploads, so the two lists must stay in step.
DOCUMENT_PREFIXES: dict[str, str] = {
    "arxiv": "arxiv_",
    "doi": "doi_",
    "openalex": "openalex_",
    "semantic_scholar": "s2_",
}
FETCHED_PREFIXES: tuple[str, ...] = tuple(DOCUMENT_PREFIXES.values())

# Public scholarly hosts a paper link may point at.
ALLOWED_LINK_HOSTS: frozenset[str] = frozenset(
    {
        "arxiv.org",
        "export.arxiv.org",
        "doi.org",
        "openalex.org",
        "semanticscholar.org",
        "www.semanticscholar.org",
    }
)

PAPER_FIELDS = (
    "id",
    "title",
    "authors",
    "abstract",
    "published",
    "year",
    "url",
    "pdf_url",
    "doi",
    "arxiv_id",
    "venue",
    "citation_count",
    "primary_category",
    "source",
    "sources",
    "source_ids",
)


def safe_link(url: str | None) -> str:
    """*url* if it is https/http on an allowlisted host, otherwise ``""``."""
    value = str(url or "").strip()
    if not value:
        return ""
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https"):
        return ""
    host = (parsed.hostname or "").lower()
    return value if host in ALLOWED_LINK_HOSTS else ""


def normalise_doi(value: str | None) -> str:
    """A bare, lowercase DOI (``10.x/y``), whatever form it arrived in."""
    doi = str(value or "").strip().lower()
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi)
    return doi if doi.startswith("10.") else ""


_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$")
_ARXIV_VERSION = re.compile(r"v\d+$")


def bare_arxiv_id(value: str | None) -> str:
    """An arXiv id without its version suffix: ``2005.11401v4`` → ``2005.11401``."""
    text = str(value or "").strip().lower()
    match = _ARXIV_DOI.match(text)
    if match:
        text = match.group(1)
    text = text.rsplit("/abs/", 1)[-1]
    return _ARXIV_VERSION.sub("", text)


def title_key(title: str | None) -> str:
    """Letters and digits only, lowercased — two spellings of one title match."""
    return re.sub(r"[^a-z0-9]+", "", str(title or "").lower())


def year_of(value: object) -> str:
    """The four-digit year at the start of a date or year value, or ``""``."""
    match = re.match(r"\s*(\d{4})", str(value or ""))
    return match.group(1) if match else ""


def new_paper(source: str, source_id: str, **fields) -> dict:
    """A paper record with every field present, tagged with where it came from."""
    paper: dict = {
        "id": source_id,
        "title": "",
        "authors": [],
        "abstract": "",
        "published": "",
        "year": "",
        "url": "",
        "pdf_url": "",
        "doi": "",
        "arxiv_id": "",
        "venue": "",
        "citation_count": None,
        "primary_category": "",
        "source": SOURCE_NAMES[source],
        "sources": [SOURCE_NAMES[source]],
        "source_ids": {source: source_id},
    }
    paper.update(fields)
    paper["title"] = " ".join(str(paper["title"]).split())
    paper["abstract"] = " ".join(str(paper["abstract"]).split())
    paper["authors"] = [str(a).strip() for a in paper["authors"] if str(a).strip()][:12]
    paper["doi"] = normalise_doi(paper["doi"])
    paper["year"] = paper["year"] or year_of(paper["published"])
    paper["url"] = safe_link(paper["url"])
    paper["pdf_url"] = safe_link(paper["pdf_url"])
    return paper


def _identifiers(paper: dict) -> list[tuple[str, str]]:
    """Every identifier a paper is known by, the most widely shared first.

    A paper's identity must not depend on which source happened to answer a
    search: when it did (the first source's own id was used), a paper found
    through OpenAlex one day and arXiv the next was stored and indexed twice.
    The arXiv id leads because every source reports it for a preprint; a
    journal DOI comes next, then each source's own id.
    """
    source_ids = paper.get("source_ids") or {}
    found: list[tuple[str, str]] = []
    arxiv = paper.get("arxiv_id") or bare_arxiv_id(source_ids.get("arxiv"))
    if arxiv:
        found.append(("arxiv", arxiv))
    doi = normalise_doi(paper.get("doi"))
    if doi and not doi.startswith("10.48550/"):
        found.append(("doi", doi))
    for source in ("openalex", "semantic_scholar"):
        if source_ids.get(source):
            found.append((source, str(source_ids[source])))
    return found


def paper_id_for(paper: dict) -> str:
    """A paper's stable id, the same whichever sources returned it."""
    identifiers = _identifiers(paper)
    if identifiers:
        kind, value = identifiers[0]
        return f"{kind}:{value}"
    return str(paper.get("id", ""))


def document_id_for(paper: dict) -> str:
    """The id a fetched paper's abstract is indexed under."""
    identifiers = _identifiers(paper)
    if identifiers:
        kind, value = identifiers[0]
        return f"{DOCUMENT_PREFIXES[kind]}{value}"
    # A record built before ``source_ids`` existed came from arXiv.
    return f"{DOCUMENT_PREFIXES['arxiv']}{paper.get('id', '')}"


def document_aliases(paper: dict) -> set[str]:
    """Other document ids this paper may already be indexed under.

    Covers every identifier it is known by now, and the ids earlier builds
    wrote — the versioned arXiv id (``arxiv_2005.11401v4``) and each source's
    own id — so re-indexing a paper replaces its earlier copies instead of
    adding another.
    """
    source_ids = paper.get("source_ids") or {}
    aliases = {f"{DOCUMENT_PREFIXES[kind]}{value}" for kind, value in _identifiers(paper)}
    for source, value in source_ids.items():
        if value and source in DOCUMENT_PREFIXES:
            aliases.add(f"{DOCUMENT_PREFIXES[source]}{value}")
    aliases.discard(document_id_for(paper))
    return aliases


def paper_aliases(paper: dict) -> set[str]:
    """Other ids this paper may already be stored under in a project's list."""
    aliases = {f"{kind}:{value}" for kind, value in _identifiers(paper)}
    aliases.update(str(v) for v in (paper.get("source_ids") or {}).values() if v)
    aliases.discard(paper_id_for(paper))
    return aliases


def source_name_for_document(document_id: str) -> str:
    """Which source a fetched abstract's document id names, or ``""``.

    A DOI-keyed id names no source, so callers that know which sources a
    paper actually came from should prefer that.
    """
    for kind, prefix in DOCUMENT_PREFIXES.items():
        if str(document_id).startswith(prefix):
            return SOURCE_NAMES.get(kind, "")
    return ""


__all__ = [
    "ALLOWED_LINK_HOSTS",
    "DOCUMENT_PREFIXES",
    "FETCHED_PREFIXES",
    "PAPER_FIELDS",
    "SOURCE_NAMES",
    "bare_arxiv_id",
    "document_aliases",
    "document_id_for",
    "new_paper",
    "normalise_doi",
    "paper_aliases",
    "paper_id_for",
    "safe_link",
    "source_name_for_document",
    "title_key",
    "year_of",
]
