"""Agent replies cut off at the output token cap are retried once.

Both configured models are gpt-oss reasoning models, which spend part of the
1,400-token default thinking before they answer. Knowledge-graph extraction
showed what that does: the JSON reply ends mid-object, nothing parses, and the
agent reports an empty result without an error. Extraction got its own budget;
these tests cover the shared path every other agent calls.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from services.agents.base import AgentContext, BaseAgent
from services.common.json_utils import extract_json
from services.generation.provider import OfflineChatModel

COMPLETE = '{"gaps": [{"gap": "no ablation of the retriever", "evidence": "c1"}]}'
CUT_OFF = COMPLETE[:30]


class CappedChatModel(BaseChatModel):
    """Cuts its reply off unless the call carries at least ``needs`` tokens."""

    needs: int = 4096
    always_cut: bool = False
    calls: list = []

    @property
    def _llm_type(self) -> str:
        return "capped"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        self.calls.append(kwargs)
        enough = kwargs.get("max_tokens", 0) >= self.needs and not self.always_cut
        message = AIMessage(
            content=COMPLETE if enough else CUT_OFF,
            response_metadata={"finish_reason": "stop" if enough else "length"},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


class EchoAgent(BaseAgent):
    name = "echo"

    async def run(self, ctx: AgentContext) -> AgentContext:  # pragma: no cover
        return ctx


def capped(**kwargs) -> CappedChatModel:
    return CappedChatModel(calls=[], **kwargs)


def test_a_cut_off_reply_is_retried_with_the_larger_budget():
    llm = capped()
    reply = EchoAgent(llm=llm).invoke_llm("find gaps")

    assert reply == COMPLETE
    assert extract_json(reply)["gaps"]
    assert extract_json(CUT_OFF) is None  # what the agent would have parsed
    # The first call used the model's own default; only the retry overrides it.
    assert llm.calls == [{}, {"max_tokens": 4096}]


def test_a_complete_reply_is_not_retried():
    llm = capped(needs=0)
    assert EchoAgent(llm=llm).invoke_llm("find gaps") == COMPLETE
    assert llm.calls == [{}]


def test_the_retry_happens_once_only():
    llm = capped(always_cut=True)
    assert EchoAgent(llm=llm).invoke_llm("find gaps") == CUT_OFF
    assert len(llm.calls) == 2


def test_the_retry_budget_is_configurable(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_retry_max_tokens", 8000)
    llm = capped(needs=8000)
    assert EchoAgent(llm=llm).invoke_llm("find gaps") == COMPLETE
    assert llm.calls[-1] == {"max_tokens": 8000}


def test_the_offline_model_makes_a_single_call():
    # No finish_reason in its replies, so nothing looks cut off.
    reply = EchoAgent(llm=OfflineChatModel()).invoke_llm("plain question")
    assert isinstance(reply, str)


def test_no_model_means_no_call():
    assert EchoAgent(llm=None).invoke_llm("anything") == ""
