"""Document Analysis Agent — contributions, methodology, and summary."""

from __future__ import annotations

from services.common.json_utils import extract_json
from services.generation.provider import TASK_ANALYSIS

from .base import AgentContext, BaseAgent

ANALYSIS_PROMPT = (
    TASK_ANALYSIS + "\n"
    "You are analysing a research paper. Read the text and extract its key "
    "contributions, its methodology, and a concise summary.\n\n"
    "Return ONLY JSON in exactly this shape:\n"
    '{{"contributions": ["...", "..."],\n'
    ' "methodology": "2-3 sentences on how the work was done",\n'
    ' "summary": "4-6 sentence summary of the whole paper",\n'
    ' "key_concepts": ["...", "..."],\n'
    ' "limitations": ["..."]}}\n\n'
    "Ground every statement in the text. If something is not stated, write "
    '"Not stated in the provided text." rather than guessing.\n\n'
    "Paper Text:\n{text}\n"
)


class AnalysisAgent(BaseAgent):
    """Extract structured findings from a paper."""

    name = "analysis"
    stage = "analyzing"

    async def run(self, ctx: AgentContext) -> AgentContext:
        ctx.log(self.name, "Analysing document text", self.stage)

        text = ctx.context_text(limit=14000)
        if not text.strip():
            ctx.log(self.name, "No document text available to analyse", self.stage, "failed")
            return ctx

        if self.llm is None:
            ctx.log(self.name, "No LLM configured", self.stage, "failed")
            return ctx

        raw = self.invoke_llm(ANALYSIS_PROMPT.format(text=text))
        data = extract_json(raw, default=None)

        if not isinstance(data, dict):
            # Model ignored the schema — keep the prose rather than losing it.
            data = {
                "contributions": [],
                "methodology": "",
                "summary": raw.strip()[:1500],
                "key_concepts": [],
                "limitations": [],
                "unstructured": True,
            }

        data.setdefault("contributions", [])
        data.setdefault("key_concepts", [])
        data.setdefault("limitations", [])
        data.setdefault("methodology", "")
        data.setdefault("summary", "")

        if isinstance(data["contributions"], str):
            data["contributions"] = [data["contributions"]]

        doc_names = sorted(
            {c.get("document_name", "") for c in ctx.retrieved_chunks if c.get("document_name")}
        )
        data["documents"] = doc_names

        ctx.intermediate_results["analysis"] = data
        ctx.log(
            self.name,
            f"Extracted {len(data['contributions'])} contributions and "
            f"{len(data['key_concepts'])} key concepts",
            self.stage,
        )
        return ctx
