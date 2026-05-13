"""Shared fixtures for cover-letter API route tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from tailor_core.context_files.store import InMemoryContextFileStore
from tailor_core.llm.client import FakeLLMClient
from tailor_core.runs.store import InMemoryRunsStore
from tailor_core.settings.store import InMemorySettingsStore

from coverletterai.agent.models import TailoredCoverLetter
from coverletterai.api.app import create_app
from coverletterai.runs.orchestrator import CoverLetterOrchestrator
from coverletterai.settings.models import RuntimeSettings

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def store() -> InMemorySettingsStore[RuntimeSettings]:
    return InMemorySettingsStore(settings_cls=RuntimeSettings)


@pytest.fixture
def runs() -> InMemoryRunsStore[TailoredCoverLetter]:
    return InMemoryRunsStore[TailoredCoverLetter]()


@pytest.fixture
def llm() -> FakeLLMClient:
    return FakeLLMClient(default_response="{}")


@pytest.fixture
def context_files() -> InMemoryContextFileStore:
    return InMemoryContextFileStore()


@pytest.fixture
def orchestrator(
    store: InMemorySettingsStore[RuntimeSettings],
    runs: InMemoryRunsStore[TailoredCoverLetter],
    llm: FakeLLMClient,
    context_files: InMemoryContextFileStore,
    tmp_path: pytest.TempPathFactory,
) -> CoverLetterOrchestrator:
    return CoverLetterOrchestrator(
        runs_store=runs,
        settings_store=store,
        llm_client=llm,
        context_file_store=context_files,
        runs_root=tmp_path,
    )


@pytest.fixture
def client(
    store: InMemorySettingsStore[RuntimeSettings],
    runs: InMemoryRunsStore[TailoredCoverLetter],
    llm: FakeLLMClient,
    orchestrator: CoverLetterOrchestrator,
    context_files: InMemoryContextFileStore,
) -> Iterator[TestClient]:
    app = create_app(
        settings_store=store,
        runs_store=runs,
        llm_client=llm,
        orchestrator=orchestrator,
        context_file_store=context_files,
    )
    with TestClient(app) as test_client:
        yield test_client
