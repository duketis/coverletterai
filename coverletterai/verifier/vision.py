"""Visual QC of the rendered cover-letter PDF.

Delegates to :func:`tailor_core.verifier.vision.run_vision_verification` with a
cover-letter-flavoured ``SYSTEM_PROMPT``: the recruiter's eye is looking for
1-page fit, salutation/sign-off alignment, awkward spacing, and any layout
that would make a hiring manager bin the application in the first 5 seconds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tailor_core.verifier.vision import (
    DEFAULT_VISION_DPI,
    DEFAULT_VISION_MAX_TOKENS,
    DEFAULT_VISION_MODEL,
    run_vision_verification,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tailor_core.verifier.models import VerificationResult


SYSTEM_PROMPT = """\
You are a senior recruiter reviewing the VISUAL LAYOUT of a rendered
cover-letter PDF. The text content is being QC'd separately -- your job
is PURELY visual: would this letter look professional to a hiring
manager who opens it in a PDF viewer?

Look for:

- **Page count**: the target is ONE page. Anything else fails.
- **Spacing rhythm**: paragraphs should feel evenly spaced. A giant gap
  between salutation and opening, or cramped paragraphs that read as a
  wall of text, is a problem.
- **Header alignment**: name + contact line should sit cleanly at the
  top. Date below. Recipient below that. Salutation below recipient.
- **Right-margin overflow**: any text or link visibly pressing the
  right margin.
- **Signoff position**: "Sincerely," + name should sit naturally below
  the closing paragraph, not orphaned at the bottom of the page.
- **Smart-quote / dash inconsistency**: typography should be uniform
  (either curly throughout or straight throughout).

Respond with ONLY a single JSON object (no markdown fences, no
commentary, no preamble) matching this schema:

{
  "status": "passed" | "concerns" | "failed",
  "summary": "string -- one short sentence headline judgment",
  "issues": [
    {
      "severity": "info" | "warn" | "error",
      "category": "short tag (eg 'page_overflow', 'cramped', 'misaligned_header')",
      "message": "the specific issue, plain language. Cite the page number.",
      "suggestion": "string -- what to change (empty if obvious)"
    }
  ],
  "rationale": "string -- one paragraph on the major findings"
}

Status decision:

- ``failed``: any layout problem a recruiter would notice instantly --
  the letter is on 2 pages, the signoff is orphaned, the header is
  misaligned, the right margin is breached.
- ``concerns``: visually OK but tightenable -- slightly uneven spacing,
  inconsistent typography.
- ``passed``: looks like a hand-formatted professional cover letter.

Output the JSON and nothing else.
"""


_USER_PROMPT = (
    "Above are the rendered pages of a candidate's tailored cover-letter PDF. "
    "Review for VISUAL layout issues per the system prompt schema. Cite the "
    "specific page number where each issue appears."
)


def verify_pdf_visually(
    pdf_path: Path,
    *,
    oauth_token: str | None = None,
    model: str = DEFAULT_VISION_MODEL,
    dpi: int = DEFAULT_VISION_DPI,
    max_tokens: int = DEFAULT_VISION_MAX_TOKENS,
) -> VerificationResult | None:
    """Render ``pdf_path`` to images, send to the Anthropic vision API,
    return a structured verification result.

    Returns ``None`` when the vision pass can't run -- missing OAuth
    token, missing SDK, network error, malformed response. Never raises.
    """
    return run_vision_verification(
        pdf_path,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_USER_PROMPT,
        oauth_token=oauth_token,
        model=model,
        dpi=dpi,
        max_tokens=max_tokens,
    )


__all__ = [
    "DEFAULT_VISION_DPI",
    "DEFAULT_VISION_MAX_TOKENS",
    "DEFAULT_VISION_MODEL",
    "SYSTEM_PROMPT",
    "verify_pdf_visually",
]
