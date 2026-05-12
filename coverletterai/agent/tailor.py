"""End-to-end cover-letter tailoring entry point.

Wires the prompt + LLM call + parser into a single function the orchestrator
calls. Retries once on a parse error -- LLMs sometimes emit a fenced or
preamble-prefixed response on the first shot; the second shot is usually
clean.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from coverletterai.agent.parser import ParseError, parse_tailored_cover_letter
from coverletterai.agent.prompt import SYSTEM_PROMPT, build_cover_letter_prompt

if TYPE_CHECKING:
    from tailor_core.context.models import UserContext
    from tailor_core.context_files.models import ContextFile
    from tailor_core.jd.models import JobRequirements
    from tailor_core.llm.client import LLMClient

    from coverletterai.agent.models import TailoredCoverLetter

_log = logging.getLogger(__name__)


def tailor_cover_letter(
    requirements: JobRequirements,
    tailored_resume: dict[str, object] | None,
    context: UserContext,
    llm: LLMClient,
    *,
    model: str | None = None,
    context_files: tuple[ContextFile, ...] = (),
) -> TailoredCoverLetter:
    """Run one tailoring call. Retries once on a parse error."""
    user_prompt = build_cover_letter_prompt(requirements, tailored_resume, context, context_files)
    try:
        raw = llm.complete(system=SYSTEM_PROMPT, user=user_prompt, model=model)
        return parse_tailored_cover_letter(raw)
    except ParseError as first_exc:
        _log.warning("cover-letter parse failed on first attempt: %s; retrying once", first_exc)
        raw = llm.complete(system=SYSTEM_PROMPT, user=user_prompt, model=model)
        return parse_tailored_cover_letter(raw)
