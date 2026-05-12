"""``CoverLetterRequest`` validation + round-trip."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coverletterai.runs.models import CoverLetterRequest


def test_accepts_jd_text_with_no_resume_source() -> None:
    req = CoverLetterRequest(jd_text="Senior Engineer ...")
    assert req.jd_text == "Senior Engineer ..."
    assert req.resume_run_id is None
    assert req.resume_payload is None


def test_accepts_resume_run_id() -> None:
    req = CoverLetterRequest(jd_text="JD", resume_run_id="run_abc")
    assert req.resume_run_id == "run_abc"


def test_accepts_resume_payload() -> None:
    req = CoverLetterRequest(jd_text="JD", resume_payload='{"name": "Jane"}')
    assert req.resume_payload == '{"name": "Jane"}'


def test_rejects_both_resume_sources() -> None:
    with pytest.raises(ValidationError, match="at most one"):
        CoverLetterRequest(
            jd_text="JD",
            resume_run_id="run_abc",
            resume_payload='{"name": "Jane"}',
        )


def test_rejects_neither_jd_source() -> None:
    """Still inherits the parent's exactly-one-of-jd_url/jd_text rule."""
    with pytest.raises(ValidationError, match="exactly one"):
        CoverLetterRequest(resume_run_id="run_abc")


def test_round_trips_through_json() -> None:
    req = CoverLetterRequest(jd_text="JD", resume_run_id="run_abc", model="claude-sonnet-4-6")
    parsed = CoverLetterRequest.model_validate_json(req.model_dump_json())
    assert parsed == req
