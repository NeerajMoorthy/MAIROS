"""Router agent — decides which agents run, and in what order.

This is the piece that makes the Orchestrator an actual decision-maker rather
than a hardcoded if/else. It asks the LLM to classify the request into a flow
and returns a validated plan; a keyword heuristic covers LLM failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.common.json_utils import extract_json
from services.generation.provider import TASK_ROUTE

from .base import AgentContext, BaseAgent

# Each flow is an ordered list of agent names the orchestrator will execute.
FLOWS: dict[str, list[str]] = {
    # "Find me papers on X" — external literature discovery
    "search": ["literature", "indexer", "knowledge_graph", "citation", "synthesis"],
    # "Analyse this paper I uploaded"
    "analyze": ["loader", "analysis", "knowledge_graph", "citation"],
    # "Answer this question from my library" — the RAG path
    "answer": ["retriever", "synthesis", "citation"],
    # "Compare these papers" — cited comparison table across documents
    "compare": ["retriever", "comparison", "citation", "synthesis"],
    # "What is missing in this literature?" — evidence-backed gap detection
    "gaps": ["retriever", "gaps", "citation", "synthesis"],
    # "What should we try next?" — hypotheses chained to evidenced gaps, then
    # checked against the corpus. Novelty runs after hypothesis on purpose:
    # "is this hypothesis already covered by your sources?" is a far more
    # useful question than the same check against the user's phrasing, and
    # without this the agent's hypothesis branch was unreachable in every
    # registered flow.
    "hypothesis": ["retriever", "gaps", "hypothesis", "novelty", "citation", "synthesis"],
    # "Is this already in my corpus?" — corpus coverage only, never field novelty
    "novelty": ["retriever", "novelty", "citation", "synthesis"],
    # "Review the literature on X" — discover, index, retrieve, contrast, assess.
    # This is the `search` flow chained into `comparison` and `synthesis`. The
    # `retriever` in the middle is the bridge the chain needs: `literature` puts
    # papers on the context and `indexer` embeds them, but `comparison` reads
    # `retrieved_chunks`, so without a retrieval step it would compare nothing.
    "review": [
        "literature",
        "indexer",
        "retriever",
        "comparison",
        "novelty",
        "knowledge_graph",
        "citation",
        "synthesis",
    ],
    # "Here is my project — what exists, what is missing, what does mine add?"
    # The review chain with an intake step in front: the pasted description is
    # read into a brief first, so the search, retrieval and coverage checks run
    # on its problem, methods and stated contributions rather than on two
    # thousand characters of prose.
    #
    # The graph is built straight after indexing, before anything reads it. A
    # live run (23 Oct 2026) had it after `gaps`, so the gap agent's graph
    # signals — thinly covered concepts, never-compared methods — were computed
    # from an empty graph and the section came back blank, while the graph
    # filled to 48 nodes moments later. Built here, it also mines every
    # fetched abstract rather than the retriever's top five, and retrieval
    # gets its graph boost.
    "project": [
        "intake",
        "literature",
        "indexer",
        "knowledge_graph",
        "retriever",
        "comparison",
        "gaps",
        "novelty",
        "citation",
        "synthesis",
    ],
    # "Does anything here overlap a patent?" — awareness only, never advice
    "patent": ["retriever", "patent_awareness", "citation", "synthesis"],
    # "How would we test that?" — full chain down to an executable protocol
    "experiment": [
        "retriever",
        "gaps",
        "hypothesis",
        "experiment",
        "citation",
        "synthesis",
    ],
}

# Human-readable labels for the UI; keys must match FLOWS.
FLOW_DESCRIPTIONS: dict[str, str] = {
    "search": "Discover new papers on a topic from arXiv, OpenAlex and Semantic Scholar, and index them.",
    "analyze": "Break down one uploaded document into contributions and methodology.",
    "answer": "Answer a question from the indexed library, with citations.",
    "compare": "Contrast two or more sources in a table where every cell is cited.",
    "gaps": "Find open research gaps, each quoted from the passage that states it.",
    "hypothesis": "Propose falsifiable hypotheses, each attached to an evidenced gap.",
    "experiment": "Design a runnable experiment for each generated hypothesis.",
    "novelty": (
        "Check whether a claim is already covered by this project's sources. "
        "Reports coverage in your corpus only — never novelty in the field."
    ),
    "review": (
        "Full literature review: find papers, index them, contrast them in a "
        "cited table, and report what is new to this project."
    ),
    "project": (
        "Review a pasted project description: read it into a brief, find related "
        "papers, contrast them, list the gaps they state, and check each stated "
        "contribution against what was found — coverage only, never a novelty verdict."
    ),
    "patent": (
        "Report where project concepts overlap patent text you supplied — "
        "research support only, not legal advice."
    ),
}

ROUTER_PROMPT = (
    TASK_ROUTE + "\n"
    "You are the orchestrator of a multi-agent research system. Classify the "
    "user request into exactly one flow.\n\n"
    "Flows:\n"
    '- "search": the user wants to DISCOVER new papers on a topic.\n'
    '- "analyze": the user wants a specific uploaded document summarised or '
    "broken down.\n"
    '- "answer": the user asks a question to be answered from documents already '
    "in their library.\n"
    '- "compare": the user wants two or more papers/sources contrasted with each '
    "other.\n"
    '- "gaps": the user asks what is missing, unsolved, or under-explored in the '
    "literature.\n"
    '- "hypothesis": the user asks what to investigate or try next.\n'
    '- "experiment": the user asks how a claim or hypothesis would be tested.\n'
    '- "novelty": the user asks whether an idea is already known, already done, '
    "or new.\n"
    '- "review": the user asks for a literature review or survey of a topic — '
    "discover papers AND contrast them, not just list them.\n"
    '- "project": the user describes THEIR OWN project or idea at length and wants '
    "related work, gaps, or how it relates to existing papers.\n"
    '- "patent":the user asks about patents, prior art, or intellectual '
    "property overlap.\n\n"
    "Context: the project currently has {doc_count} indexed document(s). "
    "A specific document {doc_state}.\n\n"
    'Reply with ONLY JSON: {{"flow": '
    '"search|analyze|answer|compare|gaps|hypothesis|experiment|novelty|review|project|patent", '
    '"reason": "one short sentence"}}\n\n'
    "User request: {question}\n"
)

_SEARCH_HINTS = (
    "find papers", "search for", "recent work", "literature", "state of the art",
    "papers on", "publications", "arxiv", "who has written", "survey of",
)
_ANALYZE_HINTS = (
    "analyze this", "analyse this", "summarize this paper", "summarise this paper",
    "this pdf", "the uploaded", "key contributions of this",
)
_COMPARE_HINTS = (
    "compare", "comparison", "versus", " vs ", "difference between",
    "differ from", "contrast", "side by side",
)
_GAP_HINTS = (
    "gap", "open problem", "open question", "unanswered", "still missing",
    "what is missing", "what's missing", "under-explored", "understudied",
    "unexplored", "limitations remain",
)
_HYPOTHESIS_HINTS = (
    "hypothesis", "hypotheses", "what should we try", "what to try next",
    "research direction", "propose an idea", "promising direction",
)
_EXPERIMENT_HINTS = (
    "experiment", "how would we test", "how do we test", "how to test",
    "study design", "experimental design",
    # Multi-word on purpose: bare "protocol" and "ablation" are ordinary
    # subject-matter nouns (a consensus protocol, a TLS handshake protocol,
    # ablation of attention heads) and captured requests that were about them.
    "experimental protocol", "study protocol", "evaluation protocol",
    "ablation study", "ablation studies", "run an ablation",
)
_PATENT_HINTS = ("patent", "prior art", "intellectual property", "patentab")
# Unambiguous "go and find papers" phrasing. Checked before the research flows
# because those match on subject-matter nouns: "protocol" and "ablation" are in
# _EXPERIMENT_HINTS and "prior art" is in _PATENT_HINTS, so "find recent papers
# on the Raft consensus protocol" routed to an experiment-design pipeline over
# the existing library and never called arXiv at all — and only once the
# project had documents, so the same request behaved differently on day two.
_DISCOVERY_HINTS = (
    "find papers", "find recent papers", "find me papers", "search for papers",
    "search for publications", "papers on", "papers about", "publications on",
    "publications about", "literature on", "literature about", "recent work on",
    "survey of", "what has been published",
)
# Deliberately multi-word: a bare "novel" appears in plenty of ordinary
# requests ("find papers on novel architectures") that are not novelty checks.
_NOVELTY_HINTS = (
    "novelty", "is this novel", "how novel", "already been done", "been done before",
    "is this new", "anything new here", "already known", "new to this", "originality",
)
_REVIEW_HINTS = (
    "literature review", "review the literature", "review of the literature",
    "survey the literature", "systematic review", "write a review",
    "state of the field",
)
# A request describing the user's own work. Only routed to `project` when it is
# also long enough to be a description: "is my project idea new?" is a
# novelty question, not a brief to read.
_PROJECT_HINTS = (
    "my project", "our project", "project description", "my idea", "our idea",
    "we propose", "we are building", "we are developing", "i am building",
    "i am developing", "proposed system", "my system", "our system",
)
PROJECT_MIN_CHARS = 200
# A pasted block this long is a description whatever words it uses.
PROJECT_LONG_CHARS = 800


def looks_like_project_description(question: str) -> bool:
    """Whether a request is a pasted description of the user's own project."""
    text = (question or "").strip()
    lowered = text.lower()
    if len(text) >= PROJECT_LONG_CHARS:
        return True
    return len(text) >= PROJECT_MIN_CHARS and any(h in lowered for h in _PROJECT_HINTS)


@dataclass
class RoutingDecision:
    """The orchestrator's execution plan for one request."""

    flow: str
    agents: list[str] = field(default_factory=list)
    reason: str = ""
    source: str = "llm"

    def as_dict(self) -> dict:
        return {
            "flow": self.flow,
            "agents": self.agents,
            "reason": self.reason,
            "decided_by": self.source,
        }


class RouterAgent(BaseAgent):
    """Choose the agent pipeline for a request."""

    name = "orchestrator"
    stage = "orchestrating"

    # ------------------------------------------------------------------
    @staticmethod
    def heuristic(question: str, has_document: bool, doc_count: int) -> tuple[str, str]:
        """Keyword fallback used when the LLM is unavailable."""
        q = (question or "").lower()

        if has_document:
            return "analyze", "A specific document was supplied with the request."
        if any(h in q for h in _ANALYZE_HINTS):
            return "analyze", "Request refers to a specific uploaded document."

        # A pasted project description is checked before the short-phrase
        # hints: it will usually contain "gap", "compare" or "literature"
        # somewhere, and any of those would send it down a flow that reads it
        # as a one-line question.
        if looks_like_project_description(question):
            return "project", "Request is a description of the user's own project."

        # `review` discovers its own papers, so unlike the flows below it does
        # not need the project to hold anything yet. It is checked ahead of
        # `search` because every review request also reads as a search one.
        if any(h in q for h in _REVIEW_HINTS):
            return "review", "Request asks for a literature review, not just a paper list."

        # The research workflows all read the existing library, so they are only
        # offered once something is indexed; with an empty project the useful
        # answer is to go and find papers first.
        #
        # Order matters and follows how the flows nest: an experiment request
        # implies hypotheses, which imply gaps. Checking the longest chain first
        # stops "how would we test this hypothesis?" from stopping at `gaps`.
        # Explicit discovery intent wins over a topic keyword, unless the user
        # also asked for a comparison — "compare recent papers on X" is a
        # comparison of what the request finds, not a bare search.
        if any(h in q for h in _DISCOVERY_HINTS) and not any(h in q for h in _COMPARE_HINTS):
            return "search", "Request explicitly asks to discover literature."

        if doc_count > 0:
            if any(h in q for h in _PATENT_HINTS):
                return "patent", "Request mentions patents or prior art."
            if any(h in q for h in _NOVELTY_HINTS):
                return "novelty", "Request asks whether an idea is already covered."
            if any(h in q for h in _EXPERIMENT_HINTS):
                return "experiment", "Request asks how a claim would be tested."
            if any(h in q for h in _HYPOTHESIS_HINTS):
                return "hypothesis", "Request asks what to investigate next."
            if any(h in q for h in _GAP_HINTS):
                return "gaps", "Request asks what is missing from the literature."
            # Comparison last of the research flows: "compare recent papers on X"
            # is a comparison of the library, not a fresh literature hunt.
            if any(h in q for h in _COMPARE_HINTS):
                return "compare", "Request asks for sources to be contrasted with each other."

        if any(h in q for h in _SEARCH_HINTS):
            return "search", "Request asks to discover external literature."
        if doc_count == 0:
            return "search", "No documents indexed yet, so external retrieval is needed."
        return "answer", "Question can be answered from the indexed library."

    # ------------------------------------------------------------------
    def decide(
        self,
        question: str,
        has_document: bool = False,
        doc_count: int = 0,
        forced_flow: str | None = None,
    ) -> RoutingDecision:
        """Return the flow to execute."""
        if forced_flow in FLOWS:
            return RoutingDecision(
                flow=forced_flow,
                agents=list(FLOWS[forced_flow]),
                reason="Flow explicitly requested by the caller.",
                source="explicit",
            )

        # A supplied document is unambiguous — no need to spend an LLM call.
        # So is a pasted project description, and a model shown 2,000
        # characters that mention gaps and comparisons may well pick one of
        # those flows instead.
        if has_document or looks_like_project_description(question):
            flow, reason = self.heuristic(question, has_document, doc_count)
            return RoutingDecision(flow, list(FLOWS[flow]), reason, "rule")

        # The offline model's "routing" is the same keyword heuristic below, so
        # skip the round-trip and report the decision honestly as a heuristic.
        from services.generation.provider import OfflineChatModel

        if self.llm is not None and not isinstance(self.llm, OfflineChatModel):
            try:
                raw = self.invoke_llm(
                    ROUTER_PROMPT.format(
                        question=question,
                        doc_count=doc_count,
                        # Always "was not supplied": the has_document case
                        # returned above without ever reaching the model, so
                        # any other value here would be unreachable and the
                        # conditional that produced it was misleading.
                        doc_state="was not supplied",
                    )
                )
                data = extract_json(raw, default={})
                flow = str((data or {}).get("flow", "")).strip().lower()
                if flow in FLOWS:
                    return RoutingDecision(
                        flow=flow,
                        agents=list(FLOWS[flow]),
                        reason=str((data or {}).get("reason", ""))[:200],
                        source="llm",
                    )
            except Exception as exc:
                print(f"[router] LLM routing failed, falling back: {exc}")

        flow, reason = self.heuristic(question, has_document, doc_count)
        return RoutingDecision(flow, list(FLOWS[flow]), reason, "heuristic")

    # ------------------------------------------------------------------
    async def run(self, ctx: AgentContext) -> AgentContext:
        """Store a routing decision on the context."""
        # `retrieved_chunks` counts chunks, not documents — a single PDF can
        # be dozens. The distinct document count is what both the doc_count
        # gate and the prompt's "N indexed document(s)" actually mean.
        decision = self.decide(
            ctx.question,
            has_document=bool(ctx.document_id),
            doc_count=len({c.get("document_id") for c in ctx.retrieved_chunks}),
        )
        ctx.intermediate_results["routing"] = decision.as_dict()
        ctx.log(self.name, f"Selected '{decision.flow}' flow — {decision.reason}")
        return ctx
