"""Multi-source literature search: arXiv, OpenAlex and Semantic Scholar.

* ``papers``   — the one paper record every source is normalised into, and the
  link allowlist
* ``sources``  — one client per service; failures are reported, never raised
* ``merge``    — de-duplication across sources and reciprocal-rank fusion
* ``queries``  — model-written search queries with a rule-based fallback
* ``coverage`` — the report of what a search did and did not look at
"""

from .coverage import build_coverage, describe_scope
from .merge import merge_ranked
from .papers import (
    FETCHED_PREFIXES,
    SOURCE_NAMES,
    document_aliases,
    document_id_for,
    paper_aliases,
    paper_id_for,
    safe_link,
    source_name_for_document,
)
from .queries import plan_queries, rule_queries
from .sources import SourceRun, build_sources

__all__ = [
    "FETCHED_PREFIXES",
    "SOURCE_NAMES",
    "SourceRun",
    "build_coverage",
    "build_sources",
    "describe_scope",
    "document_aliases",
    "document_id_for",
    "merge_ranked",
    "paper_aliases",
    "paper_id_for",
    "plan_queries",
    "rule_queries",
    "safe_link",
    "source_name_for_document",
]
