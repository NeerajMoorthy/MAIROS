"""Novelty Agent — what is new *here*, never what is new *in the field*.

The single most dangerous thing an automated research assistant can say is
"this idea is novel". It is an unbounded negative claim: to support it you must
show that nothing in the published record anticipates the idea, and no system
that has read a handful of PDFs is in a position to show that.

So this agent answers a narrower question that it *can* answer, and refuses the
wider one explicitly rather than silently:

* **"New to this project"** — computed, not generated. Each claim is scored by
  content-word overlap against the passages actually retrieved from the
  project's corpus, and the verdict comes from that number. Where a claim is
  already covered, the passage covering it is cited; where it is not, the
  output says so with the exact scope of what was searched.
* **"Novel in the field"** — always reported as ``not_assessed``, with a reason
  string naming what would be required to assess it. There is no code path that
  can set this field to anything else; see :data:`FIELD_NOVELTY`.

The LLM is used for one thing only: describing how the nearest prior passage
relates to the claim. Its description is kept only if it can still be traced to
a retrieved passage, exactly like every other generated statement in MAIROS.
It never decides a verdict, because a model asked "is this novel?" will oblige.
"""

from __future__ import annotations

from services.common.json_utils import extract_json
from services.generation.provider import TASK_NOVELTY
from services.literature.coverage import join_names
from services.literature.papers import (
    FETCHED_PREFIXES,
    SOURCE_NAMES,
    document_id_for,
    source_name_for_document,
)

from .base import AgentContext, BaseAgent
from .evidence import (
    Source,
    citation_for,
    group_sources,
    render_sources,
    strip_question_framing,
    tokens,
)

# The only value this field is ever given. Kept as a constant so that a grep
# for it shows there is no branch that upgrades it to a novelty claim.
FIELD_NOVELTY = "not_assessed"

FIELD_NOVELTY_REASON = (
    "Novelty in the field was not assessed. MAIROS compared this claim against "
    "{scope} only. Establishing that nothing in the published record anticipates "
    "a claim requires a systematic search MAIROS has not performed, so no "
    "statement about novelty in the field can be made from this evidence."
)

# Overlap of the claim's content words with the best-matching retrieved
# passage. These are corpus-coverage thresholds, not novelty thresholds.
COVERED_THRESHOLD = 0.60
PARTIAL_THRESHOLD = 0.30

# "Covered" also requires this many content words to actually match, not just a
# high proportion of them. The ratio alone is dominated by chance on a short
# claim: "Transformer accuracy on protein assays" is four content words, so
# three incidental hits anywhere in a 2,000-character passage reach 0.75 and a
# table caption gets reported as prior coverage of the idea. A proportion says
# how much of the claim matched; this says how much evidence there was.
MIN_MATCHED_TOKENS = 4

VERDICT_LABELS = {
    "covered_in_corpus": "Already covered by this project's sources",
    "partially_covered": "Partly touched on by this project's sources",
    "not_found_in_corpus": "Not found in this project's sources",
}

MAX_CLAIMS = 6
# Passages retrieved for each claim on top of the flow's own retrieval.
CLAIM_TOP_K = 5
# Sources shown to the model when it writes "how this relates" notes; coverage
# itself is computed against every source, not just these.
NOTE_SOURCES = 6


def _ordered(names: set[str]) -> list[str]:
    """Source names in the order the sources are listed, unknown ones last."""
    known = [name for name in SOURCE_NAMES.values() if name in names]
    return known + sorted(n for n in names if n and n not in known)


def _join(names: list[str]) -> str:
    return join_names(names) or "the literature search"

NOVELTY_PROMPT = (
    TASK_NOVELTY + "\n"
    "For each claim below, find the passage in the sources that comes CLOSEST "
    "to it and describe the relationship in one sentence (for example: states "
    "the same thing, studies the same idea in a different setting, or "
    "contradicts it). Use ONLY the sources.\n\n"
    "Do NOT judge whether a claim is novel, original, or new — you have not "
    "seen the literature, only these passages. If no passage is related to a "
    "claim, omit that claim entirely.\n\n"
    "Return ONLY JSON:\n"
    '{{"related": [{{"claim_index": 0, "source_key": "S1", '
    '"note": "one sentence, grounded in that source"}}]}}\n\n'
    "Claims:\n{claims}\n\n"
    "Sources:\n{sources}\n"
)


class NoveltyAgent(BaseAgent):
    """Assess claims against the project corpus; never against the field."""

    name = "novelty"
    stage = "analyzing"

    # ------------------------------------------------------------------
    @staticmethod
    def _claims(ctx: AgentContext) -> list[dict]:
        """The statements to assess, newest chain first.

        When the flow ran the hypothesis step, its hypotheses are what get
        assessed — "is this hypothesis already in the corpus?" is far more
        useful than scoring the user's phrasing of the request. The request
        ("what hypotheses follow…?") is not a claim, so it is never scored in
        their place, even when no hypothesis could be proposed. A parsed
        project brief comes next: its stated contributions are the claims a
        student wants checked, and the whole pasted description is far too
        long to score as one claim.
        """
        # HypothesisAgent stores {"hypotheses": [...]} — the same payload the
        # experiment step and the API response read.
        generated = ctx.intermediate_results.get("hypotheses")
        if isinstance(generated, dict):
            claims = [
                {"claim": str(item.get("statement", "")).strip(), "origin": "hypothesis"}
                for item in generated.get("hypotheses") or []
                if isinstance(item, dict) and str(item.get("statement", "")).strip()
            ]
            return claims[:MAX_CLAIMS]

        brief = ctx.intermediate_results.get("project_brief") or {}
        stated = [str(c).strip() for c in brief.get("contributions") or [] if str(c).strip()]
        if stated:
            return [{"claim": c, "origin": "project"} for c in stated[:MAX_CLAIMS]]

        question = (ctx.question or "").strip()
        return [{"claim": question, "origin": "question"}] if question else []

    # ------------------------------------------------------------------
    @staticmethod
    def _coverage(
        claim: str, sources: list[Source]
    ) -> tuple[float, int, Source | None, dict | None]:
        """Best content-word overlap of *claim* with any retrieved passage.

        Returns the ratio, how many content words actually matched, the source
        they came from, and a citation for the passage. Deterministic: the
        verdict must not depend on a model.

        The claim is stripped of question framing first. The ratio divides by
        the claim's own token count, so words the user typed only to ask the
        question — "idea", "already", "whether", "anyone" — are tokens the
        corpus can never match, and each one drags the score towards "not found
        in this project's sources". Novelty requests are phrased that way by
        definition, and that is the one verdict a reader takes as a signal, so
        the bias runs in the direction this agent can least afford.
        """
        claim_tokens = tokens(strip_question_framing(claim, fallback=claim))
        if not claim_tokens:
            return 0.0, 0, None, None

        best_ratio = 0.0
        best_matched = 0
        best_source: Source | None = None
        best_chunk: dict | None = None

        for source in sources:
            for chunk in source.chunks:
                overlap = claim_tokens & tokens(chunk.get("text", ""))
                if not overlap:
                    continue
                ratio = len(overlap) / len(claim_tokens)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_matched = len(overlap)
                    best_source, best_chunk = source, chunk

        if best_chunk is None:
            return 0.0, 0, None, None

        return (
            round(best_ratio, 3),
            best_matched,
            best_source,
            {
                "chunk_id": best_chunk.get("chunk_id", ""),
                "document_id": best_chunk.get("document_id", ""),
                "document_name": best_chunk.get("document_name", ""),
                "page": best_chunk.get("page"),
                "quote": " ".join(str(best_chunk.get("text", "")).split())[:320],
            },
        )

    @staticmethod
    def _verdict(ratio: float, matched: int) -> str:
        """Coverage verdict: a high proportion AND enough matched words."""
        if ratio >= COVERED_THRESHOLD and matched >= MIN_MATCHED_TOKENS:
            return "covered_in_corpus"
        if ratio >= PARTIAL_THRESHOLD:
            return "partially_covered"
        return "not_found_in_corpus"

    # ------------------------------------------------------------------
    # The Indexer writes fetched papers under these document-id prefixes.
    FETCHED_PREFIXES = FETCHED_PREFIXES

    @classmethod
    def _scope_text(cls, sources: list[Source], papers: list) -> str:
        """Exactly what was searched, in words a reader can check.

        The `review` flow fetches abstracts, indexes them under this project,
        and retrieves them straight back — so those abstracts arrive here as
        "documents from this project". Counting them again alongside the
        papers list described one corpus as two, and on a project with no
        uploads of its own it presented "absent from a single literature query
        run moments ago" as a statement about the user's library. They are
        separated by document id instead, named by the sources the run's
        papers actually came from, and kept apart from abstracts that earlier
        searches indexed.
        """
        fetched = [s for s in sources if str(s.document_id).startswith(cls.FETCHED_PREFIXES)]
        owned = [s for s in sources if s not in fetched]

        # Which fetched abstracts this run's search produced. Records without
        # source ids (built before they existed) cannot be matched, so when
        # every paper is like that the fetched abstracts are taken as this run's.
        names_by_document = {
            document_id_for(p): list(p.get("sources") or [p.get("source") or ""])
            for p in papers
            if p.get("source_ids")
        }
        if names_by_document:
            now = [s for s in fetched if s.document_id in names_by_document]
        else:
            now = fetched if papers else []
        earlier = [s for s in fetched if s not in now]

        parts = []
        if owned:
            parts.append(f"{len(owned)} document(s) already in this project")
        if now:
            names = _ordered(
                {
                    name
                    for s in now
                    for name in names_by_document.get(s.document_id)
                    or [source_name_for_document(s.document_id)]
                }
            )
            parts.append(f"{len(now)} abstract(s) fetched from {_join(names)} during this run")
        if earlier:
            parts.append(f"{len(earlier)} abstract(s) fetched by earlier searches in this project")
        if not fetched and papers and not owned:
            # Papers were fetched but none came back through retrieval.
            names = _ordered(
                {name for p in papers for name in (p.get("sources") or [p.get("source") or "arXiv"])}
            )
            parts.append(
                f"{len(papers)} abstract(s) fetched from {_join(names)} during this run"
            )

        return _join(parts) if parts else "no documents from this project"

    # ------------------------------------------------------------------
    def _passages(self, ctx: AgentContext, claims: list[dict]) -> list[dict]:
        """Every passage the claims are checked against.

        This used to be the flow's retrieved passages alone. In the `project`
        flow those are the top five for the whole description: a live run kept
        8 papers and checked the contributions against 4 of them, all from one
        source, while the answer said 8 had been searched. Now it is the flow's
        passages, every abstract this run fetched, and a retrieval for each
        claim itself, so a paper that covers a claim is found even when it did
        not rank for the description as a whole.
        """
        pool = list(ctx.retrieved_chunks) + list(
            ctx.intermediate_results.get("fetched_chunks") or []
        )
        if ctx.chroma_store is not None and ctx.project_id:
            from services.retrieval.hybrid import HybridRetriever

            retriever = HybridRetriever(vector=ctx.chroma_store)
            for item in claims:
                try:
                    found, _ = retriever.retrieve(
                        item["claim"], project_id=ctx.project_id, top_k=CLAIM_TOP_K
                    )
                except Exception as exc:  # a failed lookup narrows the check, it does not end it
                    ctx.log(self.name, f"Per-claim retrieval failed ({type(exc).__name__})", self.stage)
                    continue
                pool += [
                    {
                        "chunk_id": chunk.chunk_id,
                        "document_id": chunk.document_id,
                        "document_name": chunk.document_name,
                        "page": chunk.page,
                        "text": chunk.text,
                        "score": chunk.score,
                    }
                    for chunk in found
                ]

        seen: set[str] = set()
        unique: list[dict] = []
        for chunk in pool:
            key = str(chunk.get("chunk_id") or "") or f"{chunk.get('document_id')}:{len(unique)}"
            if key not in seen:
                seen.add(key)
                unique.append(chunk)
        return unique

    # ------------------------------------------------------------------
    def _related_notes(
        self, claims: list[dict], sources: list[Source]
    ) -> tuple[dict[int, list[dict]], int]:
        """Model-written 'how this relates' notes, dropped unless citable."""
        if self.llm is None or not sources:
            return {}, 0

        rendered_claims = "\n".join(
            f"[{index}] {item['claim'][:300]}" for index, item in enumerate(claims)
        )
        parsed = extract_json(
            self.invoke_llm(
                NOVELTY_PROMPT.format(
                    claims=rendered_claims, sources=render_sources(sources)
                )
            ),
            default={},
        )
        if not isinstance(parsed, dict):
            return {}, 0

        by_key = {source.key: source for source in sources}
        notes: dict[int, list[dict]] = {}
        dropped = 0

        for item in parsed.get("related", []):
            if not isinstance(item, dict):
                continue
            note = str(item.get("note", "")).strip()
            source = by_key.get(str(item.get("source_key", "")).strip())
            try:
                index = int(item.get("claim_index", -1))
            except (TypeError, ValueError):
                index = -1

            if not note or source is None or not 0 <= index < len(claims):
                dropped += 1
                continue

            citation = citation_for(note, source.chunks)
            if citation is None:
                # The note describes something the passage does not say.
                dropped += 1
                continue

            notes.setdefault(index, []).append(
                {
                    "document_name": source.document_name,
                    "note": note[:300],
                    "citation": citation,
                }
            )

        return notes, dropped

    # ------------------------------------------------------------------
    async def run(self, ctx: AgentContext) -> AgentContext:
        claims = self._claims(ctx)
        passages = self._passages(ctx, claims)
        # Every document is scored; only the model's notes prompt is capped.
        sources = group_sources(passages, limit=max(1, len(passages)))
        papers = ctx.intermediate_results.get("retrieved_papers", []) or []
        scope = self._scope_text(sources, papers)

        if not claims:
            ran_hypotheses = isinstance(ctx.intermediate_results.get("hypotheses"), dict)
            ctx.intermediate_results["novelty"] = {
                "scope": scope,
                "assessments": [],
                "field_novelty": FIELD_NOVELTY,
                "note": (
                    "No hypothesis was proposed, so there was nothing to check against the corpus."
                    if ran_hypotheses
                    else "Nothing to assess — no claim was supplied."
                ),
            }
            ctx.log(self.name, "No claim to assess", self.stage)
            return ctx

        notes, dropped = self._related_notes(claims, sources[:NOTE_SOURCES])

        assessments = []
        for index, item in enumerate(claims):
            ratio, matched, source, citation = self._coverage(item["claim"], sources)
            verdict = self._verdict(ratio, matched)
            nearest = list(notes.get(index, []))

            # The computed nearest passage is evidence in its own right, and it
            # is there whether or not the model wrote anything usable.
            if citation is not None and not any(
                entry["citation"]["chunk_id"] == citation["chunk_id"] for entry in nearest
            ):
                nearest.insert(
                    0,
                    {
                        "document_name": source.document_name if source else "",
                        "note": "Closest passage in the corpus by wording overlap.",
                        "citation": citation,
                    },
                )

            assessments.append(
                {
                    "claim": item["claim"][:400],
                    "origin": item["origin"],
                    "verdict": verdict,
                    "verdict_label": VERDICT_LABELS[verdict],
                    "corpus_overlap": ratio,
                    "matched_terms": matched,
                    "nearest_prior_work": nearest,
                    # Constant by construction — see the module docstring.
                    "field_novelty": FIELD_NOVELTY,
                    "field_novelty_reason": FIELD_NOVELTY_REASON.format(scope=scope),
                }
            )

        novel_to_corpus = sum(
            1 for a in assessments if a["verdict"] == "not_found_in_corpus"
        )

        ctx.intermediate_results["novelty"] = {
            "scope": scope,
            "assessments": assessments,
            "field_novelty": FIELD_NOVELTY,
            "uncited_notes_dropped": dropped,
            "limits": (
                "These verdicts describe coverage within "
                f"{scope}. 'Not found in this project's sources' means MAIROS "
                "found no supporting passage in what it searched — it is not a "
                "finding of originality, and it does not become one by being "
                "repeated."
            ),
        }

        ctx.log(
            self.name,
            f"Assessed {len(assessments)} claim(s) against {scope}: "
            f"{novel_to_corpus} not found in the corpus"
            + (f"; {dropped} uncited note(s) dropped" if dropped else ""),
            self.stage,
        )
        return ctx
