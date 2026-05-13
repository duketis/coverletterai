"""Cover-letter API route tests -- POST /api/tailor + GET runs/{id} + PDF download."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from tailor_core.runs.models import RenderResult, Run, RunStatus, TailorRequest
from tailor_core.runs.store import InMemoryRunsStore

from coverletterai.agent.models import CoverLetterContact, TailoredCoverLetter
from coverletterai.api.app import _COVERLETTERAI_DB_PATH, create_app
from coverletterai.api.deps import (
    AppState,
    get_app_state,
    get_context_file_store,
    get_orchestrator,
    get_runs_store,
    get_settings_store,
)
from coverletterai.settings.models import RuntimeSettings

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


# -- helpers ---------------------------------------------------------------


def _letter() -> TailoredCoverLetter:
    return TailoredCoverLetter(
        name="Jane Doe",
        contact=CoverLetterContact(email="jane@example.com"),
        company="Acme",
        title="Engineer",
        salutation="Dear Hiring Manager,",
        opening="Hello.",
        body_paragraphs=("Para.",),
        closing="Thanks.",
        signoff="Sincerely,",
    )


def _make_succeeded_run(*, run_id: str, pdf_path: Path) -> Run[TailoredCoverLetter]:
    when = datetime(2026, 5, 13, tzinfo=UTC)
    return Run(
        id=run_id,
        request=TailorRequest(jd_text="JD"),
        status=RunStatus.SUCCEEDED,
        created_at=when,
        updated_at=when,
        tailored=_letter(),
        result=RenderResult(doc_id=run_id, doc_url=pdf_path.as_uri(), pdf_size_bytes=12),
    )


def _make_pending_run(run_id: str = "run_pending") -> Run[TailoredCoverLetter]:
    when = datetime(2026, 5, 13, tzinfo=UTC)
    return Run(
        id=run_id,
        request=TailorRequest(jd_text="JD"),
        status=RunStatus.PENDING,
        created_at=when,
        updated_at=when,
    )


# -- POST /api/tailor ------------------------------------------------------


def test_post_tailor_kicks_off_a_run(
    client: TestClient, runs: InMemoryRunsStore[TailoredCoverLetter]
) -> None:
    response = client.post("/api/tailor", json={"jd_text": "Senior Engineer ..."})
    assert response.status_code == 202
    body = response.json()
    run_id = body["run_id"]
    assert body["status"] == "pending"
    # The orchestrator persisted a record.
    stored = runs.get(run_id)
    assert stored is not None


def test_post_tailor_accepts_resume_run_id(
    client: TestClient,
    runs: InMemoryRunsStore[TailoredCoverLetter],
    mocker: MockerFixture,
) -> None:
    """By-ref path: the request carries ``resume_run_id`` for the resolver."""
    # Stop the orchestrator from racing the test by mocking out the
    # collaborators it kicks off in the background task.
    mocker.patch(
        "coverletterai.runs.orchestrator.resolve_tailored_resume",
        return_value=None,
    )
    response = client.post(
        "/api/tailor",
        json={"jd_text": "JD", "resume_run_id": "run_resume_abc"},
    )
    assert response.status_code == 202


def test_post_tailor_rejects_both_resume_sources(client: TestClient) -> None:
    """The model_validator on ``CoverLetterRequest`` enforces at-most-one."""
    response = client.post(
        "/api/tailor",
        json={
            "jd_text": "JD",
            "resume_run_id": "run_abc",
            "resume_payload": '{"name": "Jane"}',
        },
    )
    assert response.status_code == 422


def test_post_tailor_rejects_neither_jd_source(client: TestClient) -> None:
    """Inherits the parent ``TailorRequest`` exactly-one-of rule."""
    response = client.post("/api/tailor", json={})
    assert response.status_code == 422


# -- GET /api/runs/{id} ----------------------------------------------------


def test_get_run_returns_serialised_record(
    client: TestClient,
    runs: InMemoryRunsStore[TailoredCoverLetter],
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "letter.pdf"
    pdf.write_bytes(b"%PDF-1.4 ...")
    run = _make_succeeded_run(run_id="run_one", pdf_path=pdf)
    runs.save(run)

    response = client.get(f"/api/runs/{run.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "run_one"
    assert body["status"] == "succeeded"
    assert body["tailored"]["name"] == "Jane Doe"


def test_get_run_returns_404_for_unknown_id(client: TestClient) -> None:
    response = client.get("/api/runs/never-saved")
    assert response.status_code == 404


# -- GET /api/runs ---------------------------------------------------------


def test_list_runs_returns_recent(
    client: TestClient,
    runs: InMemoryRunsStore[TailoredCoverLetter],
) -> None:
    runs.save(_make_pending_run(run_id="run_a"))
    runs.save(_make_pending_run(run_id="run_b"))

    response = client.get("/api/runs")
    assert response.status_code == 200
    body = response.json()
    assert {r["id"] for r in body["runs"]} == {"run_a", "run_b"}


def test_list_runs_respects_limit(
    client: TestClient,
    runs: InMemoryRunsStore[TailoredCoverLetter],
) -> None:
    for i in range(5):
        runs.save(_make_pending_run(run_id=f"run_{i}"))

    response = client.get("/api/runs?limit=2")
    assert response.status_code == 200
    assert len(response.json()["runs"]) == 2


# -- GET /api/runs/{id}/pdf ------------------------------------------------


def test_download_pdf_streams_file_when_present(
    client: TestClient,
    runs: InMemoryRunsStore[TailoredCoverLetter],
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "letter.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    runs.save(_make_succeeded_run(run_id="run_dl", pdf_path=pdf))

    response = client.get("/api/runs/run_dl/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 fake"


def test_download_pdf_returns_404_for_unknown_run(client: TestClient) -> None:
    response = client.get("/api/runs/never/pdf")
    assert response.status_code == 404


def test_download_pdf_returns_404_when_run_unrendered(
    client: TestClient,
    runs: InMemoryRunsStore[TailoredCoverLetter],
) -> None:
    runs.save(_make_pending_run(run_id="run_pending"))
    response = client.get("/api/runs/run_pending/pdf")
    assert response.status_code == 404


def test_download_pdf_returns_502_for_non_file_url(
    client: TestClient,
    runs: InMemoryRunsStore[TailoredCoverLetter],
) -> None:
    """Defensive: a renderer producing an http:// URL means something's
    wrong; the route surfaces 502 rather than trying to fetch it."""
    when = datetime(2026, 5, 13, tzinfo=UTC)
    run: Run[TailoredCoverLetter] = Run(
        id="run_bad",
        request=TailorRequest(jd_text="JD"),
        status=RunStatus.SUCCEEDED,
        created_at=when,
        updated_at=when,
        result=RenderResult(doc_id="x", doc_url="https://example.com/x.pdf"),
    )
    runs.save(run)
    response = client.get("/api/runs/run_bad/pdf")
    assert response.status_code == 502


def test_download_pdf_returns_404_when_file_url_missing_on_disk(
    client: TestClient,
    runs: InMemoryRunsStore[TailoredCoverLetter],
    tmp_path: Path,
) -> None:
    """``doc_url`` claims a file path that doesn't exist on disk."""
    missing = tmp_path / "ghost.pdf"
    runs.save(_make_succeeded_run(run_id="run_ghost", pdf_path=missing))
    response = client.get("/api/runs/run_ghost/pdf")
    assert response.status_code == 404


# -- create_app defaults ---------------------------------------------------


def test_create_app_without_args_constructs_sqlite_stores(mocker: MockerFixture) -> None:
    """The default factory path builds SQLite-backed stores. Mock the
    constructors so the test doesn't actually open a SQLite file."""
    sqlite_settings = mocker.patch(
        "coverletterai.api.app.SqliteSettingsStore",
        return_value=mocker.MagicMock(),
    )
    sqlite_runs = mocker.patch(
        "coverletterai.api.app.SqliteRunsStore",
        return_value=mocker.MagicMock(),
    )
    sqlite_ctx = mocker.patch(
        "coverletterai.api.app.SqliteContextFileStore",
        return_value=mocker.MagicMock(),
    )
    mocker.patch("coverletterai.api.app.ClaudeCliClient", return_value=mocker.MagicMock())

    app = create_app()
    assert app.title == "coverletterai"
    sqlite_settings.assert_called_once_with(
        settings_cls=RuntimeSettings, db_path=_COVERLETTERAI_DB_PATH
    )
    sqlite_runs.assert_called_once_with(
        tailored_cls=TailoredCoverLetter, db_path=_COVERLETTERAI_DB_PATH
    )
    sqlite_ctx.assert_called_once_with(db_path=_COVERLETTERAI_DB_PATH)


# -- deps providers --------------------------------------------------------


def test_get_app_state_returns_wired_singletons(client: TestClient) -> None:
    """``get_app_state`` reaches into ``request.app.state.app_state``;
    accessor functions each pull one field from that record."""
    from fastapi import Request  # noqa: PLC0415

    app = client.app
    scope = {"type": "http", "app": app}
    request = Request(scope)
    state = get_app_state(request)
    assert isinstance(state, AppState)
    assert get_settings_store(request) is state.settings_store
    assert get_runs_store(request) is state.runs_store
    assert get_orchestrator(request) is state.orchestrator
    assert get_context_file_store(request) is state.context_file_store
