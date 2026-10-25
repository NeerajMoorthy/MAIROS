"""Planner Agent — decomposes a complex question into sub-questions.

Separate from the Router: the Router picks *which pipeline* runs, the Planner
breaks a hard question into retrievable parts. Not in the default flows at
mid-review; it is the natural attachment point for research planning and
auto-literature-review in the final build.
"""

from __future__ import annotations

from services.common.json_utils import extract_json

from .base import AgentContext, BaseAgent

PLANNER_PROMPT = (
    "Decompose the research question into 2-4 self-contained sub-questions that "
    "could each be answered from a single passage. Preserve the user's "
    "terminology.\n\n"
    'Return ONLY JSON: {{"sub_questions": ["...", "..."], "rationale": "one sentence"}}\n\n'
    "Question: {question}\n"
)


class PlannerAgent(BaseAgent):
    """Produce a retrieval plan for a multi-hop question."""

    name = "planner"
    stage = "orchestrating"

    async def run(self, ctx: AgentContext) -> AgentContext:
        ctx.log(self.name, f"Decomposing: {ctx.question[:80]}", self.stage)

        sub_questions: list[str] = []
        rationale = ""

        if self.llm is not None:
            parsed = extract_json(
                self.invoke_llm(PLANNER_PROMPT.format(question=ctx.question)),
                default=None,
            )
            if isinstance(parsed, dict):
                sub_questions = [
                    str(q).strip() for q in parsed.get("sub_questions", []) if str(q).strip()
                ][:4]
                rationale = str(parsed.get("rationale", ""))[:200]

        if not sub_questions:
            sub_questions = [ctx.question]
            rationale = "Question treated as single-hop."

        ctx.intermediate_results["plan"] = {
            "sub_questions": sub_questions,
            "rationale": rationale,
        }
        ctx.log(self.name, f"Plan: {len(sub_questions)} sub-question(s)", self.stage)
        return ctx
