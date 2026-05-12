"""LaTeX renderer: TailoredCoverLetter -> .tex -> tectonic -> PDF.

Same shape as resumeai's renderer. Renders the full cover letter from
scratch on every run -- LaTeX decouples layout from content length, so
adding or removing a sentence cannot break formatting.

Three pure-function entry points:

- :func:`render_tex`     -- TailoredCoverLetter + template -> .tex string
- :func:`compile_pdf`    -- .tex string + output dir -> PDF bytes on disk
- :func:`render_tailored_cover_letter_latex` -- end-to-end orchestrator entry
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jinja2
from tailor_core.runs.models import RenderDiff, RenderResult, RenderStatus

if TYPE_CHECKING:
    from coverletterai.agent.models import TailoredCoverLetter


class RenderError(RuntimeError):
    """Raised when the render pipeline can't proceed (eg ``tectonic`` missing)."""


DEFAULT_TEMPLATES_DIR: Path = Path(__file__).parent / "templates"
DEFAULT_TEMPLATE_NAME: str = "default.tex.j2"

# Escapes that don't introduce LaTeX control sequences -- safe to apply
# in order. Backslash gets a sentinel pass first so the ``{`` / ``}`` rules
# don't re-escape the braces of ``\textbackslash{}``.
_LATEX_SIMPLE_ESCAPES: tuple[tuple[str, str], ...] = (
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
)
_BACKSLASH_SENTINEL = "\x00COVERLETTERAIBSLASH\x00"

_LATEX_UNICODE_MAP: tuple[tuple[str, str], ...] = (
    # Dashes
    ("–", "--"),
    ("—", "---"),
    # Ellipsis / bullet
    ("…", r"\ldots{}"),
    # Math relations (rare in cover letters but the user-supplied
    # ResumeBase / WorkHistory body can leak them in)
    ("≤", r"$\leq$"),
    ("≥", r"$\geq$"),
    ("≠", r"$\neq$"),
    ("±", r"$\pm$"),
    ("×", r"$\times$"),
    ("÷", r"$\div$"),
    ("°", r"\textdegree{}"),
    ("©", r"\textcopyright{}"),
    ("®", r"\textregistered{}"),
    ("™", r"\texttrademark{}"),
    # Smart quotes
    ("“", "``"),
    ("”", "''"),
    ("‘", "`"),
    ("’", "'"),
)


def tex_escape(text: str | None) -> str:
    """Escape LaTeX special characters in plain user text. ``None`` -> ``""``.

    The escape is single-pass safe: backslash is rewritten to a sentinel
    first so the subsequent ``{`` and ``}`` rules can't re-escape the
    braces of the ``\\textbackslash{}`` replacement. The typographic
    Unicode pass runs last so its inserted LaTeX commands aren't
    re-escaped.
    """
    if not text:
        return ""
    out = text.replace("\\", _BACKSLASH_SENTINEL)
    for char, replacement in _LATEX_SIMPLE_ESCAPES:
        out = out.replace(char, replacement)
    out = out.replace(_BACKSLASH_SENTINEL, r"\textbackslash{}")
    for char, replacement in _LATEX_UNICODE_MAP:
        out = out.replace(char, replacement)
    return out


def render_tex(
    tailored: TailoredCoverLetter,
    *,
    template_name: str = DEFAULT_TEMPLATE_NAME,
    templates_dir: Path | None = None,
    today: datetime | None = None,
) -> str:
    """Render a :class:`TailoredCoverLetter` into a ``.tex`` string."""
    directory = templates_dir or DEFAULT_TEMPLATES_DIR
    if not directory.exists():
        raise RenderError(f"templates directory not found: {directory}")
    env = _build_env(directory)
    try:
        template = env.get_template(template_name)
    except jinja2.TemplateNotFound as exc:
        raise RenderError(f"template not found: {template_name}") from exc
    return template.render(letter=_escape_letter(tailored, today=today))


def compile_pdf(
    tex_content: str,
    output_dir: Path,
    *,
    stem: str = "cover-letter",
) -> bytes:
    """Write ``tex_content`` and compile it via tectonic. Returns PDF bytes."""
    tectonic = shutil.which("tectonic")
    if tectonic is None:
        raise RenderError("tectonic not found on PATH. Install with `brew install tectonic`.")
    output_dir.mkdir(parents=True, exist_ok=True)
    tex_path = output_dir / f"{stem}.tex"
    pdf_path = output_dir / f"{stem}.pdf"
    tex_path.write_text(tex_content, encoding="utf-8")
    proc = subprocess.run(  # noqa: S603 -- args are constants, paths controlled
        [tectonic, "--chatter=minimal", tex_path.name],
        capture_output=True,
        text=True,
        check=False,
        cwd=output_dir,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-2000:]
        raise RenderError(f"tectonic compile failed (exit {proc.returncode}):\n{tail}")
    if not pdf_path.exists():
        raise RenderError(f"tectonic returned 0 but {pdf_path} is missing")
    return pdf_path.read_bytes()


def render_tailored_cover_letter_latex(
    tailored: TailoredCoverLetter,
    output_dir: Path,
    *,
    template_name: str = DEFAULT_TEMPLATE_NAME,
    templates_dir: Path | None = None,
    stem: str = "cover-letter",
    today: datetime | None = None,
) -> RenderResult:
    """End-to-end: TailoredCoverLetter -> .tex on disk -> PDF on disk -> RenderResult."""
    tex_content = render_tex(
        tailored,
        template_name=template_name,
        templates_dir=templates_dir,
        today=today,
    )
    pdf_bytes = compile_pdf(tex_content, output_dir, stem=stem)
    pdf_path = (output_dir / f"{stem}.pdf").resolve()
    diffs = (
        RenderDiff(
            kind="cover_letter",
            heading="Cover Letter",
            status=RenderStatus.REPLACED,
            before_chars=0,
            after_chars=sum(len(p) for p in tailored.body_paragraphs)
            + len(tailored.opening)
            + len(tailored.closing),
        ),
    )
    return RenderResult(
        doc_id=output_dir.name or "cover-letter",
        doc_url=pdf_path.as_uri(),
        pdf_size_bytes=len(pdf_bytes),
        diffs=diffs,
    )


# --- internals --------------------------------------------------------------


def _build_env(templates_dir: Path) -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        block_start_string="<%",
        block_end_string="%>",
        variable_start_string="<<",
        variable_end_string=">>",
        comment_start_string="<#",
        comment_end_string="#>",
        # autoescape is for HTML; LaTeX needs our tex_escape pass instead.
        autoescape=False,  # noqa: S701
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def _escape_letter(tailored: TailoredCoverLetter, *, today: datetime | None) -> dict[str, Any]:
    """Turn the structured letter into the dict shape the Jinja template wants.

    Every text field passes through :func:`tex_escape` so user content can
    never inject raw LaTeX. The ``today`` parameter is dependency-injected
    so tests can pin a deterministic date.
    """
    when = (today or datetime.now(UTC)).strftime("%-d %B %Y")
    return {
        "name": tex_escape(tailored.name),
        "email": tex_escape(tailored.contact.email),
        "phone": tex_escape(tailored.contact.phone) if tailored.contact.phone else "",
        "location": tex_escape(tailored.contact.location) if tailored.contact.location else "",
        "company": tex_escape(tailored.company),
        "title": tex_escape(tailored.title),
        "hiring_manager": tex_escape(tailored.hiring_manager or ""),
        "salutation": tex_escape(tailored.salutation),
        "opening": tex_escape(tailored.opening),
        "body_paragraphs": tuple(tex_escape(p) for p in tailored.body_paragraphs),
        "closing": tex_escape(tailored.closing),
        "signoff": tex_escape(tailored.signoff),
        "date": tex_escape(when),
    }
