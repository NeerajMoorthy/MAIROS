"""Project Intake Agent — reads a pasted project description into a brief.

A student's question is often not a topic but a whole project: "We are
building a low-cost robot that detects cracks in railway tracks using a camera
and IR sensors…". Searched as-is, a 2,000-character description makes poor
queries, embeds poorly, and cannot be scored as one claim. This agent turns it
into a structured brief — problem, methods, datasets, goals, stated
contributions, search keywords — that the later agents use:

* the Literature agent searches for the brief's ``search_text``;
* retrieval and comparison look for it instead of the raw description;
* the Novelty agent checks each stated contribution against what was found.

The brief describes *the user's own text*, so it must not say anything that
text does not. Every field except ``keywords`` is kept only if most of its
content words appear in the description; the rest are dropped and counted.
Keywords are exempt because they are search terms — a field's usual synonyms
are exactly what a good search needs — and they are labelled as such.

With no live model the brief is built by rules from the description's own
sentences, and says so.
"""

from __future__ import annotations

import re

from services.common.json_utils import extract_json
from services.common.text import normalize_name
from services.generation.provider import TASK_INTAKE
from services.literature.queries import clean_query, rule_queries

from .base import AgentContext, BaseAgent
from .evidence import tokens

INTAKE_PROMPT = (
    TASK_INTAKE + "\n"
    "Read the project description below and extract what it says, in its own "
    "wording wherever possible:\n"
    "- title: a short name for the project\n"
    "- problem: the problem it addresses, one sentence\n"
    "- domain: the research area\n"
    "- methods: named techniques, models or tools it uses\n"
    "- datasets: named datasets or data sources\n"
    "- goals: what it aims to achieve\n"
    "- contributions: what it claims to add, one sentence each\n"
    "- keywords: 4-8 search terms for finding related papers (standard "
    "synonyms of its terms are allowed here, and only here)\n\n"
    "Do not add anything the description does not say. Leave a list empty "
    "rather than guess.\n\n"
    'Return ONLY compact JSON on one line: {{"title": "", "problem": "", '
    '"domain": "", "methods": [], "datasets": [], "goals": [], '
    '"contributions": [], "keywords": []}}\n\n'
    "Description:\n{description}\n"
)

MAX_DESCRIPTION_CHARS = 6000
# Share of an item's content words that must appear in the description.
GROUNDING_THRESHOLD = 0.6

LIST_LIMITS = {"methods": 6, "datasets": 6, "goals": 4, "contributions": 6}
TEXT_LIMITS = {"title": 120, "problem": 400, "domain": 120}

# A sentence stating what the project builds or adds. Plans ("we will
# evaluate…") and aims ("aims to reduce…") are not contributions: they are
# kept as goals, and checking them for coverage would only report noise.
_CONTRIBUTION = re.compile(
    r"\b(?:we|i)(?: will)? (?:propose|present|develop|build|introduce|design|"
    r"implement|create|contribute)\b|\bthe proposed\b|\bour (?:system|method|model)\b"
)
_GOAL_CUES = ("aim", "goal", "objective", "intend", "in order to", "we will", "i will")
_PROBLEM_CUES = (
    "problem", "challenge", "difficult", "lack", "limited", "issue", "costly",
    "expensive", "manual", "slow", "error-prone",
)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [" ".join(p.split()) for p in parts if len(p.split()) >= 4]


def _grounded(item: str, description_tokens: set[str]) -> bool:
    item_tokens = tokens(item)
    if not item_tokens:
        return False
    return len(item_tokens & description_tokens) / len(item_tokens) >= GROUNDING_THRESHOLD


def _clip(text: str, limit: int) -> str:
    text = normalize_name(text)
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def search_text_for(brief: dict) -> str:
    """A compact query that stands for the whole description.

    The title leads: it is the shortest statement of the topic there is.
    """
    title, problem = brief.get("title") or "", brief.get("problem") or ""
    parts = [title] if title and not problem.startswith(title.rstrip("…")) else []
    parts.append(problem)
    if brief.get("methods"):
        parts.append("using " + ", ".join(brief["methods"][:3]))
    if brief.get("keywords"):
        parts.append(", ".join(brief["keywords"][:4]))
    return _clip(". ".join(p.strip(" .") for p in parts if p.strip()), 300)


class ProjectIntakeAgent(BaseAgent):
    """Turn a pasted project description into a structured, grounded brief."""

    name = "intake"
    stage = "extracting"

    # ------------------------------------------------------------------
    @staticmethod
    def rules_brief(description: str) -> dict:
        """A brief from the description's own sentences, with no model."""
        sentences = _sentences(description)
        lowered = [s.lower() for s in sentences]
        first_line = description.strip().splitlines()[0].strip() if description.strip() else ""

        title = first_line if 0 < len(first_line) <= 120 and "\n" in description.strip() else ""
        problem = next(
            (s for s, low in zip(sentences, lowered) if any(c in low for c in _PROBLEM_CUES)),
            sentences[0] if sentences else "",
        )
        contributions = [s for s, low in zip(sentences, lowered) if _CONTRIBUTION.search(low)]
        goals = [
            s
            for s, low in zip(sentences, lowered)
            if any(c in low for c in _GOAL_CUES) and s not in contributions
        ]
        return {
            "title": _clip(title or (sentences[0] if sentences else ""), TEXT_LIMITS["title"]),
            "problem": _clip(problem, TEXT_LIMITS["problem"]),
            "domain": "",
            "methods": [],
            "datasets": [],
            "goals": [_clip(g, 300) for g in goals[: LIST_LIMITS["goals"]]],
            "contributions": [_clip(c, 300) for c in contributions[: LIST_LIMITS["contributions"]]],
            "keywords": rule_queries(description, 6),
        }

    def model_brief(self, description: str) -> tuple[dict | None, int]:
        """The model's brief, with every ungrounded item removed.

        Returns the brief (``None`` if the reply was unusable) and how many
        items were dropped for saying something the description does not.
        """
        parsed = extract_json(self.invoke_llm(INTAKE_PROMPT.format(description=description)), default=None)
        if not isinstance(parsed, dict):
            return None, 0

        description_tokens = tokens(description)
        dropped = 0
        brief: dict = {}

        for field, limit in TEXT_LIMITS.items():
            value = _clip(str(parsed.get(field) or ""), limit)
            if value and not _grounded(value, description_tokens):
                dropped += 1
                value = ""
            brief[field] = value

        for field, limit in LIST_LIMITS.items():
            kept: list[str] = []
            for item in parsed.get(field) or []:
                value = _clip(str(item or ""), 300)
                if not value:
                    continue
                if _grounded(value, description_tokens):
                    kept.append(value)
                else:
                    dropped += 1
            brief[field] = kept[:limit]

        keywords: list[str] = []
        for item in parsed.get("keywords") or []:
            # A single technical word ("transformers") is a fine search term.
            value = clean_query(item, min_words=1)
            if value and value.lower() not in {k.lower() for k in keywords}:
                keywords.append(value)
        brief["keywords"] = keywords[:8]

        if not (brief["problem"] or brief["title"] or brief["contributions"]):
            return None, dropped
        return brief, dropped

    # ------------------------------------------------------------------
    async def run(self, ctx: AgentContext) -> AgentContext:
        from services.generation.provider import OfflineChatModel

        description = (ctx.question or "").strip()[:MAX_DESCRIPTION_CHARS]
        if not description:
            ctx.log(self.name, "No project description to read", self.stage, "failed")
            return ctx

        brief, dropped, extracted_by, note = None, 0, "rules", ""
        if self.llm is not None and not isinstance(self.llm, OfflineChatModel):
            try:
                brief, dropped = self.model_brief(description)
                extracted_by = "model"
            except Exception as exc:
                note = f"The model could not read the description ({type(exc).__name__})."
            if brief is None:
                extracted_by = "rules"
                note = note or "The model's reading was unusable, so the brief was built by rules."

        if brief is None:
            brief = self.rules_brief(description)

        brief["search_text"] = search_text_for(brief) or _clip(description, 300)
        brief["extracted_by"] = extracted_by
        brief["dropped_ungrounded"] = dropped
        brief["note"] = note
        brief["description_chars"] = len(description)
        ctx.intermediate_results["project_brief"] = brief

        ctx.log(
            self.name,
            f"Read the project description ({extracted_by}): "
            f"{len(brief['contributions'])} stated contribution(s), "
            f"{len(brief['methods'])} method(s), {len(brief['keywords'])} search keyword(s)"
            + (f"; {dropped} item(s) dropped as not in the description" if dropped else ""),
            self.stage,
        )
        ctx.log(self.name, f"Searching for: {brief['search_text']}", self.stage)
        return ctx
