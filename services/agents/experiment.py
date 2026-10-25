"""Experiment Design Agent — a runnable protocol per hypothesis.

Takes the hypotheses the previous agent attached to evidenced gaps and turns
each into something a student could actually execute: an objective, the data
and baselines to run against, the metric that decides the outcome, an ordered
procedure, the controls that keep the comparison fair, and the threats that
would undermine the result.

Two rules keep this from drifting into fiction:

* A design must belong to a hypothesis that exists on the context. A protocol
  for a hypothesis nobody proposed is dropped.
* A design must name at least one metric and one procedure step. "Run
  experiments and compare" decides nothing, so it is not shipped as a design.
"""

from __future__ import annotations

from services.common.json_utils import extract_json
from services.generation.provider import TASK_EXPERIMENT

from .base import AgentContext, BaseAgent

EXPERIMENT_PROMPT = (
    TASK_EXPERIMENT + "\n"
    "Design one experiment for each hypothesis below. The reader is a student "
    "with modest compute, so prefer designs that can be run on a public "
    "dataset with a documented baseline.\n\n"
    "Every design must name the metric that decides the outcome and the "
    "controls that keep the comparison fair. Do not claim results, and do not "
    "invent datasets that do not exist — if unsure, describe the kind of "
    "dataset required instead.\n\n"
    "Return ONLY JSON:\n"
    '{{"experiments": [{{"hypothesis_index": 0,\n'
    '                    "objective": "...",\n'
    '                    "datasets": ["..."],\n'
    '                    "baselines": ["..."],\n'
    '                    "metrics": ["..."],\n'
    '                    "procedure": ["step 1", "step 2"],\n'
    '                    "controls": ["..."],\n'
    '                    "threats_to_validity": ["..."]}}]}}\n\n'
    "Hypotheses:\n{hypotheses}\n"
)

MAX_EXPERIMENTS = 6


def _string_list(value, limit: int, item_chars: int = 240) -> list[str]:
    """Coerce model output into a clean list of non-empty strings."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:item_chars] for item in value if str(item).strip()][:limit]


class ExperimentAgent(BaseAgent):
    """Turn hypotheses into executable experiment protocols."""

    name = "experiment"
    stage = "analyzing"

    # ------------------------------------------------------------------
    @staticmethod
    def _hypothesis_records(ctx: AgentContext) -> list[dict]:
        payload = ctx.intermediate_results.get("hypotheses") or {}
        return [item for item in payload.get("hypotheses", []) if isinstance(item, dict)]

    # ------------------------------------------------------------------
    async def run(self, ctx: AgentContext) -> AgentContext:
        hypotheses = self._hypothesis_records(ctx)

        if not hypotheses:
            ctx.intermediate_results["experiments"] = {
                "experiments": [],
                "note": (
                    "No hypothesis was available, so no experiment was designed. "
                    "Run the hypothesis workflow first — a design exists to test a "
                    "specific claim, not to fill a section."
                ),
            }
            ctx.log(self.name, "No hypotheses on the context — nothing to design for", self.stage)
            return ctx

        ctx.log(
            self.name,
            f"Designing experiments for {len(hypotheses)} hypothesis/es",
            self.stage,
        )

        listing = "\n".join(
            f"HYP{index + 1}: {item.get('statement', '')} "
            f"(prediction: {item.get('testable_prediction', '')})"
            for index, item in enumerate(hypotheses)
        )

        parsed = {}
        if self.llm is not None:
            parsed = extract_json(
                self.invoke_llm(EXPERIMENT_PROMPT.format(hypotheses=listing)), default={}
            )
        if not isinstance(parsed, dict):
            parsed = {}

        experiments: list[dict] = []
        dropped = 0

        for item in parsed.get("experiments", [])[: MAX_EXPERIMENTS * 2]:
            if not isinstance(item, dict):
                continue

            try:
                index = int(item.get("hypothesis_index", -1))
            except (TypeError, ValueError):
                index = -1

            if not 0 <= index < len(hypotheses):
                dropped += 1
                continue

            objective = str(item.get("objective", "")).strip()
            metrics = _string_list(item.get("metrics"), 6)
            procedure = _string_list(item.get("procedure"), 10, 300)

            if not objective or not metrics or not procedure:
                # A design with no metric or no steps decides nothing.
                dropped += 1
                continue

            hypothesis = hypotheses[index]
            experiments.append(
                {
                    "id": f"EXP{len(experiments) + 1}",
                    "hypothesis_id": hypothesis.get("id", f"HYP{index + 1}"),
                    "hypothesis": str(hypothesis.get("statement", ""))[:300],
                    "objective": objective[:400],
                    "datasets": _string_list(item.get("datasets"), 6),
                    "baselines": _string_list(item.get("baselines"), 6),
                    "metrics": metrics,
                    "procedure": procedure,
                    "controls": _string_list(item.get("controls"), 6),
                    "threats_to_validity": _string_list(item.get("threats_to_validity"), 6),
                }
            )
            if len(experiments) >= MAX_EXPERIMENTS:
                break

        result = {"experiments": experiments}
        if dropped:
            result["incomplete_dropped"] = dropped
        if not experiments:
            result["note"] = (
                "No design came back with both a deciding metric and an ordered "
                "procedure, so none is shown."
            )

        ctx.intermediate_results["experiments"] = result
        ctx.log(
            self.name,
            f"{len(experiments)} experiment design(s) produced"
            + (f", {dropped} incomplete dropped" if dropped else ""),
            self.stage,
        )
        return ctx
