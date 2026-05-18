"""Cover-letter verifier wrapper tests."""

from __future__ import annotations

import json
from pathlib import Path

from tailor_core.jd.models import JobRequirements, RoleType, Seniority
from tailor_core.llm.client import FakeLLMClient
from tailor_core.verifier.models import IssueSeverity, VerificationStatus

from coverletterai.agent.models import CoverLetterContact, TailoredCoverLetter
from coverletterai.verifier.verifier import (
    SYSTEM_PROMPT,
    TARGET_MAX_PAGES,
    build_verifier_prompt,
    verify_cover_letter,
)


def _jd() -> JobRequirements:
    return JobRequirements(
        title="Senior Engineer",
        company="Acme",
        role_type=RoleType.ENGINEERING,
        seniority=Seniority.SENIOR,
    )


def _letter() -> TailoredCoverLetter:
    return TailoredCoverLetter(
        name="Jane",
        contact=CoverLetterContact(email="jane@example.com"),
        company="Acme",
        title="Senior Engineer",
        salutation="Dear Hiring Manager,",
        opening="Hello.",
        body_paragraphs=("Para.",),
        closing="Thanks.",
        signoff="Sincerely,",
    )


def _passed_payload() -> str:
    return json.dumps(
        {
            "status": "passed",
            "summary": "clean",
            "issues": [],
            "rationale": "fine",
        }
    )


def test_target_max_pages_is_one() -> None:
    """The verifier insists on a 1-page cover letter."""
    assert TARGET_MAX_PAGES == 1


def test_system_prompt_documents_required_schema_fields() -> None:
    for field in ('"status"', '"issues"', '"severity"', '"category"', '"message"'):
        assert field in SYSTEM_PROMPT


def test_system_prompt_calls_out_grounding_rules() -> None:
    assert "fabrication" in SYSTEM_PROMPT.lower()
    assert "contradict" in SYSTEM_PROMPT.lower()


def test_build_verifier_prompt_pairs_jd_with_letter() -> None:
    prompt = build_verifier_prompt(_jd(), _letter(), None)
    assert "# JOB DESCRIPTION" in prompt
    assert "# TAILORED COVER LETTER" in prompt
    assert "# OUTPUT" in prompt
    assert "Senior Engineer" in prompt


def test_build_verifier_prompt_includes_resume_block_when_supplied() -> None:
    resume: dict[str, object] = {"name": "Jane", "skills": ("Python",)}
    prompt = build_verifier_prompt(_jd(), _letter(), resume)
    assert "# TAILORED RESUME" in prompt
    assert '"name": "Jane"' in prompt


def test_verify_cover_letter_propagates_llm_response() -> None:
    llm = FakeLLMClient(default_response=_passed_payload())
    result = verify_cover_letter(_jd(), _letter(), None, llm)
    assert result.status is VerificationStatus.PASSED


def test_verify_cover_letter_flags_overflowing_pdf(tmp_path: Path) -> None:
    """A 2-page rendered PDF triggers a page_overflow warn and bumps
    PASSED -> CONCERNS."""
    from pypdf import PdfWriter  # noqa: PLC0415

    pdf = tmp_path / "letter.pdf"
    writer = PdfWriter()
    for _ in range(2):
        writer.add_blank_page(width=595, height=842)
    with pdf.open("wb") as fh:
        writer.write(fh)

    llm = FakeLLMClient(default_response=_passed_payload())
    result = verify_cover_letter(_jd(), _letter(), None, llm, pdf_path=pdf)
    assert result.status is VerificationStatus.CONCERNS
    overflow = [i for i in result.issues if i.category == "page_overflow"]
    assert len(overflow) == 1
    assert overflow[0].severity is IssueSeverity.WARN
    assert "2 pages" in overflow[0].message


def test_verify_cover_letter_no_overflow_issue_when_one_page(tmp_path: Path) -> None:
    from pypdf import PdfWriter  # noqa: PLC0415

    pdf = tmp_path / "letter.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with pdf.open("wb") as fh:
        writer.write(fh)

    llm = FakeLLMClient(default_response=_passed_payload())
    result = verify_cover_letter(_jd(), _letter(), None, llm, pdf_path=pdf)
    assert result.status is VerificationStatus.PASSED
    assert all(i.category != "page_overflow" for i in result.issues)


def test_verify_cover_letter_forwards_model_override() -> None:
    llm = FakeLLMClient(default_response=_passed_payload())
    verify_cover_letter(_jd(), _letter(), None, llm, model="claude-sonnet-4-6")
    assert llm.calls[0][2] == "claude-sonnet-4-6"


_VERIFIED_FACTS = "VERIFIED jobai: 1,126 backend tests at 100% line + branch coverage."


def _letter_claiming(body: str) -> TailoredCoverLetter:
    return TailoredCoverLetter(
        name="Jane",
        contact=CoverLetterContact(email="jane@example.com"),
        company="Acme",
        title="Senior Engineer",
        salutation="Dear Hiring Manager,",
        opening="Hello.",
        body_paragraphs=(body,),
        closing="Thanks.",
        signoff="Sincerely,",
    )


def test_deterministic_contradiction_folds_in_as_error_failure() -> None:
    llm = FakeLLMClient(default_response=_passed_payload())
    bad = _letter_claiming("jobai runs 705 tests at 89.5% coverage.")
    result = verify_cover_letter(_jd(), bad, None, llm, verified_context=_VERIFIED_FACTS)
    assert result.status is VerificationStatus.FAILED
    fab = [i for i in result.issues if i.category == "fabricated_metric"]
    assert fab and all(i.severity is IssueSeverity.ERROR for i in fab)


def test_clean_letter_with_verified_context_stays_passed() -> None:
    llm = FakeLLMClient(default_response=_passed_payload())
    good = _letter_claiming("jobai has 1,126 backend tests at 100% coverage.")
    result = verify_cover_letter(_jd(), good, None, llm, verified_context=_VERIFIED_FACTS)
    assert result.status is VerificationStatus.PASSED
    assert all(i.category != "fabricated_metric" for i in result.issues)


def test_no_verified_context_skips_deterministic_check() -> None:
    llm = FakeLLMClient(default_response=_passed_payload())
    bad = _letter_claiming("jobai runs 705 tests at 89.5% coverage.")
    result = verify_cover_letter(_jd(), bad, None, llm)
    assert result.status is VerificationStatus.PASSED
