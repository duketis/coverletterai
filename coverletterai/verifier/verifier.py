"""Text-mode verifier: review a tailored cover letter against the JD + resume.

The verifier's checklist:

- Does the letter reference at least one concrete bullet from the tailored
  resume?
- Does the letter contradict any resume bullet (eg "led a team of 15" when
  the resume says 5)?
- Does the letter address the JD's must-haves directly?
- Is the tone professional + free of clichés ("passionate about", "I am
  writing to apply")?
- Does it fit on one page (programmatic page-count check post-render)?

The output is a structured :class:`VerificationResult` the run-detail page
surfaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tailor_core.verifier.scaffold import (
    VerifierError,
    check_pdf_length,
    evaluate_judgement,
    fallback_concerns_result,
    merge_issue,
    parse_verifier_response,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tailor_core.jd.models import JobRequirements
    from tailor_core.llm.client import LLMClient
    from tailor_core.verifier.models import VerificationResult

    from coverletterai.agent.models import TailoredCoverLetter


__all__ = [
    "SYSTEM_PROMPT",
    "TARGET_MAX_PAGES",
    "VerifierError",
    "build_verifier_prompt",
    "fallback_concerns_result",
    "parse_verifier_response",
    "verify_cover_letter",
]


SYSTEM_PROMPT = """\
You are reviewing a TAILORED COVER LETTER against a JOB DESCRIPTION and a
TAILORED RESUME on behalf of the candidate. Your job is QC: catch
fabrications, contradictions with the resume, missing JD must-haves,
clichés, length problems -- anything that would embarrass the candidate
or hurt their chances.

Respond with ONLY a single JSON object (no markdown fences, no commentary,
no preamble) matching this exact schema:

{
  "status": "passed" | "concerns" | "failed",
  "summary": "string -- one short sentence explaining the headline judgment",
  "issues": [
    {
      "severity": "info" | "warn" | "error",
      "category": "string -- short tag (eg 'fabrication', 'resume_contradiction', 'cliche')",
      "message": "string -- the specific issue, in plain language",
      "suggestion": "string -- what to change (empty if obvious)"
    }
  ],
  "rationale": "string -- one paragraph on the major findings"
}

Status decision:

- ``failed``: any ``error``-severity issue. Things like a fabricated
  employer / metric / project; a claim that directly contradicts a
  resume bullet (eg different team size, different scope); the letter
  saying the candidate has a JD must-have skill they clearly don't.
- ``concerns``: ``warn``-severity issues only. Worth flagging, not
  blocking -- eg a cliche opening ("I am writing to express my
  interest"), a body paragraph that's too generic, a body paragraph
  that doesn't echo any resume bullet.
- ``passed``: no issues, or only ``info``-severity nice-to-haves.

Hard rules:

1. If the cover letter mentions a number, customer, project, or skill
   that doesn't appear in the resume OR in the supplied user context,
   that's a fabrication -- ``error`` severity.

2. If the cover letter contradicts a resume bullet -- promotes scope
   ("led a team of 5" -> "led a team of 15"), changes a timeline,
   invents metrics not in the bullet -- that's ``error`` severity.

3. If a body paragraph doesn't ground itself in any resume bullet
   (paraphrased), that's ``warn`` severity.

4. If the opening uses a cliche ("I am writing to apply", "I am
   passionate about", "I would welcome the opportunity to"), that's
   ``warn`` severity.

5. Never invent issues. If everything looks fine, return
   ``status=passed`` with an empty issues list.

6. Output the JSON object and nothing else.
"""


TARGET_MAX_PAGES = 1

_OVERFLOW_SUGGESTION = (
    "Trim one body paragraph or shorten the opening. Cover letters must fit on a single page."
)


def verify_cover_letter(
    jd: JobRequirements,
    tailored: TailoredCoverLetter,
    tailored_resume: dict[str, object] | None,
    llm: LLMClient,
    *,
    model: str | None = None,
    pdf_path: Path | None = None,
) -> VerificationResult:
    """Run the QC pass and return a structured :class:`VerificationResult`.

    When ``pdf_path`` is provided we additionally count pages with
    ``pypdf`` and append a programmatic length-check issue if the
    rendered output exceeds :data:`TARGET_MAX_PAGES` (=1).
    """
    user_prompt = build_verifier_prompt(jd, tailored, tailored_resume)
    result = evaluate_judgement(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        llm=llm,
        model=model,
    )
    if pdf_path is not None:
        length_issue = check_pdf_length(
            pdf_path,
            target_max_pages=TARGET_MAX_PAGES,
            overflow_suggestion=_OVERFLOW_SUGGESTION,
        )
        if length_issue is not None:
            result = merge_issue(result, length_issue)
    return result


def build_verifier_prompt(
    jd: JobRequirements,
    tailored: TailoredCoverLetter,
    tailored_resume: dict[str, object] | None,
) -> str:
    """Compose the user-prompt that pairs the JD + resume + cover letter."""
    sections: list[str] = [
        "# JOB DESCRIPTION",
        jd.model_dump_json(indent=2),
    ]
    if tailored_resume is not None:
        import json  # noqa: PLC0415

        sections.extend(
            [
                "",
                "# TAILORED RESUME (the bullets the cover letter must align with)",
                json.dumps(tailored_resume, indent=2, default=str),
            ]
        )
    sections.extend(
        [
            "",
            "# TAILORED COVER LETTER (the agent's output to review)",
            tailored.model_dump_json(indent=2),
            "",
            "# OUTPUT",
            "Return the verification JSON per the schema in the system prompt.",
        ]
    )
    return "\n".join(sections)
