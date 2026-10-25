"""Golden test set: curated questions plus the rule that decides relevance.

The relevance rule lives here, next to the cases it applies to, because it is
the part a reviewer is most likely to challenge. MAIROS does not ship
chunk-level human relevance labels — the corpus differs per project — so a
case declares what a passage must *say* to answer it, and a chunk is relevant
when it says all of it. That is a documented keyword proxy for a human
judgment, not a pretence of one: the Evaluation dashboard names the policy
in the UI, and a case whose terms appear nowhere in a project is reported as
unsupported rather than silently scored zero.

When explicit labels *are* available (``source_documents``), they win: the
proxy is only used for cases that declare no document labels.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Shipped with the package — services/evaluation/golden_set.json
DEFAULT_GOLDEN_SET = Path(__file__).resolve().parent / "golden_set.json"


def normalise(text: str) -> str:
    """Lowercase and collapse punctuation to spaces.

    ``Self-Attention``, ``self attention`` and ``SELF  ATTENTION`` all
    normalise to the same string, so a hyphenation choice in a PDF never
    decides whether a passage counts as relevant.
    """
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


@dataclass
class TestCase:
    """A single evaluation test case."""

    id: str
    question: str
    expected_answer: str = ""
    source_documents: list[str] = field(default_factory=list)
    required_entities: list[str] = field(default_factory=list)
    difficulty: str = "single-hop"  # single-hop | multi-hop | comparison | temporal
    tags: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    def is_relevant(self, chunk: dict) -> bool:
        """Does this retrieved chunk answer the case?

        Args:
            chunk: A retrieval result carrying at least ``text`` and,
                optionally, ``document_name``.

        Returns:
            True when the chunk's document is an explicitly labelled source,
            or — absent labels — when its text contains every required term.
        """
        if self.source_documents:
            name = normalise(chunk.get("document_name", ""))
            return any(normalise(doc) in name for doc in self.source_documents if doc)

        if not self.required_entities:
            return False

        text = normalise(chunk.get("text", ""))
        return all(normalise(term) in text for term in self.required_entities if term)

    @property
    def policy(self) -> str:
        """Which relevance rule this case uses — surfaced in the report."""
        return "document_label" if self.source_documents else "term_match"


class GoldenSet:
    """Load and iterate curated test cases.

    Args:
        path: JSON file to load. Defaults to the curated set shipped with
            MAIROS (``services/evaluation/golden_set.json``).
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_GOLDEN_SET
        self.cases: list[TestCase] = []
        self.metadata: dict = {}

        if self.path.exists():
            self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        with open(self.path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        raw_cases = data.get("test_cases", data) if isinstance(data, dict) else data
        self.cases = [TestCase(**case) for case in raw_cases]

        if isinstance(data, dict):
            self.metadata = {
                key: value for key, value in data.items() if key != "test_cases"
            }

    # ------------------------------------------------------------------
    def filter_by_difficulty(self, difficulty: str) -> list[TestCase]:
        """Return test cases matching the given difficulty."""
        return [case for case in self.cases if case.difficulty == difficulty]

    def filter_by_tag(self, tag: str) -> list[TestCase]:
        """Return test cases carrying the given tag."""
        return [case for case in self.cases if tag in case.tags]

    def get(self, case_id: str) -> TestCase | None:
        return next((case for case in self.cases if case.id == case_id), None)

    def __len__(self) -> int:
        return len(self.cases)

    def __iter__(self):
        return iter(self.cases)
