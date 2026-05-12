"""Cover-letter agent prompts.

The system prompt sets the rubric: tone, length, grounding rules. The user
prompt stitches the JD requirements + tailored resume + user-context tree
into one self-contained brief the LLM can act on without follow-up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tailor_core.context.models import UserContext
    from tailor_core.context_files.models import ContextFile
    from tailor_core.jd.models import JobRequirements


SYSTEM_PROMPT = """\
You are writing a TAILORED COVER LETTER for a candidate's job application.

Your output is a SINGLE JSON object matching the schema below -- no
markdown fences, no commentary, no preamble. The cover letter must fit on
ONE printed page when rendered to LaTeX with 1-inch margins (target
350-450 words across opening + body + closing).

Schema:

{
  "name": "string -- candidate's full name (copy from resume header)",
  "contact": {
    "email": "string -- copy from resume header",
    "phone": "string | null -- copy from resume header",
    "location": "string | null -- city/region, copy from resume header"
  },
  "company": "string -- the hiring company (copy from JD)",
  "title": "string -- the role title (copy from JD)",
  "hiring_manager": "string | null -- include only if the JD names a specific person",
  "salutation": "string -- 'Dear <Name>,' if hiring_manager known else 'Dear Hiring Manager,'",
  "opening": "string -- one paragraph (2-3 sentences) introducing the candidate. Concrete hook.",
  "body_paragraphs": [
    "string -- one paragraph (3-5 sentences) per substantive theme. 1 to 3 paragraphs."
  ],
  "closing": "string -- one paragraph (2-3 sentences) with a call to action + thanks.",
  "signoff": "string -- 'Sincerely,' or 'Best,' or similar"
}

HARD RULES:

1. NEVER FABRICATE. Every employer, customer, project, metric, or skill
   mentioned must appear somewhere in:
   - the TAILORED RESUME (the resume the candidate is sending with this
     letter), OR
   - the USER CONTEXT (resume.yaml, work_history/*.md, projects/*.md,
     git_audit/*.md, prior cover_letters/*.md).

   If the JD asks for something the candidate doesn't have, acknowledge
   transferability honestly rather than claiming the skill directly.

2. NEVER CONTRADICT THE TAILORED RESUME. The resume bullets are the
   source of truth for what the candidate did. Don't promote a bullet
   ("led a team of 5") into a stronger claim ("led a team of 15"); don't
   invent metrics not present in the bullets; don't reorder a career
   timeline.

3. GROUND THE BODY PARAGRAPHS IN SPECIFIC RESUME BULLETS. Each body
   paragraph should echo at least one concrete bullet (paraphrased, not
   verbatim). The verifier will fail you if a paragraph reads as generic
   filler.

4. ONE PAGE. The output renders to a 1-inch-margin 11pt LaTeX letter.
   Total content (opening + body + closing) should fit in 350-450 words.
   Aim for the lower end if you're uncertain.

5. NO CLICHES. "I am writing to apply" / "I would welcome the
   opportunity" / "passionate about" -- avoid stale openings. Lead with
   a concrete hook (a specific project, a specific responsibility from
   the JD, etc.).

6. NO TECH-STACK SLASH LISTS in body paragraphs. The resume already
   carries those. The letter is for context the resume can't give: why
   you want THIS role at THIS company, not a generic "I know Python".

7. PROSE, NOT BULLET POINTS. Body paragraphs are paragraphs.

8. OUTPUT ONLY THE JSON OBJECT. No fences, no surrounding prose.
"""


def build_cover_letter_prompt(
    requirements: JobRequirements,
    tailored_resume: dict[str, object] | None,
    context: UserContext,
    context_files: tuple[ContextFile, ...] = (),
) -> str:
    """Compose the user-prompt for one tailoring call.

    ``tailored_resume`` is the model_dump() of the resumeai ``TailoredResume``
    output -- we pass it as a dict rather than importing the resumeai class
    so coverletterai doesn't take a hard runtime dep on resumeai. ``None``
    means no resume was supplied; the agent has to work from user context
    alone (less ideal; will produce a more generic letter).
    """
    sections: list[str] = ["# JOB DESCRIPTION", requirements.model_dump_json(indent=2)]

    if tailored_resume is not None:
        sections.extend(
            [
                "",
                "# TAILORED RESUME (the agent's previous output; the letter must align with this)",
                _dumps_dict(tailored_resume),
            ]
        )

    sections.extend(["", "# USER CONTEXT", _render_user_context(context)])

    if context_files:
        sections.append("")
        sections.append("# SUPPLEMENTARY DOCUMENTS")
        for f in context_files:
            sections.append(f"## {f.name} ({f.kind.value})")
            sections.append(f.extracted_text)

    sections.append("")
    sections.append("# OUTPUT")
    sections.append("Return the cover letter JSON per the system prompt's schema.")
    return "\n".join(sections)


def _dumps_dict(data: dict[str, object]) -> str:
    """JSON-dump a dict with stable indentation."""
    import json  # noqa: PLC0415

    return json.dumps(data, indent=2, default=str)


def _format_dates(start: str | None, end: str | None) -> str:
    """Render a work-history date range. Falls back to the present tense
    when ``end`` is absent (current role)."""
    if start and end:
        return f"{start} – {end}"
    if start:
        return f"{start} – present"
    return "dates unknown"


def _render_user_context(context: UserContext) -> str:
    """Flatten the loaded ``UserContext`` into a readable text block.

    The agent only needs enough to recognise + verify resume claims; the
    full corpus would blow past the prompt budget. We include
    resume-base + a compact list of work-history headings + a compact
    list of project headings. The cover_letters tree is intentionally
    excluded (old Opus-4.6 outputs we don't want to anchor on).
    """
    parts: list[str] = []
    if context.resume is not None:
        parts.append("## resume.yaml")
        parts.append(context.resume.model_dump_json(indent=2))

    if context.work_history:
        parts.append("\n## work_history headings")
        for entry in context.work_history:
            dates = _format_dates(entry.start, entry.end)
            parts.append(f"- {entry.company} ({entry.title}, {dates})")

    if context.projects:
        parts.append("\n## projects headings")
        for project in context.projects:
            parts.append(f"- {project.name}: {project.summary}")

    if context.git_audit:
        parts.append("\n## git_audit (commit topics across engagements)")
        for audit in context.git_audit:
            parts.append(f"- {audit.repo} ({audit.role or 'engineer'})")

    return "\n".join(parts) if parts else "(no user context loaded)"
