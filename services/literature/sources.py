"""Literature sources: arXiv, OpenAlex and Semantic Scholar.

Each source turns a list of search queries into ranked lists of paper records
(see ``papers.py``) and reports how the search went. A source that cannot be
reached, times out, or is rate limited reports that and returns nothing; it
never raises, so one unavailable service narrows a search instead of ending it.

All three are free public APIs that serve paper *metadata and abstracts*.
Nothing here downloads a paper's full text.

Parsing is kept in plain functions (``parse_arxiv`` and friends) so it can be
tested against recorded responses without a network.
"""

from __future__ import annotations

import asyncio
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import httpx

from .papers import SOURCE_NAMES, bare_arxiv_id, new_paper, normalise_doi

USER_AGENT = "MAIROS/0.3 (research assistant; metadata search)"

ARXIV_API = "https://export.arxiv.org/api/query"
OPENALEX_API = "https://api.openalex.org/works"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"

_ATOM = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

_STOPWORDS = {
    "what", "which", "how", "why", "does", "did", "the", "and", "for", "with",
    "about", "find", "papers", "paper", "recent", "work", "on", "of", "in", "a",
    "an", "is", "are", "me", "show", "search", "give", "latest", "using", "use",
}


@dataclass
class SourceRun:
    """What one source returned for a search, and how the search went."""

    source: str
    status: str = "ok"  # ok | failed | rate_limited
    detail: str = ""
    # One ranked list per request the source answered, best match first.
    ranked: list[list[dict]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return SOURCE_NAMES[self.source]

    @property
    def returned(self) -> int:
        return sum(len(papers) for papers in self.ranked)

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "name": self.name,
            "status": self.status,
            "returned": self.returned,
            "detail": self.detail,
        }


def _describe_failure(exc: Exception) -> tuple[str, str]:
    """A status and a short, user-readable reason for a failed request."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429:
            return "rate_limited", "The service asked MAIROS to slow down (HTTP 429)."
        return "failed", f"The service answered HTTP {code}."
    if isinstance(exc, httpx.TimeoutException):
        return "failed", "The request timed out."
    if isinstance(exc, httpx.TransportError):
        return "failed", "The service could not be reached."
    return "failed", f"The response could not be read ({type(exc).__name__})."


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------
def arxiv_query(text: str) -> str:
    """Turn natural-language text into an arXiv ``search_query`` expression."""
    words = [
        w.strip(".,?!:;\"'()")
        for w in (text or "").split()
        if w.strip(".,?!:;\"'()").lower() not in _STOPWORDS and len(w.strip(".,?!:;\"'()")) > 2
    ]
    terms = words[:6] or (text or "machine learning").split()[:4]
    return " AND ".join(f"all:{term}" for term in terms)


def _atom_text(node, path: str) -> str:
    found = node.find(path, _ATOM)
    if found is None or found.text is None:
        return ""
    return " ".join(found.text.split())


def parse_arxiv(xml_text: str) -> list[dict]:
    """Paper records from an arXiv Atom feed."""
    root = ET.fromstring(xml_text)
    papers: list[dict] = []
    for entry in root.findall("atom:entry", _ATOM):
        title = _atom_text(entry, "atom:title")
        entry_id = _atom_text(entry, "atom:id")
        if not title or not entry_id:
            continue

        pdf_url = ""
        for link in entry.findall("atom:link", _ATOM):
            if link.get("title") == "pdf":
                pdf_url = link.get("href", "")

        category = entry.find("arxiv:primary_category", _ATOM)
        arxiv_id = entry_id.rsplit("/", 1)[-1]
        published = _atom_text(entry, "atom:published")
        papers.append(
            new_paper(
                "arxiv",
                arxiv_id,
                title=title,
                authors=[_atom_text(a, "atom:name") for a in entry.findall("atom:author", _ATOM)],
                abstract=_atom_text(entry, "atom:summary"),
                published=published,
                year=published[:4],
                url=entry_id,
                pdf_url=pdf_url,
                doi=_atom_text(entry, "arxiv:doi"),
                arxiv_id=bare_arxiv_id(arxiv_id),
                venue=_atom_text(entry, "arxiv:journal_ref"),
                primary_category=category.get("term", "") if category is not None else "",
            )
        )
    return papers


class ArxivSource:
    """arXiv's Atom API. All queries go in one request, joined with OR.

    arXiv asks clients to send no more than one request every three seconds,
    so the queries are combined rather than sent one by one.
    """

    key = "arxiv"

    def __init__(self, per_query: int = 5):
        self.per_query = per_query

    def url(self, queries: list[str]) -> str:
        expression = " OR ".join(f"({arxiv_query(q)})" for q in queries)
        params = {
            "search_query": expression,
            "start": 0,
            "max_results": min(self.per_query * len(queries), 30),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        return f"{ARXIV_API}?{urllib.parse.urlencode(params)}"

    async def search(self, client, queries: list[str]) -> SourceRun:
        run = SourceRun(self.key)
        try:
            response = await client.get(self.url(queries), headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            run.ranked.append(parse_arxiv(response.text))
        except Exception as exc:
            run.status, run.detail = _describe_failure(exc)
        return run


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------
def _openalex_abstract(inverted: dict | None) -> str:
    """Rebuild an abstract from OpenAlex's word → positions index."""
    if not isinstance(inverted, dict):
        return ""
    positions: dict[int, str] = {}
    for word, places in inverted.items():
        for place in places or []:
            if isinstance(place, int):
                positions[place] = word
    return " ".join(positions[i] for i in sorted(positions))


def parse_openalex(payload: dict) -> list[dict]:
    """Paper records from an OpenAlex ``/works`` response."""
    papers: list[dict] = []
    for work in (payload or {}).get("results", []) or []:
        if not isinstance(work, dict):
            continue
        work_id = str(work.get("id", "")).rsplit("/", 1)[-1]
        title = work.get("display_name") or work.get("title") or ""
        if not work_id or not title:
            continue

        location = work.get("primary_location") or {}
        landing = str(location.get("landing_page_url") or "")
        doi = normalise_doi(work.get("doi"))
        arxiv_id = ""
        if doi.startswith("10.48550/arxiv."):
            arxiv_id = bare_arxiv_id(doi)
        elif "arxiv.org/abs/" in landing:
            arxiv_id = bare_arxiv_id(landing)

        papers.append(
            new_paper(
                "openalex",
                work_id,
                title=title,
                authors=[
                    (a.get("author") or {}).get("display_name", "")
                    for a in work.get("authorships") or []
                    if isinstance(a, dict)
                ],
                abstract=_openalex_abstract(work.get("abstract_inverted_index")),
                published=str(work.get("publication_date") or ""),
                year=str(work.get("publication_year") or ""),
                url=f"https://doi.org/{doi}" if doi else str(work.get("id", "")),
                pdf_url=str(location.get("pdf_url") or ""),
                doi=doi,
                arxiv_id=arxiv_id,
                venue=((location.get("source") or {}).get("display_name") or ""),
                citation_count=work.get("cited_by_count"),
            )
        )
    return papers


class OpenAlexSource:
    """OpenAlex's ``/works`` search: journals, conferences and preprints.

    Works without a key. Setting ``OPENALEX_MAILTO`` joins OpenAlex's "polite
    pool", which is faster and more reliable.
    """

    key = "openalex"
    FIELDS = (
        "id,doi,display_name,publication_year,publication_date,authorships,"
        "abstract_inverted_index,primary_location,cited_by_count"
    )

    def __init__(self, per_query: int = 5, mailto: str = ""):
        self.per_query = per_query
        self.mailto = mailto

    def url(self, query: str) -> str:
        params = {
            "search": query,
            "per-page": self.per_query,
            # A paper with no abstract gives the agents nothing to work with.
            "filter": "has_abstract:true",
            "select": self.FIELDS,
        }
        if self.mailto:
            params["mailto"] = self.mailto
        return f"{OPENALEX_API}?{urllib.parse.urlencode(params)}"

    async def _one(self, client, query: str) -> list[dict]:
        response = await client.get(self.url(query), headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return parse_openalex(response.json())

    async def search(self, client, queries: list[str]) -> SourceRun:
        run = SourceRun(self.key)
        outcomes = await asyncio.gather(
            *(self._one(client, q) for q in queries), return_exceptions=True
        )
        failures = [o for o in outcomes if isinstance(o, Exception)]
        run.ranked = [o for o in outcomes if not isinstance(o, Exception)]
        if failures and not run.ranked:
            run.status, run.detail = _describe_failure(failures[0])
        elif failures:
            run.detail = f"{len(failures)} of {len(queries)} queries failed."
        return run


# ---------------------------------------------------------------------------
# Semantic Scholar
# ---------------------------------------------------------------------------
def parse_semantic_scholar(payload: dict) -> list[dict]:
    """Paper records from a Semantic Scholar ``/paper/search`` response."""
    papers: list[dict] = []
    for item in (payload or {}).get("data", []) or []:
        if not isinstance(item, dict):
            continue
        paper_id = str(item.get("paperId") or "")
        title = item.get("title") or ""
        if not paper_id or not title:
            continue
        external = item.get("externalIds") or {}
        papers.append(
            new_paper(
                "semantic_scholar",
                paper_id,
                title=title,
                authors=[
                    a.get("name", "") for a in item.get("authors") or [] if isinstance(a, dict)
                ],
                abstract=item.get("abstract") or "",
                published=str(item.get("publicationDate") or ""),
                year=str(item.get("year") or ""),
                url=str(item.get("url") or ""),
                doi=external.get("DOI") or "",
                arxiv_id=bare_arxiv_id(external.get("ArXiv") or ""),
                venue=item.get("venue") or "",
                citation_count=item.get("citationCount"),
            )
        )
    return papers


class SemanticScholarSource:
    """Semantic Scholar's paper search, strong on computer science.

    Without a key it shares a public rate limit and often answers 429; queries
    are therefore sent one at a time and the search stops at the first 429.
    ``SEMANTIC_SCHOLAR_API_KEY`` lifts the limit.
    """

    key = "semantic_scholar"
    FIELDS = "paperId,title,abstract,authors,year,publicationDate,externalIds,url,venue,citationCount"

    def __init__(self, per_query: int = 5, api_key: str = ""):
        self.per_query = per_query
        self.api_key = api_key

    def url(self, query: str) -> str:
        params = {"query": query, "limit": self.per_query, "fields": self.FIELDS}
        return f"{SEMANTIC_SCHOLAR_API}?{urllib.parse.urlencode(params)}"

    async def search(self, client, queries: list[str]) -> SourceRun:
        run = SourceRun(self.key)
        headers = {"User-Agent": USER_AGENT}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        failed = 0
        for query in queries:
            try:
                response = await client.get(self.url(query), headers=headers)
                response.raise_for_status()
                run.ranked.append(parse_semantic_scholar(response.json()))
            except Exception as exc:
                failed += 1
                status, detail = _describe_failure(exc)
                if status == "rate_limited":
                    run.status, run.detail = status, detail
                    break
                run.detail = detail

        if not run.ranked and run.status == "ok" and failed:
            run.status = "failed"
        elif run.ranked and failed and run.status == "ok":
            run.detail = f"{failed} of {len(queries)} queries failed."
        if run.status == "rate_limited" and not self.api_key:
            run.detail += " Set SEMANTIC_SCHOLAR_API_KEY to raise the limit."
        return run


# ---------------------------------------------------------------------------
def build_sources(names: list[str], per_query: int, *, mailto: str = "", s2_key: str = ""):
    """The configured sources, in the order given, unknown names ignored."""
    factories = {
        "arxiv": lambda: ArxivSource(per_query),
        "openalex": lambda: OpenAlexSource(per_query, mailto=mailto),
        "semantic_scholar": lambda: SemanticScholarSource(per_query, api_key=s2_key),
    }
    built = []
    for name in names:
        key = name.strip().lower().replace("-", "_").replace(" ", "_")
        if key in factories and key not in {s.key for s in built}:
            built.append(factories[key]())
    return built


__all__ = [
    "ArxivSource",
    "OpenAlexSource",
    "SemanticScholarSource",
    "SourceRun",
    "arxiv_query",
    "build_sources",
    "parse_arxiv",
    "parse_openalex",
    "parse_semantic_scholar",
]
