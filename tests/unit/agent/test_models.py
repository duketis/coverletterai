"""Validation + round-trip tests for ``TailoredCoverLetter``."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coverletterai.agent.models import CoverLetterContact, TailoredCoverLetter


def _letter(**overrides: object) -> TailoredCoverLetter:
    base: dict[str, object] = {
        "name": "Jane Doe",
        "contact": CoverLetterContact(email="jane@example.com", phone="0400 000 000"),
        "company": "Acme",
        "title": "Senior Engineer",
        "opening": "I'm writing to ...",
        "body_paragraphs": ("My most relevant experience ...",),
        "closing": "I'd welcome a conversation ...",
    }
    base.update(overrides)
    return TailoredCoverLetter.model_validate(base)


def test_round_trips_through_json() -> None:
    letter = _letter(body_paragraphs=("p1", "p2"))
    assert TailoredCoverLetter.model_validate_json(letter.model_dump_json()) == letter


def test_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        _letter(name="")


def test_rejects_empty_opening() -> None:
    with pytest.raises(ValidationError):
        _letter(opening="")


def test_rejects_zero_body_paragraphs() -> None:
    with pytest.raises(ValidationError):
        _letter(body_paragraphs=())


def test_rejects_more_than_two_body_paragraphs() -> None:
    """Three+ body paragraphs guarantees a >1-page render; the schema
    rejects so the LLM client's retry mechanism kicks in and the model
    re-emits a tighter letter."""
    with pytest.raises(ValidationError):
        _letter(body_paragraphs=("a", "b", "c"))


def test_defaults_apply_when_omitted() -> None:
    letter = _letter()
    assert letter.salutation == "Dear Hiring Manager,"
    assert letter.signoff == "Sincerely,"
    assert letter.hiring_manager is None


def test_contact_round_trips() -> None:
    contact = CoverLetterContact(email="x@y.com", phone="0400", location="Melbourne")
    assert CoverLetterContact.model_validate_json(contact.model_dump_json()) == contact


def test_contact_rejects_empty_email() -> None:
    with pytest.raises(ValidationError):
        CoverLetterContact(email="")
