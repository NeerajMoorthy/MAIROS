"""Merge ranked results from several sources into one de-duplicated list.

The same paper routinely comes back from all three sources — as an arXiv
preprint, as an OpenAlex work with a journal DOI, and as a Semantic Scholar
record carrying both ids. Showing it three times would inflate the paper count
the coverage report is built on, so records are merged when they share any
identifier: a DOI, an arXiv id, or (failing both) the same title.

Ranking is reciprocal-rank fusion: each ranked list a paper appears in adds
``1 / (K + rank)``. A paper that several sources and queries agree on rises;
no source's own relevance score has to be trusted or rescaled, which matters
because the three services score on unrelated scales.
"""

from __future__ import annotations

from .papers import paper_id_for, title_key

# The usual RRF constant: damps the advantage of a first place in one list.
RRF_K = 60

# Shorter titles ("Introduction", "Deep learning") collide across papers.
MIN_TITLE_KEY = 25


def _keys(paper: dict) -> list[str]:
    keys = []
    if paper.get("doi") and not paper["doi"].startswith("10.48550/arxiv."):
        keys.append(f"doi:{paper['doi']}")
    if paper.get("arxiv_id"):
        keys.append(f"arxiv:{paper['arxiv_id']}")
    title = title_key(paper.get("title"))
    if len(title) >= MIN_TITLE_KEY:
        keys.append(f"title:{title}")
    return keys


def _absorb(target: dict, other: dict) -> None:
    """Fold *other*'s metadata into *target* where it adds something."""
    for name in other.get("sources", []):
        if name not in target["sources"]:
            target["sources"].append(name)
    target["source_ids"] = {**other.get("source_ids", {}), **target.get("source_ids", {})}

    if len(other.get("abstract", "")) > len(target.get("abstract", "")):
        target["abstract"] = other["abstract"]
    if len(other.get("authors", [])) > len(target.get("authors", [])):
        target["authors"] = other["authors"]
    for name in ("arxiv_id", "venue", "primary_category", "pdf_url", "published"):
        if not target.get(name) and other.get(name):
            target[name] = other[name]

    # A journal DOI is more useful to a reader than arXiv's own DOI.
    dois = [d for d in (target.get("doi"), other.get("doi")) if d]
    journal = [d for d in dois if not d.startswith("10.48550/")]
    target["doi"] = (journal or dois or [""])[0]

    # The earliest year is when the work first appeared.
    years = [y for y in (target.get("year"), other.get("year")) if y]
    if years:
        target["year"] = min(years)

    counts = [c for c in (target.get("citation_count"), other.get("citation_count")) if c is not None]
    if counts:
        target["citation_count"] = max(counts)


def _best_link(paper: dict) -> str:
    """A DOI link where there is a published version, else the source page."""
    doi = paper.get("doi", "")
    if doi and not doi.startswith("10.48550/"):
        return f"https://doi.org/{doi}"
    if paper.get("arxiv_id"):
        return f"https://arxiv.org/abs/{paper['arxiv_id']}"
    return paper.get("url", "")


def _relevance(paper: dict, focus: set[str]) -> float:
    """How much of the topic's wording a paper's title and abstract share.

    Title matches count double: a paper titled with the topic's terms is about
    it, while an abstract can mention them in passing.
    """
    from services.agents.evidence import tokens

    title = tokens(paper.get("title", "")) & focus
    abstract = tokens(paper.get("abstract", "")) & focus
    return 2 * len(title) + len(abstract)


def merge_ranked(
    ranked_lists: list[list[dict]], focus: str | None = None
) -> tuple[list[dict], int]:
    """Fuse ranked lists into one list, best first.

    Args:
        focus: The topic searched for. When given, the fused rank is blended
            half and half with each paper's wording overlap with it. Rank
            fusion alone rewards agreement between lists, and a broad query
            ("low-cost robot") agrees with itself across sources about papers
            that are not on the topic at all — a live search ranked a robot
            learning benchmark above "Railway Track Crack Detection Vehicle".

    Returns:
        The merged papers, ranked, and how many duplicate records were folded
        into another one.
    """
    # Every record with its rank, in the order the lists arrived.
    entries = [
        (rank, paper) for papers in ranked_lists for rank, paper in enumerate(papers, start=1)
    ]

    # Records sharing any identifier are one paper, and so are records joined
    # only through a third: an arXiv preprint and a published version with a
    # different title are one paper once a record carrying both the arXiv id
    # and the DOI turns up. Attaching each record to the first match left
    # those two separate (union-find joins them).
    parent = list(range(len(entries)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[str, int] = {}
    for index, (_rank, paper) in enumerate(entries):
        for key in _keys(paper):
            if key in owner:
                parent[find(index)] = find(owner[key])
            else:
                owner[key] = index

    groups: dict[int, list[int]] = {}
    for index in range(len(entries)):
        groups.setdefault(find(index), []).append(index)

    merged: list[dict] = []
    scores: list[float] = []
    for members in sorted(groups.values(), key=lambda m: m[0]):
        first = entries[members[0]][1]
        record = dict(first)
        record["sources"] = list(first.get("sources", []))
        record["source_ids"] = dict(first.get("source_ids", {}))
        for index in members[1:]:
            _absorb(record, entries[index][1])
        merged.append(record)
        scores.append(sum(1.0 / (RRF_K + entries[index][0]) for index in members))
    duplicates = len(entries) - len(merged)

    for record in merged:
        record["url"] = _best_link(record)
        record["source"] = record["sources"][0] if record["sources"] else record.get("source", "")
        record["id"] = paper_id_for(record)

    if focus and merged:
        from services.agents.evidence import tokens

        focus_tokens = tokens(focus)
        relevance = [_relevance(record, focus_tokens) for record in merged]
        top_score, top_relevance = max(scores) or 1.0, max(relevance) or 1
        scores = [
            0.5 * score / top_score + 0.5 * rel / top_relevance
            for score, rel in zip(scores, relevance)
        ]

    order = sorted(
        range(len(merged)),
        key=lambda i: (-scores[i], -(merged[i].get("citation_count") or 0), i),
    )
    return [merged[i] for i in order], duplicates


__all__ = ["merge_ranked", "RRF_K"]
