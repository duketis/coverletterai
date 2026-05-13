"""Tailoring API: kick off cover-letter runs, fetch state, download PDFs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from tailor_core.runs.models import Run

from coverletterai.api.deps import get_orchestrator, get_runs_store
from coverletterai.runs.models import CoverLetterRequest

if TYPE_CHECKING:
    from tailor_core.runs.store import RunsStore

    from coverletterai.agent.models import TailoredCoverLetter
    from coverletterai.runs.orchestrator import CoverLetterOrchestrator


router = APIRouter(prefix="/api")

_BACKGROUND_TASKS: set[asyncio.Task[object]] = set()


@router.post("/tailor", status_code=202)
async def kickoff_tailor(
    request: CoverLetterRequest,
    runs: RunsStore[TailoredCoverLetter] = Depends(get_runs_store),
    orchestrator: CoverLetterOrchestrator = Depends(get_orchestrator),
) -> dict[str, str]:
    """Create a new run + kick off the pipeline. Returns the run id."""
    del runs
    run = orchestrator.create_run(request)
    task: asyncio.Task[object] = asyncio.create_task(orchestrator.execute(run.id))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return {"run_id": run.id, "status": run.status.value}


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    runs: RunsStore[TailoredCoverLetter] = Depends(get_runs_store),
) -> dict[str, Any]:
    run = runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown run {run_id!r}")
    return _serialise_run(run)


@router.get("/runs")
def list_runs(
    limit: int = 20,
    runs: RunsStore[TailoredCoverLetter] = Depends(get_runs_store),
) -> dict[str, Any]:
    return {"runs": [_serialise_run(run) for run in runs.list_recent(limit=limit)]}


@router.get("/runs/{run_id}/pdf")
def download_pdf(
    run_id: str,
    runs: RunsStore[TailoredCoverLetter] = Depends(get_runs_store),
) -> FileResponse:
    """Stream the rendered PDF for ``run_id``.

    Convenience endpoint for jobai / the user / a future bot to fetch
    the artefact without having to know the on-disk path. Returns 404 if
    the run doesn't exist or hasn't rendered yet.
    """
    run = runs.get(run_id)
    if run is None or run.result is None:
        raise HTTPException(status_code=404, detail=f"no rendered PDF for run {run_id!r}")
    pdf_url = run.result.doc_url
    if not pdf_url.startswith("file://"):
        raise HTTPException(status_code=502, detail=f"PDF URL is not a local file: {pdf_url!r}")
    # ``doc_url`` is a ``Path.as_uri()`` string, so reserved characters in the
    # filename (notably the spaces in "Cover Letter - <Company> - <Title>.pdf")
    # come back URL-encoded as ``%20``. ``Path`` doesn't decode them, so we
    # must, or ``exists()`` falsely returns False and the route 404s with the
    # file sitting right there on disk.
    pdf_path = Path(unquote(urlparse(pdf_url).path))
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF missing on disk for run {run_id!r}")
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path.name)


def _serialise_run(run: Run[TailoredCoverLetter]) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(run.model_dump_json())
    return parsed
