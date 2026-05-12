"""FastAPI application factory.

Tests construct the app with in-memory implementations of every singleton;
production builds the SQLite stores and the ``claude`` CLI subprocess LLM
client by default.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from tailor_core.context_files.store import SqliteContextFileStore
from tailor_core.llm.client import ClaudeCliClient
from tailor_core.runs.store import SqliteRunsStore
from tailor_core.settings.store import SqliteSettingsStore

from coverletterai import __version__
from coverletterai.agent.models import TailoredCoverLetter
from coverletterai.api.deps import AppState
from coverletterai.api.routes import cover_letter as cover_letter_routes
from coverletterai.runs.orchestrator import CoverLetterOrchestrator
from coverletterai.settings.models import RuntimeSettings

# Single SQLite file shared by every store the app uses. Outside the repo
# so it survives ``docker compose down``. Lib defaults point at the neutral
# ``~/.tailor_core/`` -- we override with our own per-app path.
_COVERLETTERAI_DB_PATH = Path("~/.coverletterai/coverletterai.db").expanduser()

if TYPE_CHECKING:
    from tailor_core.context_files.store import ContextFileStore
    from tailor_core.llm.client import LLMClient
    from tailor_core.runs.store import RunsStore
    from tailor_core.settings.store import SettingsStore


def create_app(
    *,
    settings_store: SettingsStore[RuntimeSettings] | None = None,
    runs_store: RunsStore[TailoredCoverLetter] | None = None,
    llm_client: LLMClient | None = None,
    orchestrator: CoverLetterOrchestrator | None = None,
    context_file_store: ContextFileStore | None = None,
) -> FastAPI:
    """Build a configured FastAPI app.

    Every dependency can be injected from tests; defaults are the production
    implementations. ``orchestrator`` is built from the other singletons
    when not supplied -- pass it directly for tests that want full control.
    """
    settings = settings_store or SqliteSettingsStore(
        settings_cls=RuntimeSettings, db_path=_COVERLETTERAI_DB_PATH
    )
    runs = runs_store or SqliteRunsStore(
        tailored_cls=TailoredCoverLetter, db_path=_COVERLETTERAI_DB_PATH
    )
    context_files = context_file_store or SqliteContextFileStore(db_path=_COVERLETTERAI_DB_PATH)
    llm = llm_client or ClaudeCliClient()
    orch = orchestrator or CoverLetterOrchestrator(
        runs_store=runs,
        settings_store=settings,
        llm_client=llm,
        context_file_store=context_files,
    )

    app = FastAPI(
        title="coverletterai",
        version=__version__,
        description="AI-driven cover-letter tailoring -- LaTeX/Tectonic rendered.",
    )
    app.state.app_state = AppState(
        settings_store=settings,
        runs_store=runs,
        orchestrator=orch,
        context_file_store=context_files,
    )

    app.include_router(cover_letter_routes.router)

    return app
