"""Cover-letter-specific orchestrator -- subclasses ``BaseOrchestrator``.

The pipeline skeleton (JD fetch + parse, context load, run lifecycle,
event publishing, error handling, vision verification dispatch) lives in
``tailor_core.runs.orchestrator.BaseOrchestrator``. This module supplies
the four hooks the base calls into, plus an extra resolver step that
loads the tailored resume from a ``resume_run_id`` or ``resume_payload``
before tailoring.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from tailor_core.runs.orchestrator import BaseOrchestrator, OrchestratorError

from coverletterai.agent.models import TailoredCoverLetter
from coverletterai.agent.tailor import tailor_cover_letter
from coverletterai.renderer.latex_renderer import render_tailored_cover_letter_latex
from coverletterai.runs.models import CoverLetterRequest
from coverletterai.runs.resume_resolver import ResumeResolverError, resolve_tailored_resume
from coverletterai.settings.models import RuntimeSettings
from coverletterai.verifier.verifier import verify_cover_letter
from coverletterai.verifier.vision import verify_pdf_visually

if TYPE_CHECKING:
    from tailor_core.context.models import UserContext
    from tailor_core.context_files.models import ContextFile
    from tailor_core.jd.models import JobRequirements
    from tailor_core.runs.models import RenderResult, TailorRequest
    from tailor_core.verifier.models import VerificationResult


__all__ = [
    "CoverLetterOrchestrator",
    "OrchestratorError",
]


class CoverLetterOrchestrator(BaseOrchestrator[TailoredCoverLetter, RuntimeSettings]):
    """Cover-letter-tailoring concrete orchestrator.

    Adds one twist over resumeai's orchestrator: the ``_tailor`` hook
    first calls :func:`resolve_tailored_resume` to pull in the resume
    JSON (by-ref via HTTP fetch from resumeai, or inline payload, or
    ``None`` when neither is supplied). The resume JSON flows into the
    agent's prompt + the verifier.
    """

    def __init__(self, *, resumeai_base_url: str | None = None, **kwargs: object) -> None:
        # mypy can't infer the **kwargs forwarding precisely; we trust the
        # base's signature and let the call propagate at runtime.
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._resumeai_base_url = resumeai_base_url
        self._resolved_resume: dict[str, object] | None = None

    def _tailor(
        self,
        requirements: JobRequirements,
        context: UserContext,
        request: TailorRequest,
        context_files: tuple[ContextFile, ...],
    ) -> TailoredCoverLetter:
        cl_request = CoverLetterRequest.model_validate(request.model_dump())
        try:
            resolved = resolve_tailored_resume(
                cl_request,
                resumeai_base_url=self._resumeai_base_url or "http://resumeai:8765",
            )
        except ResumeResolverError as exc:
            raise OrchestratorError(f"could not resolve tailored resume: {exc}") from exc
        # Stash for the later verify hook; ``_verify`` receives only the
        # ``TailoredCoverLetter`` so we keep the resume on the instance.
        self._resolved_resume = resolved
        return tailor_cover_letter(
            requirements,
            resolved,
            context,
            self._llm,
            model=cl_request.model,
            context_files=context_files,
        )

    def _render(
        self,
        tailored: TailoredCoverLetter,
        requirements: JobRequirements,
        output_dir: Path,
    ) -> RenderResult:
        stem = _cover_letter_filename_stem(requirements)
        return render_tailored_cover_letter_latex(tailored, output_dir, stem=stem)

    def _verify(
        self,
        requirements: JobRequirements,
        tailored: TailoredCoverLetter,
        pdf_path: Path,
    ) -> VerificationResult:
        return verify_cover_letter(
            requirements,
            tailored,
            self._resolved_resume,
            self._llm,
            pdf_path=pdf_path,
        )

    def _verify_visually(self, pdf_path: Path) -> VerificationResult | None:
        return verify_pdf_visually(pdf_path)


_FILENAME_SAFE_RE = re.compile(r"[^\w\s\-(),.&]+", re.UNICODE)
_WHITESPACE_RUN_RE = re.compile(r"\s+")


def _cover_letter_filename_stem(requirements: JobRequirements) -> str:
    """Build a per-JD filename stem like ``Cover Letter - GoSource - Software Developer``.

    Mirrors resumeai's slugger pattern. Falls back to ``"cover-letter"``
    when sanitisation strips every part to nothing.
    """
    parts = [
        "Cover Letter",
        _sanitize_for_filename(requirements.company or ""),
        _sanitize_for_filename(requirements.title),
    ]
    parts = [p for p in parts if p]
    return " - ".join(parts) if len(parts) > 1 else "cover-letter"


def _sanitize_for_filename(raw: str) -> str:
    cleaned = _FILENAME_SAFE_RE.sub("", raw)
    return _WHITESPACE_RUN_RE.sub(" ", cleaned).strip(" -._")
