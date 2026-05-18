"""Prompt-builder + system-prompt sanity."""

from __future__ import annotations

from tailor_core.context.models import (
    Contact,
    GitAuditEntry,
    ProjectEntry,
    ResumeBase,
    UserContext,
    WorkHistoryEntry,
)
from tailor_core.context_files.models import ContextFile, ContextFileKind
from tailor_core.jd.models import (
    EmploymentType,
    JobRequirements,
    RemoteType,
    RoleType,
    Seniority,
)

from coverletterai.agent.prompt import (
    SYSTEM_PROMPT,
    build_cover_letter_prompt,
)


def _jd() -> JobRequirements:
    return JobRequirements(
        title="Senior Engineer",
        company="Acme",
        role_type=RoleType.ENGINEERING,
        seniority=Seniority.SENIOR,
        employment_type=EmploymentType.FULL_TIME,
        remote_type=RemoteType.REMOTE,
        required_skills=("Python",),
        must_haves=("AU citizen",),
    )


def _context() -> UserContext:
    return UserContext(
        resume=ResumeBase(name="Jane", contact=Contact(email="jane@example.com")),
        work_history=(
            WorkHistoryEntry(
                slug="acme-2020",
                title="Engineer",
                company="Acme",
                start="2020",
                end="2024",
                summary="Stuff.",
            ),
            WorkHistoryEntry(
                slug="current-2024",
                title="Senior Engineer",
                company="BetaCo",
                start="2024",
                summary="Other stuff.",
            ),
        ),
        projects=(
            ProjectEntry(
                slug="proj",
                name="my-project",
                summary="A side project.",
            ),
        ),
        git_audit=(
            GitAuditEntry(slug="repo-a", repo="repo-a", role="contributor"),
            GitAuditEntry(slug="repo-b", repo="repo-b"),
        ),
    )


def test_system_prompt_documents_required_schema_fields() -> None:
    for field in (
        '"name"',
        '"contact"',
        '"company"',
        '"title"',
        '"opening"',
        '"body_paragraphs"',
        '"closing"',
        '"signoff"',
    ):
        assert field in SYSTEM_PROMPT, f"missing {field}"


def test_system_prompt_calls_out_grounding_rules() -> None:
    assert "NEVER FABRICATE" in SYSTEM_PROMPT
    assert "NEVER CONTRADICT THE TAILORED RESUME" in SYSTEM_PROMPT
    assert "ONE PAGE" in SYSTEM_PROMPT


def test_system_prompt_forbids_inventing_project_metrics() -> None:
    """Regression: jobai run #50 -- the LLM hallucinated '705+ tests at
    89.5% coverage' about the candidate's own repo. The prompt must
    explicitly forbid inventing/recalling any quantitative claim."""
    assert "NEVER INVENT A NUMBER" in SYSTEM_PROMPT
    assert "VERBATIM" in SYSTEM_PROMPT
    assert "hallucination" in SYSTEM_PROMPT


def test_build_prompt_pairs_jd_with_resume_and_context() -> None:
    tailored_resume: dict[str, object] = {"name": "Jane Doe", "skills": ["Python"]}
    prompt = build_cover_letter_prompt(_jd(), tailored_resume, _context())
    assert "# JOB DESCRIPTION" in prompt
    assert "# TAILORED RESUME" in prompt
    assert "# USER CONTEXT" in prompt
    assert "# OUTPUT" in prompt
    assert "Senior Engineer" in prompt  # JD title
    assert '"name": "Jane Doe"' in prompt  # resume payload
    assert "Acme" in prompt  # work history


def test_build_prompt_omits_tailored_resume_block_when_none() -> None:
    prompt = build_cover_letter_prompt(_jd(), None, _context())
    assert "# JOB DESCRIPTION" in prompt
    assert "# TAILORED RESUME" not in prompt


def test_build_prompt_includes_supplementary_documents() -> None:
    from datetime import UTC, datetime  # noqa: PLC0415

    files = (
        ContextFile(
            id="x",
            name="role-notes.md",
            kind=ContextFileKind.MARKDOWN,
            extracted_text="Notes about the role.",
            byte_size=20,
            uploaded_at=datetime(2026, 5, 12, tzinfo=UTC),
        ),
    )
    prompt = build_cover_letter_prompt(_jd(), None, _context(), context_files=files)
    assert "# SUPPLEMENTARY DOCUMENTS" in prompt
    assert "role-notes.md" in prompt
    assert "Notes about the role." in prompt


def test_build_prompt_handles_empty_context() -> None:
    prompt = build_cover_letter_prompt(_jd(), None, UserContext())
    assert "(no user context loaded)" in prompt


def test_build_prompt_includes_current_role_dates_when_end_missing() -> None:
    ctx = UserContext(
        work_history=(
            WorkHistoryEntry(
                slug="x",
                title="Engineer",
                company="Acme",
                start="2024",
                summary="",
            ),
        ),
    )
    prompt = build_cover_letter_prompt(_jd(), None, ctx)
    assert "2024 – present" in prompt


def test_build_prompt_handles_missing_dates() -> None:
    ctx = UserContext(
        work_history=(
            WorkHistoryEntry(
                slug="x",
                title="Engineer",
                company="Acme",
                summary="",
            ),
        ),
    )
    prompt = build_cover_letter_prompt(_jd(), None, ctx)
    assert "dates unknown" in prompt


_VERIFIED = "VERIFIED jobai stats: 1,126 backend tests at 100% coverage."


def test_verified_facts_emitted_before_jd_when_supplied() -> None:
    prompt = build_cover_letter_prompt(_jd(), None, _context(), verified_context=_VERIFIED)
    assert "# VERIFIED FACTS" in prompt
    assert "1,126 backend tests at 100% coverage" in prompt
    assert "VERBATIM" in prompt
    # Ground truth must precede the JD so the model anchors on it first.
    assert prompt.index("# VERIFIED FACTS") < prompt.index("# JOB DESCRIPTION")


def test_verified_facts_omitted_when_absent() -> None:
    assert "# VERIFIED FACTS" not in build_cover_letter_prompt(_jd(), None, _context())


def test_verified_facts_omitted_when_blank() -> None:
    prompt = build_cover_letter_prompt(_jd(), None, _context(), verified_context="   \n ")
    assert "# VERIFIED FACTS" not in prompt
