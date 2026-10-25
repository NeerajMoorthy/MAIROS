"""Recorded-shape responses from arXiv, OpenAlex and Semantic Scholar.

The shapes follow each API's real response format (fields trimmed to what
MAIROS requests). The same paper — Lewis et al.'s retrieval-augmented
generation paper — comes back from all three sources under different ids, as
it does in practice, so merging can be tested against a realistic overlap.
"""

from __future__ import annotations

import httpx

from test_literature import ARXIV_XML

OPENALEX_WORKS = {
    "meta": {"count": 2},
    "results": [
        {
            "id": "https://openalex.org/W3027879771",
            "doi": "https://doi.org/10.5555/3495724.3496517",
            "display_name": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "publication_year": 2020,
            "publication_date": "2020-05-22",
            "authorships": [
                {"author": {"display_name": "Patrick Lewis"}},
                {"author": {"display_name": "Ethan Perez"}},
                {"author": {"display_name": "Aleksandra Piktus"}},
            ],
            "abstract_inverted_index": {
                "Large": [0],
                "pre-trained": [1],
                "language": [2],
                "models": [3],
                "store": [4],
                "factual": [5],
                "knowledge.": [6],
            },
            "primary_location": {
                "landing_page_url": "https://arxiv.org/abs/2005.11401",
                "pdf_url": "https://some-publisher.example/rag.pdf",
                "source": {"display_name": "Neural Information Processing Systems"},
            },
            "cited_by_count": 4100,
        },
        {
            "id": "https://openalex.org/W3099700870",
            "doi": "https://doi.org/10.18653/v1/2020.emnlp-main.550",
            "display_name": "Dense Passage Retrieval for Open-Domain Question Answering",
            "publication_year": 2020,
            "publication_date": "2020-01-01",
            "authorships": [{"author": {"display_name": "Vladimir Karpukhin"}}],
            "abstract_inverted_index": {"Open-domain": [0], "question": [1], "answering": [2]},
            "primary_location": {
                "landing_page_url": "https://aclanthology.org/2020.emnlp-main.550",
                "source": {"display_name": "Empirical Methods in Natural Language Processing"},
            },
            "cited_by_count": 3200,
        },
    ],
}

SEMANTIC_SCHOLAR_SEARCH = {
    "total": 3,
    "data": [
        {
            "paperId": "659bf9ce7175e1ec266ff54359e2bd76e0b7ff31",
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "abstract": "Large pre-trained language models have been shown to store factual knowledge in their parameters.",
            "authors": [{"name": "Patrick Lewis"}, {"name": "Ethan Perez"}],
            "year": 2020,
            "publicationDate": "2020-05-22",
            "externalIds": {"ArXiv": "2005.11401", "DBLP": "conf/nips/LewisPPPKGKLYR020"},
            "url": "https://www.semanticscholar.org/paper/659bf9ce7175e1ec266ff54359e2bd76e0b7ff31",
            "venue": "Neural Information Processing Systems",
            "citationCount": 4300,
        },
        {
            "paperId": "79cd9f77e5258f62c0e15d11534aea6393ef73fe",
            "title": "Dense Passage Retrieval for Open-Domain Question Answering",
            "abstract": "Open-domain question answering relies on efficient passage retrieval.",
            "authors": [{"name": "Vladimir Karpukhin"}],
            "year": 2020,
            "publicationDate": "2020-04-10",
            "externalIds": {"DOI": "10.18653/v1/2020.emnlp-main.550", "ArXiv": "2004.04906"},
            "url": "https://www.semanticscholar.org/paper/79cd9f77e5258f62c0e15d11534aea6393ef73fe",
            "venue": "Conference on Empirical Methods in Natural Language Processing",
            "citationCount": 3300,
        },
        {
            "paperId": "832fff14d2ed50eb7969c4c4b976c35776548f56",
            "title": "REALM: Retrieval-Augmented Language Model Pre-Training",
            "abstract": "Language model pre-training captures a surprising amount of world knowledge.",
            "authors": [{"name": "Kelvin Guu"}],
            "year": 2020,
            "publicationDate": "2020-02-10",
            "externalIds": {"ArXiv": "2002.08909"},
            "url": "https://www.semanticscholar.org/paper/832fff14d2ed50eb7969c4c4b976c35776548f56",
            "venue": "International Conference on Machine Learning",
            "citationCount": 1900,
        },
    ],
}


class _Response:
    def __init__(self, url: str, status: int = 200, text: str = "", payload=None):
        self.url = url
        self.status_code = status
        self.text = text
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", self.url)
            raise httpx.HTTPStatusError(
                str(self.status_code),
                request=request,
                response=httpx.Response(self.status_code, request=request),
            )


class RecordedClient:
    """Stands in for ``httpx.AsyncClient``, answering each source by host.

    ``status`` overrides the answer for a source key (``"semantic_scholar":
    429``); every URL requested is kept in ``requests``.
    """

    status: dict[str, int] = {}
    requests: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        RecordedClient.requests.append(url)
        if "arxiv.org" in url:
            key, body = "arxiv", {"text": ARXIV_XML}
        elif "openalex.org" in url:
            key, body = "openalex", {"payload": OPENALEX_WORKS}
        elif "semanticscholar.org" in url:
            key, body = "semantic_scholar", {"payload": SEMANTIC_SCHOLAR_SEARCH}
        else:  # pragma: no cover - a source the tests do not know
            raise httpx.ConnectError(f"unexpected host in {url}")
        status = RecordedClient.status.get(key, 200)
        if status >= 400:
            return _Response(url, status)
        return _Response(url, **body)


def use_recorded_sources(monkeypatch, **status: int) -> type[RecordedClient]:
    """Patch every source to answer from the recordings above."""
    RecordedClient.status = dict(status)
    RecordedClient.requests = []
    monkeypatch.setattr(httpx, "AsyncClient", RecordedClient)
    return RecordedClient
