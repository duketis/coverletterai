"""Parser round-trip + error-path tests."""

from __future__ import annotations

import json
from typing import Any

import pytest

from coverletterai.agent.parser import ParseError, parse_tailored_cover_letter

_VALID_PAYLOAD: dict[str, Any] = {
    "name": "Jane Doe",
    "contact": {"email": "jane@example.com"},
    "company": "Acme",
    "title": "Senior Engineer",
    "salutation": "Dear Hiring Manager,",
    "opening": "Hello.",
    "body_paragraphs": ["A paragraph about my experience."],
    "closing": "Thanks.",
    "signoff": "Sincerely,",
}


def test_parses_well_formed_response() -> None:
    letter = parse_tailored_cover_letter(json.dumps(_VALID_PAYLOAD))
    assert letter.name == "Jane Doe"
    assert letter.body_paragraphs == ("A paragraph about my experience.",)


def test_strips_markdown_fences() -> None:
    fenced = f"```json\n{json.dumps(_VALID_PAYLOAD)}\n```"
    letter = parse_tailored_cover_letter(fenced)
    assert letter.name == "Jane Doe"


def test_strips_unlabelled_fence() -> None:
    fenced = f"```\n{json.dumps(_VALID_PAYLOAD)}\n```"
    assert parse_tailored_cover_letter(fenced).company == "Acme"


def test_rejects_empty_response() -> None:
    with pytest.raises(ParseError, match="empty"):
        parse_tailored_cover_letter("")


def test_rejects_whitespace_only_response() -> None:
    with pytest.raises(ParseError, match="empty"):
        parse_tailored_cover_letter("   \n  ")


def test_rejects_invalid_json() -> None:
    with pytest.raises(ParseError, match="not valid JSON"):
        parse_tailored_cover_letter("{not json")


def test_rejects_non_object() -> None:
    with pytest.raises(ParseError, match="not a JSON object"):
        parse_tailored_cover_letter("[1, 2]")


def test_rejects_schema_violation() -> None:
    bad = dict(_VALID_PAYLOAD)
    del bad["name"]
    with pytest.raises(ParseError, match="schema validation"):
        parse_tailored_cover_letter(json.dumps(bad))
