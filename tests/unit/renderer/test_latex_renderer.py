"""LaTeX renderer tests -- escape rules, render_tex shape, compile_pdf failure paths."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coverletterai.agent.models import CoverLetterContact, TailoredCoverLetter
from coverletterai.renderer.latex_renderer import (
    RenderError,
    compile_pdf,
    render_tailored_cover_letter_latex,
    render_tex,
    tex_escape,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _letter(**overrides: object) -> TailoredCoverLetter:
    base: dict[str, object] = {
        "name": "Jane Doe",
        "contact": CoverLetterContact(email="jane@example.com", phone="0400 000 000"),
        "company": "Acme",
        "title": "Senior Engineer",
        "salutation": "Dear Hiring Manager,",
        "opening": "Opening paragraph with 50% growth.",
        "body_paragraphs": (
            "First body paragraph mentions $1M revenue.",
            "Second body paragraph with C# and a smart quote: “hello”.",
        ),
        "closing": "Closing paragraph.",
        "signoff": "Sincerely,",
    }
    base.update(overrides)
    return TailoredCoverLetter.model_validate(base)


# -- tex_escape ------------------------------------------------------------


def test_tex_escape_none_returns_empty() -> None:
    assert tex_escape(None) == ""


def test_tex_escape_empty_returns_empty() -> None:
    assert tex_escape("") == ""


def test_tex_escape_ampersand() -> None:
    assert tex_escape("R&D") == r"R\&D"


def test_tex_escape_percent() -> None:
    assert tex_escape("50%") == r"50\%"


def test_tex_escape_dollar() -> None:
    assert tex_escape("$1M") == r"\$1M"


def test_tex_escape_hash() -> None:
    assert tex_escape("C#") == r"C\#"


def test_tex_escape_underscore() -> None:
    assert tex_escape("my_var") == r"my\_var"


def test_tex_escape_braces() -> None:
    assert tex_escape("{x}") == r"\{x\}"


def test_tex_escape_tilde() -> None:
    assert tex_escape("a~b") == r"a\textasciitilde{}b"


def test_tex_escape_caret() -> None:
    assert tex_escape("a^b") == r"a\textasciicircum{}b"


def test_tex_escape_backslash_uses_sentinel() -> None:
    """Backslash -> ``\\textbackslash{}`` without re-escaping the braces."""
    out = tex_escape("a\\b")
    assert "\\textbackslash{}" in out
    # ensure the trailing braces from textbackslash aren't escaped to \{\}
    assert r"\textbackslash\{\}" not in out


def test_tex_escape_smart_quotes() -> None:
    assert tex_escape("“hello”") == "``hello''"


def test_tex_escape_dashes() -> None:
    assert tex_escape("a–b—c") == "a--b---c"


def test_tex_escape_ellipsis() -> None:
    assert tex_escape("done…") == r"done\ldots{}"


def test_tex_escape_degree() -> None:
    assert tex_escape("90°") == r"90\textdegree{}"


# -- render_tex ------------------------------------------------------------


def test_render_tex_emits_name_and_contact() -> None:
    out = render_tex(_letter(), today=datetime(2026, 5, 13, tzinfo=UTC))
    assert "Jane Doe" in out
    assert "jane@example.com" in out
    assert "0400 000 000" in out
    assert "13 May 2026" in out


def test_render_tex_emits_company_and_title() -> None:
    out = render_tex(_letter(), today=datetime(2026, 5, 13, tzinfo=UTC))
    assert "Acme" in out
    assert "Senior Engineer" in out


def test_render_tex_escapes_user_content() -> None:
    out = render_tex(_letter(), today=datetime(2026, 5, 13, tzinfo=UTC))
    assert r"50\%" in out  # ``50%`` in opening became escaped
    assert r"\$1M" in out  # ``$1M`` in body became escaped
    assert r"C\#" in out


def test_render_tex_includes_each_body_paragraph() -> None:
    out = render_tex(_letter(), today=datetime(2026, 5, 13, tzinfo=UTC))
    assert "First body paragraph" in out
    # The C# escape proves the second paragraph also rendered.
    assert r"C\#" in out


def test_render_tex_omits_phone_block_when_phone_missing() -> None:
    letter = _letter(contact=CoverLetterContact(email="jane@example.com"))
    out = render_tex(letter, today=datetime(2026, 5, 13, tzinfo=UTC))
    assert "0400" not in out
    assert "jane@example.com" in out


def test_render_tex_includes_hiring_manager_when_supplied() -> None:
    letter = _letter(hiring_manager="Alex Roe")
    out = render_tex(letter, today=datetime(2026, 5, 13, tzinfo=UTC))
    assert "Alex Roe" in out


def test_render_tex_raises_when_templates_dir_missing(tmp_path: Path) -> None:
    nonexistent = tmp_path / "no-such-dir"
    with pytest.raises(RenderError, match="templates directory"):
        render_tex(_letter(), templates_dir=nonexistent)


def test_render_tex_raises_when_template_file_missing(tmp_path: Path) -> None:
    # Empty templates dir exists but has no .tex.j2 inside.
    (tmp_path / "templates").mkdir()
    with pytest.raises(RenderError, match="template not found"):
        render_tex(_letter(), templates_dir=tmp_path / "templates")


def test_render_tex_uses_now_when_today_is_none() -> None:
    out = render_tex(_letter())
    # We can't assert the exact date, but the year should appear.
    assert str(datetime.now(UTC).year) in out


# -- compile_pdf -----------------------------------------------------------


def test_compile_pdf_raises_when_tectonic_missing(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch("shutil.which", return_value=None)
    with pytest.raises(RenderError, match="tectonic"):
        compile_pdf("\\documentclass{article}", tmp_path)


def test_compile_pdf_raises_on_nonzero_exit(tmp_path: Path, mocker: MockerFixture) -> None:
    import subprocess  # noqa: PLC0415

    mocker.patch("shutil.which", return_value="/usr/local/bin/tectonic")

    def fake_run(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")

    mocker.patch("subprocess.run", side_effect=fake_run)
    with pytest.raises(RenderError, match="tectonic compile failed"):
        compile_pdf("\\documentclass{article}", tmp_path)


def test_compile_pdf_raises_when_pdf_missing_after_zero_exit(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    import subprocess  # noqa: PLC0415

    mocker.patch("shutil.which", return_value="/usr/local/bin/tectonic")

    def fake_run(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        # exit 0 but no PDF written -- tectonic should have made one;
        # surface a clear error instead of returning empty bytes.
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")

    mocker.patch("subprocess.run", side_effect=fake_run)
    with pytest.raises(RenderError, match="missing"):
        compile_pdf("\\documentclass{article}", tmp_path)


# -- render_tailored_cover_letter_latex ------------------------------------


def test_end_to_end_render_emits_pdf_url_and_size(tmp_path: Path, mocker: MockerFixture) -> None:
    """End-to-end render against a stubbed tectonic so the test doesn't need
    the binary installed."""
    import subprocess  # noqa: PLC0415

    mocker.patch("shutil.which", return_value="/usr/local/bin/tectonic")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args
        # Mimic tectonic writing the PDF next to the .tex.
        output_dir = kwargs.get("cwd")
        assert output_dir is not None
        pdf_path = Path(str(output_dir)) / "cover-letter.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    mocker.patch("subprocess.run", side_effect=fake_run)

    result = render_tailored_cover_letter_latex(
        _letter(),
        tmp_path / "run_x",
        today=datetime(2026, 5, 13, tzinfo=UTC),
    )
    assert result.doc_id == "run_x"
    assert result.doc_url.endswith("cover-letter.pdf")
    assert result.doc_url.startswith("file://")
    assert result.pdf_size_bytes == len(b"%PDF-1.4 fake")
    assert len(result.diffs) == 1
    assert result.diffs[0].kind == "cover_letter"
