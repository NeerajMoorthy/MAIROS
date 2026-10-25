"""Central LLM provider for every MAIROS agent.

One place decides which chat model the whole system uses, so swapping
providers later never means touching agent code.

Order of preference:

1. **Groq** (``GROQ_API_KEY`` set) — the configured production provider.
2. **Offline deterministic model** — a real ``BaseChatModel`` that returns
   well-formed, schema-correct output derived from the prompt itself.

The offline model exists so a live demo degrades instead of crashing when the
network or the API key is unavailable. It never invents facts: for grounded
answers it quotes the retrieved context verbatim.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import SimpleChatModel
from langchain_core.messages import BaseMessage

# ---------------------------------------------------------------------------
# Task markers
#
# Every agent prompt begins with one of these so the offline model can emit a
# response of the right shape. Real models simply ignore the marker.
# ---------------------------------------------------------------------------
TASK_ROUTE = "[MAIROS-TASK: route]"
TASK_ANALYSIS = "[MAIROS-TASK: analysis]"
TASK_CITATION = "[MAIROS-TASK: citation]"
TASK_EXTRACTION = "[MAIROS-TASK: extraction]"
TASK_SYNTHESIS = "[MAIROS-TASK: synthesis]"
TASK_COMPARISON = "[MAIROS-TASK: comparison]"
TASK_GAPS = "[MAIROS-TASK: gaps]"
TASK_HYPOTHESIS = "[MAIROS-TASK: hypothesis]"
TASK_EXPERIMENT = "[MAIROS-TASK: experiment]"
TASK_PATENT = "[MAIROS-TASK: patent]"
TASK_NOVELTY = "[MAIROS-TASK: novelty]"
TASK_QUERIES = "[MAIROS-TASK: queries]"
TASK_INTAKE = "[MAIROS-TASK: intake]"

# Header lines the Literature agent puts above a fetched abstract.
_METADATA_LINE = re.compile(r"^(Title|Authors|Published|Venue):\s")


class OfflineChatModel(SimpleChatModel):
    """Deterministic stand-in used when no LLM API key is configured.

    Implements the LangChain ``BaseChatModel`` interface so it drops into the
    same chains, streams, and agents as a hosted model.
    """

    model_name: str = "mairos-offline"

    @property
    def _llm_type(self) -> str:
        return "mairos-offline"

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _sentences(text: str, limit: int = 3) -> list[str]:
        parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 30]
        return parts[:limit]

    @staticmethod
    def _sources(prompt: str) -> list[tuple[str, str]]:
        """Return ``(header, body)`` pairs from a formatted RAG context."""
        blocks = re.split(r"--- SOURCE \d+ ", prompt)[1:]
        out: list[tuple[str, str]] = []
        for block in blocks:
            header, _, body = block.partition("---")
            out.append((header.strip(), body.strip()))
        return out

    @staticmethod
    def _keywords(text: str, limit: int = 8) -> list[str]:
        stop = {
            "the", "and", "for", "with", "that", "this", "from", "are", "was",
            "were", "which", "have", "has", "been", "into", "than", "then",
            "they", "their", "these", "those", "such", "also", "using", "used",
            "based", "paper", "text", "json", "return", "extract", "format",
            # Header labels the Literature agent writes above each abstract:
            # without these, "Abstract" and "Authors" became graph concepts.
            "title", "authors", "abstract", "published", "venue",
        }
        words = re.findall(r"\b[A-Za-z][A-Za-z\-]{3,}\b", text)
        seen: dict[str, int] = {}
        for w in words:
            key = w.lower()
            if key in stop:
                continue
            seen[key] = seen.get(key, 0) + 1
        ranked = sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))
        return [w.title() for w, _ in ranked[:limit]]

    # -- responses ------------------------------------------------------
    def _route(self, prompt: str) -> str:
        # Read ONLY the user's request. Matching against the whole prompt would
        # hit the instruction text itself (which names every flow).
        request = prompt.rsplit("User request:", 1)[-1].strip().lower()

        # Mirrors RouterAgent.heuristic, including its ordering: the research
        # flows nest (experiment ⊃ hypothesis ⊃ gaps), so the longest chain is
        # matched first.
        from services.agents.router import looks_like_project_description

        if any(k in request for k in ("analyse this", "analyze this", "this pdf", "uploaded")):
            flow = "analyze"
        elif looks_like_project_description(request):
            flow = "project"
        elif any(
            k in request
            for k in (
                "literature review", "review the literature", "review of the literature",
                "survey the literature", "systematic review", "write a review",
                "state of the field",
            )
        ):
            flow = "review"
        elif any(
            k in request
            for k in (
                "find papers", "find recent papers", "find me papers",
                "search for papers", "search for publications", "papers on",
                "papers about", "publications on", "publications about",
                "literature on", "literature about", "recent work on",
                "survey of", "what has been published",
            )
        ) and not any(
            k in request
            for k in ("compare", "comparison", "versus", " vs ", "difference between", "contrast")
        ):
            # Discovery intent beats a subject-matter keyword, exactly as in
            # RouterAgent.heuristic — the two must not disagree.
            flow = "search"
        elif any(k in request for k in ("patent", "prior art", "intellectual property")):
            flow = "patent"
        elif any(
            k in request
            for k in (
                "novelty", "is this novel", "how novel", "already been done",
                "been done before", "is this new", "already known", "originality",
            )
        ):
            flow = "novelty"
        elif any(
            k in request
            for k in (
                "experiment", "how would we test", "how to test",
                "experimental protocol", "study protocol", "evaluation protocol",
                "ablation study", "ablation studies", "run an ablation",
            )
        ):
            flow = "experiment"
        elif any(k in request for k in ("hypothesis", "hypotheses", "what should we try")):
            flow = "hypothesis"
        elif any(
            k in request
            for k in ("gap", "open problem", "open question", "what is missing", "unanswered")
        ):
            flow = "gaps"
        elif any(
            k in request
            for k in ("compare", "comparison", "versus", " vs ", "difference between", "contrast")
        ):
            flow = "compare"
        elif any(
            k in request
            for k in ("find paper", "search for", "literature", "recent work", "papers on", "arxiv")
        ):
            flow = "search"
        else:
            flow = "answer"

        return (
            '{"flow": "%s", '
            '"reason": "Offline router: keyword heuristic (no LLM key configured)."}' % flow
        )

    def _analysis(self, prompt: str) -> str:
        body = prompt.split("Paper Text:")[-1].strip()
        sents = self._sentences(body, 3)
        contributions = sents[:2] or ["Text was too short to extract distinct contributions."]
        methodology = sents[2] if len(sents) > 2 else "Methodology not stated in the extracted text."
        summary = " ".join(sents) or body[:400]
        import json

        return json.dumps(
            {
                "contributions": contributions,
                "methodology": methodology,
                "summary": summary,
                "offline": True,
            }
        )

    def _citation(self, prompt: str) -> str:
        import json

        try:
            papers = json.loads(prompt.split("Papers:")[-1])
        except ValueError:
            papers = []
        cites = []
        for paper in papers if isinstance(papers, list) else []:
            if not isinstance(paper, dict) or not paper.get("title"):
                continue
            year = str(paper.get("year") or paper.get("published") or "")[:4] or "n.d."
            container = paper.get("venue") or paper.get("source") or "arXiv"
            cite = f"({year}). {paper['title']}. {container}."
            if paper.get("url"):
                cite += f" {paper['url']}"
            cites.append(cite)
        return json.dumps(cites or ["No paper metadata was available to format."])

    def _extraction(self, prompt: str) -> str:
        import json

        body = prompt.split("Text:")[-1]
        terms = self._keywords(body, 6)
        entities = [{"name": t, "type": "Concept", "description": ""} for t in terms]
        relations = [
            {"subject": terms[i], "relation": "RELATED_TO", "object": terms[i + 1], "confidence": 0.5}
            for i in range(len(terms) - 1)
        ]
        return json.dumps({"entities": entities, "relations": relations})

    def _synthesis(self, prompt: str) -> str:
        sources = self._sources(prompt)
        if not sources:
            return (
                "I cannot answer this based on the provided documents — no matching "
                "passages were retrieved."
            )
        lines = [
            "*(Offline mode — no LLM API key configured. The passages below are "
            "quoted verbatim from your indexed documents.)*",
            "",
        ]
        for header, body in sources[:3]:
            snippet = " ".join(body.split())[:320]
            lines.append(f"- {snippet}… {header}")
        return "\n".join(lines)

    # -- structured research tasks --------------------------------------
    @staticmethod
    def _labelled_sources(prompt: str) -> list[tuple[str, str, str]]:
        """Parse ``--- S1 | Document name ---`` blocks into (key, name, body)."""
        pattern = re.compile(r"---\s*(S\d+)\s*\|\s*(.+?)\s*---")
        matches = list(pattern.finditer(prompt))
        out: list[tuple[str, str, str]] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(prompt)
            out.append((match.group(1), match.group(2), prompt[start:end].strip()))
        return out

    def _comparison(self, prompt: str) -> str:
        """Build a comparison table by quoting each source, never inventing."""
        import json

        sources = self._labelled_sources(prompt)
        if len(sources) < 2:
            return json.dumps({"dimensions": [], "rows": [], "agreements": [], "contradictions": [], "gaps": []})

        dimensions = ["Focus of the work", "Approach described", "Reported outcome"]
        rows = []
        for position, dimension in enumerate(dimensions):
            cells = []
            for key, _name, body in sources:
                sentences = self._sentences(body, 3)
                value = sentences[position] if position < len(sentences) else ""
                if value:
                    cells.append({"source_key": key, "value": value})
            if cells:
                rows.append({"dimension": dimension, "cells": cells})

        shared = None
        for key, _name, body in sources:
            terms = set(self._keywords(body, 10))
            shared = terms if shared is None else (shared & terms)
        agreements = [
            {"claim": f"All sources discuss {term}.", "sources": [k for k, _, _ in sources]}
            for term in sorted(shared or [])[:3]
        ]

        return json.dumps(
            {
                "dimensions": dimensions,
                "rows": rows,
                "agreements": agreements,
                "contradictions": [],
                "gaps": [
                    "Offline mode compares only the retrieved passages; a live model "
                    "is needed to argue contradictions."
                ],
            }
        )

    def _gaps(self, prompt: str) -> str:
        """Surface limitation-style sentences verbatim as evidence-backed gaps."""
        import json

        sources = self._labelled_sources(prompt)
        cues = ("limitation", "future work", "remains", "not yet", "challenge", "however", "open problem")
        gaps = []
        for key, name, body in sources:
            for sentence in re.split(r"(?<=[.!?])\s+", body):
                clean = sentence.strip()
                if len(clean) > 40 and any(cue in clean.lower() for cue in cues):
                    gaps.append(
                        {
                            "gap": clean[:240],
                            "evidence_quote": clean[:240],
                            "source_key": key,
                            "kind": "stated_limitation",
                        }
                    )
                    break
            if len(gaps) >= 5:
                break
        return json.dumps({"gaps": gaps})

    def _hypothesis(self, prompt: str) -> str:
        """Turn each supplied gap into a conservative, testable statement."""
        import json

        gap_lines = re.findall(r"GAP\d+:\s*(.+)", prompt)
        hypotheses = []
        for index, gap in enumerate(gap_lines[:4], start=1):
            subject = gap.strip().rstrip(".")[:160]
            hypotheses.append(
                {
                    "statement": (
                        f"Addressing the gap '{subject}' measurably improves the "
                        "outcome the cited work reports as limited."
                    ),
                    "rationale": (
                        "Derived directly from the cited limitation; offline mode "
                        "restates the gap rather than speculating beyond it."
                    ),
                    "testable_prediction": (
                        "A system that closes this gap outperforms the reported "
                        "baseline on the same metric and dataset."
                    ),
                    "gap_index": index - 1,
                }
            )
        return json.dumps({"hypotheses": hypotheses})

    def _experiment(self, prompt: str) -> str:
        """Produce a conservative experiment skeleton per hypothesis."""
        import json

        statements = re.findall(r"HYP\d+:\s*(.+)", prompt)
        designs = []
        for index, statement in enumerate(statements[:4]):
            designs.append(
                {
                    "hypothesis_index": index,
                    "objective": f"Test whether {statement.strip().rstrip('.')[:180]}.",
                    "datasets": ["The dataset used by the cited baseline"],
                    "baselines": ["The approach reported in the cited work"],
                    "metrics": ["The metric the cited work reports"],
                    "procedure": [
                        "Reproduce the cited baseline on its original dataset.",
                        "Introduce the single change the hypothesis proposes.",
                        "Compare both systems on the same metric with identical splits.",
                        "Repeat across seeds and report variance.",
                    ],
                    "controls": ["Hold the dataset, splits, and metric fixed across arms."],
                    "threats_to_validity": [
                        "Offline mode cannot verify that the cited baseline is reproducible.",
                    ],
                }
            )
        return json.dumps({"experiments": designs})

    def _patent(self, prompt: str) -> str:
        """Report literal term overlap between project concepts and patent text."""
        import json

        concepts = re.findall(r"CONCEPT:\s*(.+)", prompt)
        patent_body = prompt.split("PATENT TEXT:", 1)[-1].lower()
        overlaps = [
            {
                "concept": concept.strip(),
                "overlap": "term appears in the supplied patent text",
                "confidence": "literal-term-match",
            }
            for concept in concepts
            if concept.strip() and concept.strip().lower() in patent_body
        ]
        return json.dumps(
            {
                "overlaps": overlaps[:10],
                "summary": (
                    f"{len(overlaps)} project concept(s) appear verbatim in the supplied "
                    "patent text. This is a literal term match for awareness only."
                ),
            }
        )

    def _novelty(self, prompt: str) -> str:
        """Point each claim at the source sentence that shares the most wording.

        Deliberately says nothing about whether a claim is new — offline or
        online, that judgement is not the model's to make, and the agent
        computes coverage itself.
        """
        import json

        claims = re.findall(r"^\[(\d+)\]\s*(.+)$", prompt, flags=re.MULTILINE)
        sources = self._labelled_sources(prompt)
        if not claims or not sources:
            return json.dumps({"related": []})

        stop = {"the", "and", "for", "with", "that", "this", "from", "which"}
        related = []
        for raw_index, claim in claims[:6]:
            claim_terms = {
                w for w in re.findall(r"[a-z0-9]{4,}", claim.lower()) if w not in stop
            }
            best = None
            for key, _name, body in sources:
                # Line breaks end a sentence too: a fetched abstract starts with
                # "Title: … / Authors: …" lines, which are metadata, not text.
                for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
                    clean = sentence.strip()
                    if len(clean) < 40 or _METADATA_LINE.match(clean):
                        continue
                    overlap = claim_terms & set(re.findall(r"[a-z0-9]{4,}", clean.lower()))
                    if not overlap:
                        continue
                    if best is None or len(overlap) > best[0]:
                        best = (len(overlap), key, clean)
            if best is not None:
                related.append(
                    {
                        "claim_index": int(raw_index),
                        "source_key": best[1],
                        # Verbatim, so the agent's citation check can locate it.
                        "note": best[2][:280],
                    }
                )
        return json.dumps({"related": related})

    # -- BaseChatModel --------------------------------------------------
    def _call(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        prompt = "\n".join(str(getattr(m, "content", m)) for m in messages)

        if TASK_ROUTE in prompt:
            return self._route(prompt)
        if TASK_ANALYSIS in prompt:
            return self._analysis(prompt)
        if TASK_CITATION in prompt:
            return self._citation(prompt)
        if TASK_EXTRACTION in prompt:
            return self._extraction(prompt)
        if TASK_COMPARISON in prompt:
            return self._comparison(prompt)
        if TASK_GAPS in prompt:
            return self._gaps(prompt)
        if TASK_HYPOTHESIS in prompt:
            return self._hypothesis(prompt)
        if TASK_EXPERIMENT in prompt:
            return self._experiment(prompt)
        if TASK_PATENT in prompt:
            return self._patent(prompt)
        if TASK_NOVELTY in prompt:
            return self._novelty(prompt)
        # The grounded-answer chain sends the sources as the system message and
        # the question after it. Quote from the sources only: joined, the last
        # source's body ran on into the question and it was "quoted" as if a
        # document had said it.
        if len(messages) > 1:
            return self._synthesis(
                "\n".join(str(getattr(m, "content", m)) for m in messages[:-1])
            )
        return self._synthesis(prompt)


def _build_groq(model: str, temperature: float, max_tokens: int):
    """Construct a ChatGroq client, or return ``None`` if unavailable."""
    from app.config import settings

    api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return None

    try:
        from langchain_groq import ChatGroq
    except ImportError:  # pragma: no cover - dependency guard
        return None

    # langchain_groq reads the key from the environment.
    os.environ["GROQ_API_KEY"] = api_key

    return ChatGroq(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=60,
        max_retries=2,
    )


@lru_cache(maxsize=8)
def get_chat_model(
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
):
    """Return the chat model every agent should use.

    Args:
        model: Override the configured model ID.
        temperature: Sampling temperature.
        max_tokens: Response cap.

    Returns:
        A LangChain ``BaseChatModel`` — Groq when a key is configured,
        otherwise the deterministic offline model.
    """
    from app.config import settings

    model = model or settings.default_llm
    temperature = settings.llm_temperature if temperature is None else temperature
    max_tokens = max_tokens or settings.llm_max_tokens

    llm = _build_groq(model, temperature, max_tokens)
    if llm is not None:
        return llm

    if not settings.allow_offline_llm:
        raise RuntimeError(
            "No GROQ_API_KEY configured and ALLOW_OFFLINE_LLM is disabled. "
            "Set GROQ_API_KEY in mairos/.env — see .env.example."
        )

    return OfflineChatModel()


def get_fast_model():
    """A smaller/cheaper model for structured extraction and routing."""
    from app.config import settings

    return get_chat_model(model=settings.fast_llm, temperature=0.0)


def describe_provider() -> dict:
    """Report which provider is active — surfaced on ``/api/health``."""
    llm = get_chat_model()
    offline = isinstance(llm, OfflineChatModel)
    from app.config import settings

    return {
        "provider": "offline-fallback" if offline else "groq",
        "model": "mairos-offline" if offline else settings.default_llm,
        "live": not offline,
    }


def reset_provider_cache() -> None:
    """Clear the memoised models (used by tests and config reloads)."""
    get_chat_model.cache_clear()
