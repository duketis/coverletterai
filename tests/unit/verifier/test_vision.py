"""Cover-letter vision verifier -- thin wrapper over the lib's run_vision_verification."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from coverletterai.verifier.vision import (
    DEFAULT_VISION_DPI,
    DEFAULT_VISION_MAX_TOKENS,
    DEFAULT_VISION_MODEL,
    SYSTEM_PROMPT,
    verify_pdf_visually,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_system_prompt_documents_required_schema_fields() -> None:
    for field in ('"status"', '"issues"', '"severity"', '"category"', '"message"'):
        assert field in SYSTEM_PROMPT


def test_system_prompt_calls_out_one_page_target() -> None:
    """Layout pass insists on ONE page; anything else is a failed letter."""
    assert "ONE page" in SYSTEM_PROMPT


def test_system_prompt_calls_out_layout_concerns() -> None:
    """Each rubric line the prompt should mention."""
    assert "Header alignment" in SYSTEM_PROMPT
    assert "Signoff position" in SYSTEM_PROMPT
    assert "Right-margin overflow" in SYSTEM_PROMPT


def test_verify_pdf_visually_delegates_to_lib(tmp_path: Path, mocker: MockerFixture) -> None:
    """The wrapper just forwards the call to ``run_vision_verification``
    with the cover-letter ``SYSTEM_PROMPT`` + user prompt."""
    pdf = tmp_path / "x.pdf"
    pdf.touch()
    spy = mocker.patch("coverletterai.verifier.vision.run_vision_verification", return_value=None)
    result = verify_pdf_visually(pdf, oauth_token="sk-ant-oat01-fake")
    assert result is None
    spy.assert_called_once()
    kwargs = spy.call_args.kwargs
    assert kwargs["system_prompt"] == SYSTEM_PROMPT
    assert "rendered pages" in kwargs["user_prompt"]
    assert kwargs["oauth_token"] == "sk-ant-oat01-fake"
    assert kwargs["model"] == DEFAULT_VISION_MODEL
    assert kwargs["dpi"] == DEFAULT_VISION_DPI
    assert kwargs["max_tokens"] == DEFAULT_VISION_MAX_TOKENS


def test_verify_pdf_visually_forwards_model_override(tmp_path: Path, mocker: MockerFixture) -> None:
    pdf = tmp_path / "x.pdf"
    pdf.touch()
    spy = mocker.patch("coverletterai.verifier.vision.run_vision_verification", return_value=None)
    verify_pdf_visually(pdf, oauth_token="sk-ant-oat01-fake", model="claude-haiku-4-5")
    assert spy.call_args.kwargs["model"] == "claude-haiku-4-5"
