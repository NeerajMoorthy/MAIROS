"""Generation service — grounded answer synthesis and LLM provisioning."""

from .llm import GenerationService
from .provider import get_chat_model, get_fast_model, describe_provider

__all__ = [
    "GenerationService",
    "get_chat_model",
    "get_fast_model",
    "describe_provider",
]
