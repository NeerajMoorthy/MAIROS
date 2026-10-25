"""Tolerant JSON parsing for LLM output.

LLMs wrap JSON in prose, markdown fences, or trailing commentary. Every agent
in MAIROS goes through :func:`extract_json` rather than calling ``json.loads``
directly, so a chatty model never takes down the pipeline.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def _balanced_slice(text: str, open_ch: str, close_ch: str) -> str | None:
    """Return the first balanced ``open_ch``…``close_ch`` span in *text*."""
    start = text.find(open_ch)
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def extract_json(text: str, default: Any = None) -> Any:
    """Parse the first JSON value found in *text*.

    Handles raw JSON, ```json fenced blocks, and JSON embedded in prose.
    Returns *default* (``None`` unless given) when nothing parses.
    """
    if text is None:
        return default

    if not isinstance(text, str):
        # Already a parsed structure (e.g. a tool-calling model).
        return text

    candidates: list[str] = []

    stripped = text.strip()
    if stripped:
        candidates.append(stripped)

    for match in _FENCE_RE.findall(text):
        cleaned = match.strip()
        if cleaned:
            candidates.append(cleaned)

    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        span = _balanced_slice(text, open_ch, close_ch)
        if span:
            candidates.append(span)

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue

    return default


def as_text(response: Any) -> str:
    """Normalise a LangChain message / string / object into plain text."""
    if response is None:
        return ""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Multi-part content blocks (e.g. [{"type": "text", "text": "..."}])
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)
