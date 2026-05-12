"""Request subclass for cover-letter runs.

Extends ``tailor_core.runs.models.TailorRequest`` with two cover-letter-specific
keys:

- ``resume_run_id`` -- by-ref lookup; orchestrator HTTP-fetches the
  resumeai sibling's ``GET /api/runs/<id>`` to resolve the tailored
  resume payload at execution time.
- ``resume_payload`` -- inline upload; a JSON-encoded ``TailoredResume``
  blob passed straight in. Useful when resumeai isn't running or the
  caller (jobai later) already holds the structured resume.

Exactly one of the two should be supplied; both ``None`` means the agent
runs without a resume to ground in (less ideal -- it will produce a more
generic letter).
"""

from __future__ import annotations

from typing import Self

from pydantic import model_validator
from tailor_core.runs.models import TailorRequest


class CoverLetterRequest(TailorRequest):
    """``TailorRequest`` + the cover-letter inputs.

    ``model_config`` is inherited from ``TailorRequest`` (frozen + extras
    allowed). ``extras="allow"`` is what lets these extra keys survive
    when the instance is stored inside ``Run.request`` (typed as the
    base) and round-tripped through the SQLite store.
    """

    resume_run_id: str | None = None
    resume_payload: str | None = None

    @model_validator(mode="after")
    def _at_most_one_resume_source(self) -> Self:
        has_ref = bool(self.resume_run_id and self.resume_run_id.strip())
        has_payload = bool(self.resume_payload and self.resume_payload.strip())
        if has_ref and has_payload:
            raise ValueError("supply at most one of resume_run_id or resume_payload")
        return self
