"""``CoverLetterOrchestrator`` hook tests + filename helper.

The pipeline-integration coverage lives in ai-tailor-core's BaseOrchestrator
test suite (which exercises the run lifecycle, event publishing, error
funnelling end-to-end via a stub subclass). This file pins coverletterai-
specific behaviour: the four hooks call the right collaborators, the
filename helper slugs JD context correctly, and the resume-resolver
failure path surfaces as an OrchestratorError.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tailor_core.context.models import Contact, ResumeBase, UserContext
from tailor_core.jd.models import (
    EmploymentType,
    JobRequirements,
    RemoteType,
    RoleType,
    Seniority,
)
from tailor_core.llm.client import FakeLLMClient
from tailor_core.runs.events import RunEventBus
from tailor_core.runs.models import RenderResult, TailorRequest
from tailor_core.runs.store import InMemoryRunsStore
from tailor_core.settings.store import InMemorySettingsStore
from tailor_core.verifier.models import VerificationResult, VerificationStatus

from coverletterai.agent.models import CoverLetterContact, TailoredCoverLetter
from coverletterai.runs.models import CoverLetterRequest
from coverletterai.runs.orchestrator import (
    CoverLetterOrchestrator,
    OrchestratorError,
    _cover_letter_filename_stem,
    _sanitize_for_filename,
)
from coverletterai.runs.resume_resolver import ResumeResolverError
from coverletterai.settings.models import RuntimeSettings

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _jd(*, title: str = "Engineer", company: str | None = "Acme") -> JobRequirements:
    return JobRequirements(
        title=title,
        company=company,
        role_type=RoleType.ENGINEERING,
        seniority=Seniority.SENIOR,
        employment_type=EmploymentType.FULL_TIME,
        remote_type=RemoteType.REMOTE,
    )


def _letter() -> TailoredCoverLetter:
    return TailoredCoverLetter(
        name="Jane",
        contact=CoverLetterContact(email="jane@example.com"),
        company="Acme",
        title="Engineer",
        salutation="Dear Hiring Manager,",
        opening="Hello.",
        body_paragraphs=("Para.",),
        closing="Thanks.",
        signoff="Sincerely,",
    )


@pytest.fixture
def orchestrator(tmp_path: Path) -> CoverLetterOrchestrator:
    return CoverLetterOrchestrator(
        runs_store=InMemoryRunsStore[TailoredCoverLetter](),
        settings_store=InMemorySettingsStore(settings_cls=RuntimeSettings),
        llm_client=FakeLLMClient(default_response="{}"),
        event_bus=RunEventBus(),
        context_root=tmp_path / "userctx",
        runs_root=tmp_path / "runs",
    )


# -- _cover_letter_filename_stem -------------------------------------------


class TestCoverLetterFilenameStem:
    def test_combines_company_and_title(self) -> None:
        stem = _cover_letter_filename_stem(_jd(title="Software Developer", company="GoSource"))
        assert stem == "Cover Letter - GoSource - Software Developer"

    def test_drops_missing_company(self) -> None:
        stem = _cover_letter_filename_stem(_jd(title="Software Developer", company=None))
        assert stem == "Cover Letter - Software Developer"

    def test_falls_back_to_cover_letter_when_everything_sanitises_to_empty(self) -> None:
        """title is min_length=1 but ``///`` sanitises to empty; with no
        surviving parts the helper falls back to the literal ``cover-letter``."""
        stem = _cover_letter_filename_stem(_jd(title="///", company="///"))
        assert stem == "cover-letter"

    def test_strips_filesystem_unsafe_characters(self) -> None:
        stem = _cover_letter_filename_stem(_jd(title="DevOps/SRE | Backend", company="ACME: Inc"))
        assert ":" not in stem
        assert "/" not in stem
        assert "|" not in stem
        assert "ACME" in stem
        assert "DevOps" in stem


class TestSanitizeForFilename:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("GoSource", "GoSource"),
            ("Software Developer", "Software Developer"),
            ("ACME (Pty) Ltd.", "ACME (Pty) Ltd"),
            ("R&D Lead", "R&D Lead"),
            ("  spaces   inside  ", "spaces inside"),
            ("path/with/slashes", "pathwithslashes"),
            ("colons:bad", "colonsbad"),
            ("“curly”", "curly"),
            ("", ""),
            ("///", ""),
        ],
    )
    def test_strips_unsafe_chars(self, raw: str, expected: str) -> None:
        assert _sanitize_for_filename(raw) == expected


# -- _tailor hook ----------------------------------------------------------


def test_tailor_calls_resolver_with_request_and_passes_resume_to_agent(
    orchestrator: CoverLetterOrchestrator, mocker: MockerFixture
) -> None:
    """``_tailor`` resolves the resume first then forwards it to the
    cover-letter agent. We stub both collaborators so the test doesn't
    spin up an LLM."""
    resolver = mocker.patch(
        "coverletterai.runs.orchestrator.resolve_tailored_resume",
        return_value={"name": "Jane", "skills": ["Python"]},
    )
    tailor_agent = mocker.patch(
        "coverletterai.runs.orchestrator.tailor_cover_letter",
        return_value=_letter(),
    )

    request = CoverLetterRequest(jd_text="JD", resume_run_id="run_abc")
    result = orchestrator._tailor(
        requirements=_jd(),
        context=UserContext(resume=ResumeBase(name="Jane", contact=Contact(email="j@x.com"))),
        request=request,
        context_files=(),
    )

    assert result == _letter()
    # Resolver got the typed subclass with resume_run_id.
    resolver_arg = resolver.call_args.args[0]
    assert resolver_arg.resume_run_id == "run_abc"
    # Cover-letter agent got the resolved resume dict.
    agent_kwargs = tailor_agent.call_args
    assert agent_kwargs.args[1] == {"name": "Jane", "skills": ["Python"]}
    # Orchestrator stashed the resume for the later verify hook.
    assert orchestrator._resolved_resume == {"name": "Jane", "skills": ["Python"]}


def test_tailor_with_no_resume_source_passes_none_to_agent(
    orchestrator: CoverLetterOrchestrator, mocker: MockerFixture
) -> None:
    mocker.patch(
        "coverletterai.runs.orchestrator.resolve_tailored_resume",
        return_value=None,
    )
    tailor_agent = mocker.patch(
        "coverletterai.runs.orchestrator.tailor_cover_letter",
        return_value=_letter(),
    )

    orchestrator._tailor(
        requirements=_jd(),
        context=UserContext(),
        request=CoverLetterRequest(jd_text="JD"),
        context_files=(),
    )

    assert tailor_agent.call_args.args[1] is None
    assert orchestrator._resolved_resume is None


def test_tailor_wraps_resolver_error_as_orchestrator_error(
    orchestrator: CoverLetterOrchestrator, mocker: MockerFixture
) -> None:
    mocker.patch(
        "coverletterai.runs.orchestrator.resolve_tailored_resume",
        side_effect=ResumeResolverError("HTTP 404"),
    )

    with pytest.raises(OrchestratorError, match="could not resolve tailored resume"):
        orchestrator._tailor(
            requirements=_jd(),
            context=UserContext(),
            request=CoverLetterRequest(jd_text="JD", resume_run_id="bad"),
            context_files=(),
        )


def test_tailor_forwards_model_override_to_agent(
    orchestrator: CoverLetterOrchestrator, mocker: MockerFixture
) -> None:
    mocker.patch("coverletterai.runs.orchestrator.resolve_tailored_resume", return_value=None)
    tailor_agent = mocker.patch(
        "coverletterai.runs.orchestrator.tailor_cover_letter",
        return_value=_letter(),
    )

    orchestrator._tailor(
        requirements=_jd(),
        context=UserContext(),
        request=CoverLetterRequest(jd_text="JD", model="claude-sonnet-4-6"),
        context_files=(),
    )
    assert tailor_agent.call_args.kwargs["model"] == "claude-sonnet-4-6"


# -- _render hook ----------------------------------------------------------


def test_render_calls_renderer_with_jd_flavoured_stem(
    orchestrator: CoverLetterOrchestrator, mocker: MockerFixture, tmp_path: Path
) -> None:
    spy = mocker.patch(
        "coverletterai.runs.orchestrator.render_tailored_cover_letter_latex",
        return_value=RenderResult(doc_id="run_x", doc_url="file:///x.pdf"),
    )

    requirements = _jd(title="Software Developer", company="GoSource")
    orchestrator._render(_letter(), requirements, tmp_path / "run_x")

    assert spy.call_args.kwargs["stem"] == "Cover Letter - GoSource - Software Developer"
    assert spy.call_args.args[1] == tmp_path / "run_x"


# -- _verify hook ----------------------------------------------------------


def test_verify_forwards_resolved_resume_to_verifier(
    orchestrator: CoverLetterOrchestrator, mocker: MockerFixture, tmp_path: Path
) -> None:
    """``_verify`` must pass the stashed resume to the verifier so it can
    flag contradictions; if it forgets, the rubric falls back to
    structural-only checks."""
    orchestrator._resolved_resume = {"name": "Jane"}
    spy = mocker.patch(
        "coverletterai.runs.orchestrator.verify_cover_letter",
        return_value=VerificationResult(status=VerificationStatus.PASSED, summary="ok"),
    )
    pdf = tmp_path / "x.pdf"
    pdf.touch()

    result = orchestrator._verify(_jd(), _letter(), pdf)

    assert result.status is VerificationStatus.PASSED
    # Resume dict reached the verifier as the third positional arg.
    assert spy.call_args.args[2] == {"name": "Jane"}
    assert spy.call_args.kwargs["pdf_path"] == pdf


# -- _verify_visually hook -------------------------------------------------


def test_verify_visually_delegates_to_vision_wrapper(
    orchestrator: CoverLetterOrchestrator, mocker: MockerFixture, tmp_path: Path
) -> None:
    spy = mocker.patch(
        "coverletterai.runs.orchestrator.verify_pdf_visually",
        return_value=VerificationResult(status=VerificationStatus.PASSED, summary="ok"),
    )
    pdf = tmp_path / "x.pdf"
    pdf.touch()
    result = orchestrator._verify_visually(pdf)
    assert result is not None
    spy.assert_called_once_with(pdf)


def test_verify_visually_returns_none_when_wrapper_does(
    orchestrator: CoverLetterOrchestrator, mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("coverletterai.runs.orchestrator.verify_pdf_visually", return_value=None)
    pdf = tmp_path / "x.pdf"
    pdf.touch()
    assert orchestrator._verify_visually(pdf) is None


# -- resumeai_base_url plumbing -------------------------------------------


def test_init_accepts_custom_resumeai_base_url(tmp_path: Path) -> None:
    """Default is ``http://resumeai:8765``; consumers (jobai when it
    eventually wires the chain) can override."""
    orch = CoverLetterOrchestrator(
        runs_store=InMemoryRunsStore[TailoredCoverLetter](),
        settings_store=InMemorySettingsStore(settings_cls=RuntimeSettings),
        llm_client=FakeLLMClient(default_response="{}"),
        resumeai_base_url="http://resume-prod.internal:9000",
        context_root=tmp_path / "userctx",
        runs_root=tmp_path / "runs",
    )
    assert orch._resumeai_base_url == "http://resume-prod.internal:9000"


def test_tailor_uses_default_resumeai_base_url_when_unset(
    orchestrator: CoverLetterOrchestrator, mocker: MockerFixture
) -> None:
    resolver = mocker.patch(
        "coverletterai.runs.orchestrator.resolve_tailored_resume",
        return_value=None,
    )
    mocker.patch(
        "coverletterai.runs.orchestrator.tailor_cover_letter",
        return_value=_letter(),
    )
    orchestrator._tailor(
        requirements=_jd(),
        context=UserContext(),
        request=CoverLetterRequest(jd_text="JD"),
        context_files=(),
    )
    assert resolver.call_args.kwargs["resumeai_base_url"] == "http://resumeai:8765"


def test_create_run_is_inherited(
    orchestrator: CoverLetterOrchestrator,
) -> None:
    """Belt-and-braces: the base ``create_run`` works through the
    cover-letter subclass with the cover-letter-specific request type."""
    run = orchestrator.create_run(TailorRequest(jd_text="paste"))
    assert run.status.value == "pending"
    assert orchestrator._runs.get(run.id) == run
