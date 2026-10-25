"""Evidence linking — shared by the comparison, gap, hypothesis and patent agents.

The rule these agents follow is that a claim without a locatable source is not
shipped. That needs two things: a stable way to label the sources handed to a
model, and a deterministic way to attach the passage that best supports a
returned statement. Both live here so every agent links evidence the same way
and a reviewer only has to check the logic once.

Nothing here calls an LLM — it is string matching over passages the retriever
already returned, so a claim can always be traced back to text in the corpus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "which", "have", "has", "been", "into", "than", "then", "they", "their",
    "these", "those", "such", "also", "using", "used", "based", "its", "it",
    "a", "an", "of", "to", "in", "on", "by", "as", "is", "be", "or", "at",
}


def _content_words(text: str) -> list[str]:
    """Content words in order, lowercased and stripped of punctuation."""
    words = re.findall(r"[a-z0-9]+", str(text).lower())
    return [word for word in words if len(word) > 2 and word not in _STOPWORDS]


def tokens(text: str) -> set[str]:
    """Distinct content words of *text* — for overlap tests, not for ranking."""
    return set(_content_words(text))


def token_counts(text: str) -> dict[str, int]:
    """How often each content word occurs in *text*.

    Separate from :func:`tokens` because that one deduplicates: anything
    ranking terms by frequency must count occurrences, or every term in a
    passage ties at one and the ordering silently collapses to alphabetical.
    """
    counts: dict[str, int] = {}
    for word in _content_words(text):
        counts[word] = counts.get(word, 0) + 1
    return counts


@dataclass
class Source:
    """One document handed to a model, under a stable key like ``S1``."""

    key: str
    document_id: str
    document_name: str
    chunks: list[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(chunk.get("text", "") for chunk in self.chunks)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "chunk_count": len(self.chunks),
        }


def group_sources(chunks: list[dict], limit: int = 6) -> list[Source]:
    """Group retrieved chunks by document, newest key order preserved.

    Args:
        chunks: Retrieval results carrying ``document_name``/``document_id``.
        limit: Maximum number of distinct documents to compare.
    """
    grouped: dict[str, Source] = {}
    for chunk in chunks:
        name = chunk.get("document_name") or "Untitled document"
        source = grouped.get(name)
        if source is None:
            if len(grouped) >= limit:
                continue
            source = Source(
                key=f"S{len(grouped) + 1}",
                document_id=str(chunk.get("document_id", "")),
                document_name=name,
            )
            grouped[name] = source
        source.chunks.append(chunk)
    return list(grouped.values())


def render_sources(sources: list[Source], per_source_chars: int = 2200) -> str:
    """Format sources as ``--- S1 | Name ---`` blocks for a prompt."""
    return "\n\n".join(
        f"--- {source.key} | {source.document_name} ---\n{source.text[:per_source_chars]}"
        for source in sources
    )


def best_supporting_chunk(claim: str, chunks: list[dict]) -> dict | None:
    """The chunk whose wording best supports *claim*.

    Scored by content-word overlap. Returns ``None`` when nothing overlaps at
    all, which is the signal for a caller to drop the claim rather than cite a
    passage that does not mention it.
    """
    claim_tokens = tokens(claim)
    if not claim_tokens:
        return None

    best: tuple[float, dict] | None = None
    for chunk in chunks:
        overlap = claim_tokens & tokens(chunk.get("text", ""))
        if not overlap:
            continue
        score = len(overlap) / len(claim_tokens)
        if best is None or score > best[0]:
            best = (score, chunk)

    return best[1] if best else None


def citation_for(claim: str, chunks: list[dict]) -> dict | None:
    """A citation dict for *claim*, or ``None`` when no passage supports it."""
    chunk = best_supporting_chunk(claim, chunks)
    if chunk is None:
        return None
    return {
        "chunk_id": chunk.get("chunk_id", ""),
        "document_id": chunk.get("document_id", ""),
        "document_name": chunk.get("document_name", ""),
        "page": chunk.get("page"),
        "quote": " ".join(str(chunk.get("text", "")).split())[:320],
    }


# ---------------------------------------------------------------------------
# Question framing
# ---------------------------------------------------------------------------
# Novelty framing, removed a phrase at a time rather than as one span. An
# earlier version matched "is my ... novel" as a single group, which swallowed
# the subject between the two and left nothing but punctuation.
#
# This lives here rather than in either agent because two of them need the same
# answer for different reasons: the Synthesis agent must not hand a novelty
# question to a language model, and the Novelty agent must not score a claim on
# words the user only typed to ask the question.
_FRAMING_PATTERNS = (
    # Leading interrogative framing: "Is my idea of X", "Has anyone done X"
    re.compile(
        r"^\s*(is|are|was|were|has|have|had|does|do|did|can|could|would|should)\s+"
        r"(this|that|these|those|it|my|our|the|anyone|anybody|someone|somebody)\s+"
        r"(idea|work|approach|method|claim|research|project|team)?\s*"
        r"(of|for|about|on|that|to)?\s*",
        flags=re.IGNORECASE,
    ),
    # "already been done", "been done before", "already published"
    re.compile(
        r"\b(already\s+)?(been\s+)?(done|published|explored|known|tried|studied)"
        r"(\s+before)?(\s+(by|in)\s+(anyone|anybody|someone|the\s+field|the\s+literature))?\b",
        flags=re.IGNORECASE,
    ),
    # Bare novelty vocabulary, wherever it appears.
    re.compile(
        r"\b(novel|novelty|original|originality|unique|uniqueness|unprecedented|"
        r"groundbreaking|first\s+of\s+its\s+kind)\b",
        flags=re.IGNORECASE,
    ),
    # Trailing scaffolding left behind once the above are gone.
    re.compile(
        r"\b(or\s+has\s+anyone|has\s+anyone|have\s+others|anything\s+similar\s+to|"
        r"similar\s+to\s+my|whether|or\s+not)\b",
        flags=re.IGNORECASE,
    ),
)

_NOVELTY_VOCABULARY = _FRAMING_PATTERNS[2]

# If a question is nothing but framing there is no subject left. Returning the
# original would defeat the point, so callers get this instead.
NEUTRAL_QUESTION = "the main topics covered by these sources"


def strip_question_framing(question: str, fallback: str = NEUTRAL_QUESTION) -> str:
    """Remove interrogative and novelty framing, keeping the subject matter.

    Used for two things that both go wrong without it. A language model asked
    "is X novel?" over passages that do not mention X will answer that it looks
    novel and cite a passage for it. And scoring a claim's overlap against the
    corpus divides by the claim's own token count, so every word the user typed
    only to ask the question ("idea", "already", "whether", "anyone") is a token
    the corpus can never match and which drags the score down — in the
    false-negative direction, towards "not found in this project's sources",
    which is the one verdict that reads like a novelty signal.

    The postcondition is checked rather than assumed: if novelty vocabulary
    survives a wording the patterns did not anticipate, the fallback is used.
    """
    text = question or ""
    for pattern in _FRAMING_PATTERNS:
        text = pattern.sub(" ", text)

    text = re.sub(r"\s{2,}", " ", text).strip(" ,;:?.!—-")

    if not text or _NOVELTY_VOCABULARY.search(text):
        return fallback
    return text


__all__ = [
    "NEUTRAL_QUESTION",
    "Source",
    "best_supporting_chunk",
    "citation_for",
    "group_sources",
    "render_sources",
    "strip_question_framing",
    "token_counts",
    "tokens",
]
