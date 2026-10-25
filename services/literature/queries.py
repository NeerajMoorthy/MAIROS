"""Search queries for the literature sources.

A single keyword query misses most of a topic: papers name the same idea in
different words ("retrieval-augmented generation", "open-domain QA with a
retriever", "RAG"). So a search runs several queries.

The live model is asked for them first, because it knows a field's synonyms
and method names. Its reply is only *search input* — it never reaches the user
as a finding — but it is still validated: anything that is not a short plain
phrase is dropped. When there is no live model, or its reply is unusable, the
queries come from rules over the text itself, and the coverage report says
which of the two wrote them.
"""

from __future__ import annotations

import re

from services.common.json_utils import extract_json
from services.common.text import normalize_name
from services.generation.provider import TASK_QUERIES

QUERY_PROMPT = (
    TASK_QUERIES + "\n"
    "Write {count} different search queries for finding academic papers relevant "
    "to the text below. Each query is 2-8 words of technical terms: the topic "
    "itself, its synonyms, the named methods, and the problem it addresses. No "
    "quotation marks, boolean operators, years or author names.\n\n"
    'Return ONLY compact JSON on one line: {{"queries": ["...", "..."]}}\n\n'
    "Text:\n{text}\n"
)

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "can", "do", "does",
    "for", "from", "give", "has", "have", "how", "i", "in", "into", "is", "it",
    "its", "latest", "me", "my", "of", "on", "or", "our", "out", "paper", "papers",
    "project", "recent", "review", "search", "show", "so", "such", "survey",
    "than", "that", "the", "their", "them", "then", "there", "these", "this",
    "those", "to", "using", "use", "used", "was", "we", "were", "what", "which",
    "will", "with", "would", "why", "find", "about", "literature", "work",
    "also", "based", "new", "propose", "proposed", "aim", "aims", "goal",
    "system", "approach", "study", "student", "students",
}

MAX_QUERY_WORDS = 8
MAX_QUERY_CHARS = 100


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9\-]*[a-z0-9]|[a-z0-9]", normalize_name(text).lower())


def _content(words: list[str]) -> list[str]:
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


# Words that end a key phrase. Wider than _STOPWORDS: everyday verbs and
# adjectives ("uses", "slow", "struggle") separate the technical terms in a
# description rather than belong to them.
_PHRASE_BREAKS = _STOPWORDS | {
    "after", "all", "any", "because", "before", "being", "between", "both",
    "but", "cheaper", "could", "each", "easier", "else", "every", "faster",
    "help", "helps", "here", "if", "just", "long", "make", "makes", "many",
    "more", "most", "much", "must", "no", "not", "only", "other", "over",
    "same", "should", "slow", "some", "spend", "struggle", "time", "under",
    "uses", "very", "way", "well", "when", "where", "while", "who", "write",
    "written", "able", "allow", "allows", "answer", "answers", "find", "finds",
    "need", "needs", "reduce", "reduces", "send", "sends", "try", "evaluate",
    "existing", "current", "currently", "first", "one", "two", "three",
    "detects", "help", "people", "user", "users",
}
MAX_PHRASE_WORDS = 4


def key_phrases(text: str) -> list[str]:
    """Key phrases of *text*, best first (RAKE, Rose et al. 2010).

    Candidates are the runs of words between punctuation and break words.
    Each word scores its degree over its frequency — how much longer phrase
    it tends to sit in — and a phrase scores the sum of its words. Repeated,
    multi-word technical terms ("railway track crack detection") rise; the
    connective prose around them never forms a candidate.
    """
    candidates: list[list[str]] = []
    for clause in re.split(r"[.,;:!?()\[\]\"\n]+", normalize_name(text).lower()):
        run: list[str] = []
        for word in _words(clause):
            if word in _PHRASE_BREAKS or len(word) < 2 or word.isdigit():
                if run:
                    candidates.append(run[:MAX_PHRASE_WORDS])
                run = []
            else:
                run.append(word)
        if run:
            candidates.append(run[:MAX_PHRASE_WORDS])

    frequency: dict[str, int] = {}
    degree: dict[str, int] = {}
    for phrase in candidates:
        for word in phrase:
            frequency[word] = frequency.get(word, 0) + 1
            degree[word] = degree.get(word, 0) + len(phrase)

    scores: dict[str, float] = {}
    for phrase in candidates:
        key = " ".join(phrase)
        score = sum(degree[w] / frequency[w] for w in phrase)
        scores[key] = max(scores.get(key, 0.0), score) + (0.5 if key in scores else 0.0)
    return sorted(scores, key=lambda p: -scores[p])


def rule_queries(text: str, limit: int = 4) -> list[str]:
    """Queries built from the text alone.

    A short topic ("graph neural networks") is one query; splitting it into
    phrases would only search for fragments of it. A longer description gives
    its best multi-word key phrases, skipping any already contained in one
    chosen before.
    """
    content = _content(_words(text))
    if not content:
        return []
    if len(content) <= 8 or limit <= 1:
        return [" ".join(content[:6])]

    queries: list[str] = []
    for phrase in key_phrases(text):
        if len(queries) >= limit:
            break
        if len(phrase.split()) < 2:
            continue
        if any(set(phrase.split()) <= set(q.split()) for q in queries):
            continue
        queries.append(phrase)
    return queries or [" ".join(content[:6])]


def clean_query(value: object, min_words: int = 2) -> str:
    """A short plain phrase, or ``""`` if *value* is not usable as one."""
    text = normalize_name(str(value or ""))
    text = re.sub(r"[^\w\s\-]", " ", text)
    text = re.sub(r"\b(AND|OR|NOT)\b", " ", text)
    text = " ".join(text.split())
    if not min_words <= len(text.split()) <= MAX_QUERY_WORDS or len(text) > MAX_QUERY_CHARS:
        return ""
    return text


def parse_model_queries(raw: str, limit: int) -> list[str]:
    """Validated queries from the model's reply, best first, no repeats."""
    data = extract_json(raw or "", default=None)
    items = data.get("queries") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []

    queries: list[str] = []
    seen: set[str] = set()
    for item in items:
        query = clean_query(item)
        if query and query.lower() not in seen:
            seen.add(query.lower())
            queries.append(query)
        if len(queries) >= limit:
            break
    return queries


def plan_queries(
    text: str, limit: int, invoke=None, seeds: list[dict] | None = None
) -> tuple[list[dict], str]:
    """The queries a search will run, each tagged with who wrote it.

    Args:
        text: The topic or project description to search for.
        limit: How many queries to run at most.
        invoke: ``prompt -> reply`` for the live model, or ``None`` offline.
        seeds: Queries already chosen (a project brief's keywords), as
            ``{"text", "written_by"}``; they replace the rule-based core.

    Returns:
        ``[{"text": ..., "written_by": "rules" | "model"}]`` and, when the
        model was asked but not used, the reason why (else ``""``).
    """
    rules = rule_queries(text, limit)
    planned: list[dict] = []
    for seed in seeds or []:
        query = clean_query(seed.get("text"), min_words=1)
        if query and query.lower() not in {p["text"].lower() for p in planned}:
            planned.append({"text": query, "written_by": seed.get("written_by", "rules")})
    # Seeds take half the budget at most, so the model still adds its own.
    planned = planned[: max(1, limit // 2)] or [{"text": q, "written_by": "rules"} for q in rules[:1]]
    note = ""

    if invoke is not None and limit > 1:
        try:
            reply = invoke(QUERY_PROMPT.format(count=limit - 1, text=text[:3000]))
            model = parse_model_queries(reply, limit - 1)
        except Exception as exc:  # the search must still run
            model, note = [], f"The model could not write queries ({type(exc).__name__})."
        if not model and not note:
            note = "The model's queries were unusable, so rule-based queries were used."
        seen = {p["text"].lower() for p in planned}
        for query in model:
            if query.lower() not in seen:
                seen.add(query.lower())
                planned.append({"text": query, "written_by": "model"})

    if len(planned) < limit:
        seen = {p["text"].lower() for p in planned}
        for query in rules:
            if len(planned) >= limit:
                break
            if query.lower() not in seen:
                seen.add(query.lower())
                planned.append({"text": query, "written_by": "rules"})

    return planned[:limit], note


__all__ = ["QUERY_PROMPT", "clean_query", "parse_model_queries", "plan_queries", "rule_queries"]
