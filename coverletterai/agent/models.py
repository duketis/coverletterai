"""Pydantic models for the tailored cover-letter output.

The agent emits a structured object the renderer maps to LaTeX. The shape
is deliberately conservative -- a 1-page cover letter is just an opening,
a few body paragraphs, and a closing. Header (name + contact + date) and
recipient (company + role) come from the resume base + JD respectively;
the agent doesn't need to re-derive them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CoverLetterContact(BaseModel):
    """Sender contact line above the cover letter body."""

    model_config = ConfigDict(frozen=True)

    email: str = Field(min_length=1)
    phone: str | None = None
    location: str | None = None


class TailoredCoverLetter(BaseModel):
    """The agent's structured output. One per run.

    Field-by-field semantics:

    - ``name`` -- candidate's full name (mirrors the resume header).
    - ``contact`` -- email / phone / location (mirrors the resume header).
    - ``company`` -- the hiring company. From the JD.
    - ``title`` -- the role title. From the JD.
    - ``hiring_manager`` -- name if the JD names one; otherwise ``None``
      and the salutation falls back to "Dear Hiring Manager,".
    - ``salutation`` -- the agent-rendered salutation line, eg
      ``"Dear Alex,"`` or ``"Dear Hiring Manager,"``.
    - ``opening`` -- one paragraph: who I am, why this role, why this
      company. Two short sentences ideal.
    - ``body_paragraphs`` -- 1 to 4 paragraphs of the substantive case.
      Each paragraph anchors on the JD's must-haves and cites the
      tailored resume's bullets without contradiction. 2-3 is the
      sweet spot for a one-page letter; 4 is the upper bound.
    - ``closing`` -- one paragraph: call to action + thanks. Short.
    - ``signoff`` -- closing line, eg ``"Sincerely,"`` or ``"Best,"``.

    Single-page LaTeX render: opening + body + closing should fit in
    ~350-450 words on a standard 1-inch-margin page.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    contact: CoverLetterContact
    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    hiring_manager: str | None = None
    salutation: str = Field(default="Dear Hiring Manager,", min_length=1)
    opening: str = Field(min_length=1)
    body_paragraphs: tuple[str, ...] = Field(min_length=1, max_length=4)
    closing: str = Field(min_length=1)
    signoff: str = Field(default="Sincerely,", min_length=1)
