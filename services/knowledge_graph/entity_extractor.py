"""LLM-based entity and relation extraction from text."""

from __future__ import annotations

from dataclasses import dataclass, field

from services.common.json_utils import as_text, extract_json
from services.common.text import normalize_name
from services.generation.provider import TASK_EXTRACTION

from .concepts import co_occurring, concept_phrases

ALLOWED_TYPES = {
    "Concept",
    "Method",
    "Person",
    "Dataset",
    "Metric",
    "Paper",
    "Task",
    # Reserved for a future patent-analysis flow — no agent produces this yet,
    # but the graph store, extractor, and UI legend all already understand it.
    "Patent",
}
ALLOWED_RELATIONS = {
    "USES",
    "EXTENDS",
    "COMPARES_TO",
    "PART_OF",
    "AUTHORED_BY",
    "EVALUATED_ON",
    "IMPROVES",
    "RELATED_TO",
}


@dataclass
class ExtractedEntity:
    name: str
    type: str = "Concept"
    description: str = ""


@dataclass
class ExtractedRelation:
    subject: str
    relation: str
    object: str
    confidence: float = 1.0


@dataclass
class ExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)
    # Why nothing was extracted, when that is not simply "the text had none":
    # the caller reports it instead of logging a silent "+0 nodes".
    problem: str = ""


EXTRACTION_PROMPT = (
    TASK_EXTRACTION + "\n"
    "Extract the key scientific entities and the relations between them from the "
    "text below.\n\n"
    "Return ONLY a JSON object, no prose:\n"
    '{{"entities": [{{"name": "...", "type": "Concept|Method|Person|Dataset|Metric|Task", '
    '"description": "one short clause"}}],\n'
    ' "relations": [{{"subject": "...", "relation": '
    '"USES|EXTENDS|COMPARES_TO|PART_OF|AUTHORED_BY|EVALUATED_ON|IMPROVES|RELATED_TO", '
    # (A stray `"` used to follow the closing braces here, so every model saw
    # a dangling quote straight after the schema it was asked to match.)
    '"object": "...", "confidence": 0.0-1.0}}]}}\n\n'
    "Rules: at most 12 entities and 12 relations. Use the exact surface form from "
    "the text as the name. Every relation's subject and object MUST also appear in "
    "the entities array. Skip generic words like 'method' or 'result'. Write "
    "compact JSON on one line, without indentation.\n\n"
    "Text:\n{text}\n"
)


def _salvage_entities(raw: str) -> dict | None:
    """The complete ``entities`` array from a reply that was cut off later.

    The schema puts entities before relations, so a reply truncated by the
    token cap usually still holds a whole entity list. Keeping it is strictly
    better than discarding a run's extraction because its tail went missing.
    """
    from services.common.json_utils import _balanced_slice

    key = raw.find('"entities"')
    if key == -1:
        return None
    span = _balanced_slice(raw[key:], "[", "]")
    entities = extract_json(span, default=None) if span else None
    return {"entities": entities, "relations": []} if isinstance(entities, list) else None


class EntityRelationExtractor:
    """Extract entities and relations using an LLM, with strict validation.

    Args:
        llm: Either a LangChain chat model or a plain ``str -> str`` callable.
        max_tokens: Output budget for this call only, overriding the model's
            default. Extraction needs more than other prompts: see
            ``llm_extraction_max_tokens`` in ``app/config.py`` for the live
            run that showed why.
    """

    def __init__(self, llm=None, max_tokens: int | None = None):
        self.llm = llm
        self.max_tokens = max_tokens

    def _invoke(self, prompt: str) -> tuple[str, bool]:
        """The reply text, and whether the model stopped at its token cap."""
        if self.llm is None:
            return "", False
        if hasattr(self.llm, "invoke"):
            model = self.llm
            if self.max_tokens and hasattr(model, "bind"):
                # Per-call kwargs reach the provider request and override the
                # model's own max_tokens; nothing else that shares this model
                # is affected.
                model = model.bind(max_tokens=self.max_tokens)
            response = model.invoke(prompt)
            metadata = getattr(response, "response_metadata", None) or {}
            return as_text(response), metadata.get("finish_reason") == "length"
        return as_text(self.llm(prompt)), False

    def extract(self, text: str, max_chars: int = 6000, fallback_text: str = "") -> ExtractionResult:
        """Extract entities and relations from *text*.

        When the model is missing, fails, or returns nothing usable, the
        concepts *fallback_text* (or *text*) repeats are used instead — see
        :mod:`services.knowledge_graph.concepts` — and ``problem`` says so.
        """
        text = (text or "").strip()
        if not text:
            return ExtractionResult()
        if self.llm is None:
            return self._from_key_concepts(fallback_text or text, "no model is configured")

        try:
            raw, truncated = self._invoke(EXTRACTION_PROMPT.format(text=text[:max_chars]))
        except Exception as exc:  # e.g. a 429 from the provider's per-minute limit
            return self._from_key_concepts(
                fallback_text or text, f"the model call failed ({type(exc).__name__}: {str(exc)[:160]})"
            )
        budget = (
            "the model reached its output token limit before finishing "
            "(LLM_EXTRACTION_MAX_TOKENS; a reasoning model spends part of it thinking)"
        )
        if not raw.strip():
            return self._from_key_concepts(
                fallback_text or text, budget if truncated else "the model returned an empty response"
            )

        data = extract_json(raw, default=None)
        problem = ""
        if not isinstance(data, dict):
            data = _salvage_entities(raw)
            if data is None:
                return self._from_key_concepts(
                    fallback_text or text,
                    budget if truncated else "the model's response contained no parseable JSON object",
                )
            problem = (budget if truncated else "the response was cut off") + "; the complete entity list was kept and the relations were lost"

        entities: list[ExtractedEntity] = []
        names: set[str] = set()
        for item in data.get("entities", [])[:12]:
            if not isinstance(item, dict):
                continue
            # Normalised here as well as in the graph store, so the duplicate
            # checks below compare names the way the graph will store them.
            name = normalize_name(item.get("name", ""))
            if not name or len(name) > 120:
                continue
            etype = str(item.get("type", "Concept")).strip()
            if etype not in ALLOWED_TYPES:
                etype = "Concept"
            entities.append(
                ExtractedEntity(
                    name=name,
                    type=etype,
                    description=str(item.get("description", ""))[:240],
                )
            )
            names.add(name.lower())

        relations: list[ExtractedRelation] = []
        for item in data.get("relations", [])[:12]:
            if not isinstance(item, dict):
                continue
            subj = normalize_name(item.get("subject", ""))
            obj = normalize_name(item.get("object", ""))
            if not subj or not obj or subj == obj:
                continue

            rel = str(item.get("relation", "RELATED_TO")).strip().upper().replace(" ", "_")
            if rel not in ALLOWED_RELATIONS:
                rel = "RELATED_TO"

            # Keep the graph connected: promote unseen endpoints to entities.
            for endpoint in (subj, obj):
                if endpoint.lower() not in names:
                    entities.append(ExtractedEntity(name=endpoint, type="Concept"))
                    names.add(endpoint.lower())

            try:
                confidence = float(item.get("confidence", 1.0))
            except (TypeError, ValueError):
                confidence = 1.0

            relations.append(
                ExtractedRelation(
                    subject=subj,
                    relation=rel,
                    object=obj,
                    confidence=max(0.0, min(1.0, confidence)),
                )
            )

        if not entities:
            return self._from_key_concepts(fallback_text or text, "the model named no entities")
        return ExtractionResult(entities=entities, relations=relations, problem=problem)

    @staticmethod
    def _from_key_concepts(text: str, why: str) -> ExtractionResult:
        """Concepts the text repeats, linked when they share a sentence.

        Without this, a model failure — such as a rate limit during a run —
        left the paper with no concepts in the graph, and patent awareness,
        which matches patents against those concepts, with almost nothing.
        """
        names = concept_phrases(text)
        if not names:
            return ExtractionResult(problem=why)
        return ExtractionResult(
            entities=[ExtractedEntity(name=name, type="Concept") for name in names],
            relations=[
                ExtractedRelation(subject=a, relation="RELATED_TO", object=b, confidence=0.5)
                for a, b in co_occurring(names, text)
            ],
            problem=f"{why}; key concepts were taken from the text instead",
        )
