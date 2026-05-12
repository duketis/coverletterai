"""Decode the LLM's text response into a ``TailoredCoverLetter``.

The agent should return a bare JSON object per the system prompt. We tolerate
optional Markdown fences (a model occasionally emits them despite the
instructions) and surface a clear ``ParseError`` when the schema doesn't
match so the orchestrator can retry once.
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from coverletterai.agent.models import TailoredCoverLetter

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


class ParseError(RuntimeError):
    """Raised when the LLM response can't be parsed into a ``TailoredCoverLetter``."""


def parse_tailored_cover_letter(raw: str) -> TailoredCoverLetter:
    """Parse the LLM's text response into a :class:`TailoredCoverLetter`.

    Strips an optional Markdown fence, decodes the JSON, and validates
    against the pydantic schema. Raises :class:`ParseError` on any
    failure.
    """
    text = raw.strip()
    if not text:
        raise ParseError("cover-letter response was empty")
    payload = _FENCE_RE.sub(r"\1", text).strip()
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ParseError(
            f"cover-letter response was not valid JSON: {exc.msg} — got {payload[:200]!r}"
        ) from exc
    if not isinstance(data, dict):
        raise ParseError(f"cover-letter response was not a JSON object — got {type(data).__name__}")
    try:
        return TailoredCoverLetter.model_validate(data)
    except ValidationError as exc:
        raise ParseError(f"cover-letter response failed schema validation: {exc}") from exc
