"""End-to-end tailor entry tests using ``FakeLLMClient``."""

from __future__ import annotations

import json

import pytest
from tailor_core.context.models import Contact, ResumeBase, UserContext
from tailor_core.jd.models import JobRequirements, RoleType, Seniority
from tailor_core.llm.client import FakeLLMClient

from coverletterai.agent.parser import ParseError
from coverletterai.agent.tailor import tailor_cover_letter

_VALID_RESPONSE = json.dumps(
    {
        "name": "Jane",
        "contact": {"email": "jane@example.com"},
        "company": "Acme",
        "title": "Senior Engineer",
        "salutation": "Dear Hiring Manager,",
        "opening": "Hello.",
        "body_paragraphs": ["Body."],
        "closing": "Thanks.",
        "signoff": "Sincerely,",
    }
)


def _jd() -> JobRequirements:
    return JobRequirements(
        title="Senior Engineer",
        company="Acme",
        role_type=RoleType.ENGINEERING,
        seniority=Seniority.SENIOR,
    )


def _context() -> UserContext:
    return UserContext(resume=ResumeBase(name="Jane", contact=Contact(email="jane@example.com")))


def test_tailor_returns_parsed_letter_on_first_attempt() -> None:
    llm = FakeLLMClient(default_response=_VALID_RESPONSE)
    letter = tailor_cover_letter(_jd(), None, _context(), llm)
    assert letter.name == "Jane"
    assert len(llm.calls) == 1


def test_tailor_retries_on_first_parse_error() -> None:
    # First call returns garbage, second returns valid. We mimic that by
    # supplying a ``responses`` map keyed on the user-prompt and falling
    # back to a counter via a custom client.

    class _Flaky:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, *, system: str, user: str, model: str | None = None) -> str:
            del system, user, model
            self.calls += 1
            if self.calls == 1:
                return "not valid json garbage"
            return _VALID_RESPONSE

    flaky = _Flaky()
    letter = tailor_cover_letter(_jd(), None, _context(), flaky)
    assert letter.name == "Jane"
    assert flaky.calls == 2


def test_tailor_propagates_second_parse_failure() -> None:
    """Two consecutive bad responses surface the error -- no infinite retry."""
    llm = FakeLLMClient(default_response="still not valid")
    with pytest.raises(ParseError):
        tailor_cover_letter(_jd(), None, _context(), llm)


def test_tailor_forwards_model_override() -> None:
    llm = FakeLLMClient(default_response=_VALID_RESPONSE)
    tailor_cover_letter(_jd(), None, _context(), llm, model="claude-sonnet-4-6")
    assert llm.calls[0][2] == "claude-sonnet-4-6"
