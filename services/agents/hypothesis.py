"""Hypothesis Generation Agent — proposals chained to evidenced gaps.

A hypothesis is the first output in this system that is genuinely *new* text
rather than a restatement of a source, which is exactly why it needs the
tightest leash. The rule here: a hypothesis may only exist if it is attached to
a gap the Gap Detection agent already evidenced with a quote. The chain is

    passage → quoted gap → hypothesis

and the citation travels the whole way, so a reader can always get back to the
sentence that motivated a proposal. A hypothesis the model attaches to no gap
is dropped, because nothing in the corpus would support showing it.

Each hypothesis must also carry a falsifiable prediction. "X might help" is not
a hypothesis; "X beats the reported baseline on the same metric" is.
"""

from __future__ import annotations

from services.common.json_utils import extract_json
from services.generation.provider import TASK_HYPOTHESIS

from .base import AgentContext, BaseAgent

HYPOTHESIS_PROMPT = (
    TASK_HYPOTHESIS + "\n"
    "You are proposing research hypotheses for a researcher. Each numbered gap "
    "below was quoted from a real paper in their library.\n\n"
    "For each gap you address, write ONE hypothesis that is specific, "
    "falsifiable, and answerable with an experiment. State what you expect to "
    "happen and under what conditions. Do not propose anything the gap does "
    "not motivate, and do not invent results.\n\n"
    "Return ONLY JSON:\n"
    '{{"hypotheses": [{{"statement": "...",\n'
    '                   "rationale": "why the gap motivates this",\n'
    '                   "testable_prediction": "what would be observed if true",\n'
    '                   "gap_index": 0}}]}}\n\n'
    "Gaps:\n{gaps}\n"
)

MAX_HYPOTHESES = 6


class HypothesisAgent(BaseAgent):
    """Generate falsifiable hypotheses from evidenced research gaps."""

    name = "hypothesis"
    stage = "analyzing"

    # ------------------------------------------------------------------
    @staticmethod
    def _gap_records(ctx: AgentContext) -> list[dict]:
        gaps = ctx.intermediate_results.get("gaps") or {}
        return [gap for gap in gaps.get("gaps", []) if isinstance(gap, dict)]

    # ------------------------------------------------------------------
    async def run(self, ctx: AgentContext) -> AgentContext:
        gaps = self._gap_records(ctx)

        if not gaps:
            ctx.intermediate_results["hypotheses"] = {
                "hypotheses": [],
                "note": (
                    "No evidenced gap was available, so no hypothesis was generated. "
                    "Hypotheses in MAIROS are only proposed on top of a gap that was "
                    "quoted from a source."
                ),
            }
            ctx.log(
                self.name,
                "No evidenced gaps on the context — nothing to hypothesise from",
                self.stage,
            )
            return ctx

        ctx.log(self.name, f"Generating hypotheses from {len(gaps)} evidenced gap(s)", self.stage)

        listing = "\n".join(
            f"GAP{index + 1}: {gap.get('gap', '')} "
            f"(stated in {gap.get('source_document', 'a source')})"
            for index, gap in enumerate(gaps)
        )

        parsed = {}
        if self.llm is not None:
            parsed = extract_json(
                self.invoke_llm(HYPOTHESIS_PROMPT.format(gaps=listing)), default={}
            )
        if not isinstance(parsed, dict):
            parsed = {}

        hypotheses: list[dict] = []
        dropped = 0

        for item in parsed.get("hypotheses", [])[: MAX_HYPOTHESES * 2]:
            if not isinstance(item, dict):
                continue

            statement = str(item.get("statement", "")).strip()
            prediction = str(item.get("testable_prediction", "")).strip()
            if not statement or not prediction:
                dropped += 1
                continue

            try:
                gap_index = int(item.get("gap_index", -1))
            except (TypeError, ValueError):
                gap_index = -1

            if not 0 <= gap_index < len(gaps):
                # An unattached hypothesis has no evidence chain behind it.
                dropped += 1
                continue

            gap = gaps[gap_index]
            hypotheses.append(
                {
                    "id": f"HYP{len(hypotheses) + 1}",
                    "statement": statement[:400],
                    "rationale": str(item.get("rationale", "")).strip()[:400],
                    "testable_prediction": prediction[:400],
                    "grounded_in_gap": gap.get("id", f"GAP{gap_index + 1}"),
                    "gap_text": str(gap.get("gap", ""))[:300],
                    # The citation travels with the gap it came from.
                    "citation": gap.get("citation"),
                }
            )
            if len(hypotheses) >= MAX_HYPOTHESES:
                break

        result = {"hypotheses": hypotheses}
        if dropped:
            result["unattached_dropped"] = dropped
        if not hypotheses:
            result["note"] = (
                "The model returned no hypothesis that could be attached to an "
                "evidenced gap, so none is shown."
            )

        ctx.intermediate_results["hypotheses"] = result
        ctx.log(
            self.name,
            f"{len(hypotheses)} hypothesis/es grounded in cited gaps"
            + (f", {dropped} unattached dropped" if dropped else ""),
            self.stage,
        )
        return ctx
