"""End-to-end cover-letter tailoring entry point.

Wires the prompt + LLM call + parser into a single function the orchestrator
calls. Retries once on a parse error -- LLMs sometimes emit a fenced or
preamble-prefixed response on the first shot; the second shot is usually
clean.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tailor_core.verifier.deterministic import find_numeric_contradictions

from coverletterai.agent.parser import ParseError, parse_tailored_cover_letter
from coverletterai.agent.prompt import SYSTEM_PROMPT, build_cover_letter_prompt

if TYPE_CHECKING:
    from tailor_core.context.models import UserContext
    from tailor_core.context_files.models import ContextFile
    from tailor_core.jd.models import JobRequirements
    from tailor_core.llm.client import LLMClient
    from tailor_core.verifier.models import VerificationIssue

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
    verified_context: str | None = None,
) -> TailoredCoverLetter:
    """Run one tailoring call.

    Retries once on a parse error. Then, when ``verified_context`` is
    supplied, runs the deterministic numeric-claim check and -- if the
    LLM still fabricated a metric despite the VERIFIED FACTS block in
    the prompt -- re-prompts exactly once with the contradictions
    spelled out inline. Bounded by design: a single deterministic
    correction, never a loop. A residual contradiction is left for the
    verifier + jobai's QA gate to surface (never a silent ship).
    """
    user_prompt = build_cover_letter_prompt(
        requirements, tailored_resume, context, context_files, verified_context=verified_context
    )
    letter = _complete_and_parse(llm, user_prompt, model)
    if verified_context:
        issues = find_numeric_contradictions(_letter_text(letter), verified_context)
        if issues:
            _log.warning(
                "cover-letter numeric contradiction(s) after first pass; re-prompting once: %s",
                "; ".join(i.message for i in issues),
            )
            corrected_prompt = user_prompt + _numeric_correction_block(issues)
            letter = _complete_and_parse(llm, corrected_prompt, model)
    return letter


def _complete_and_parse(llm: LLMClient, user_prompt: str, model: str | None) -> TailoredCoverLetter:
    """One LLM call + parse, retrying once on a parse error."""
    try:
        raw = llm.complete(system=SYSTEM_PROMPT, user=user_prompt, model=model)
        return parse_tailored_cover_letter(raw)
    except ParseError as first_exc:
        _log.warning("cover-letter parse failed on first attempt: %s; retrying once", first_exc)
        raw = llm.complete(system=SYSTEM_PROMPT, user=user_prompt, model=model)
        return parse_tailored_cover_letter(raw)


def _letter_text(letter: TailoredCoverLetter) -> str:
    """Flatten the letter's prose for the deterministic numeric check."""
    return "\n".join(
        (
            letter.title,
            letter.company,
            letter.opening,
            *letter.body_paragraphs,
            letter.closing,
        )
    )


def _numeric_correction_block(issues: tuple[VerificationIssue, ...]) -> str:
    """An inline correction appended to the prompt for the single re-prompt."""
    lines = [
        "",
        "",
        "# NUMERIC CONTRADICTIONS DETECTED IN YOUR LAST DRAFT — YOU MUST FIX THESE",
        "Your previous draft stated figures that contradict the VERIFIED FACTS "
        "above. Regenerate the FULL cover letter JSON. For each item below, use "
        "the verified figure VERBATIM, or state the achievement qualitatively "
        "with no number. Do not introduce any other number not in VERIFIED FACTS.",
    ]
    for issue in issues:
        lines.append(f"- {issue.message} {issue.suggestion}".rstrip())
    return "\n".join(lines)
