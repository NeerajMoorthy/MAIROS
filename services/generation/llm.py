"""Grounded answer generation — the 'G' in RAG.

The prompt forbids outside knowledge and requires an inline ``[document, p.N]``
marker on every claim, which is what makes the answers auditable in the UI.
"""

from __future__ import annotations

from typing import AsyncGenerator, Iterable

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from services.generation.provider import TASK_SYNTHESIS, get_chat_model

SYSTEM_PROMPT = (
    TASK_SYNTHESIS + "\n"
    "You are MAIROS, a research assistant. Answer the question using ONLY the "
    "numbered CONTEXT passages below.\n"
    "Rules:\n"
    "1. Never use outside knowledge. If the context does not contain the answer, "
    "reply exactly: 'I cannot answer this based on the provided documents.'\n"
    "2. End every sentence that makes a factual claim with its source marker in "
    "square brackets, e.g. [attention.pdf, p. 3].\n"
    "3. If passages disagree, say so explicitly and cite both.\n"
    "4. Be concise — at most one short paragraph plus bullet points.\n\n"
    "CONTEXT:\n{context}"
)


class GenerationService:
    """Generate answers grounded in retrieved chunks."""

    def __init__(self, model_name: str | None = None, llm=None):
        self.llm = llm or get_chat_model(model=model_name)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", SYSTEM_PROMPT), ("human", "{question}")]
        )
        self.chain = self.prompt | self.llm | StrOutputParser()

    # ------------------------------------------------------------------
    @staticmethod
    def format_context(chunks: Iterable) -> str:
        """Render retrieved chunks into numbered, citable source blocks."""
        formatted: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            doc_name = getattr(chunk, "document_name", None) or "Unknown Document"
            page = getattr(chunk, "page", None)
            page_info = f", p. {page}" if page and page > 0 else ""
            formatted.append(
                f"--- SOURCE {i} [{doc_name}{page_info}] ---\n{getattr(chunk, 'text', '')}"
            )
        return "\n\n".join(formatted)

    # Backwards-compatible alias
    _format_context = format_context

    # ------------------------------------------------------------------
    async def generate(self, question: str, chunks: list) -> str:
        """Return a complete grounded answer as a single string."""
        if not chunks:
            return "I cannot answer this based on the provided documents."
        return await self.chain.ainvoke(
            {"context": self.format_context(chunks), "question": question}
        )

    async def generate_stream(
        self, question: str, chunks: list
    ) -> AsyncGenerator[str, None]:
        """Stream the grounded answer token by token."""
        if not chunks:
            yield "I cannot answer this based on the provided documents."
            return

        context = self.format_context(chunks)
        async for token in self.chain.astream(
            {"context": context, "question": question}
        ):
            yield token
