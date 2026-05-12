"""Resolve a tailored resume from a coverletterai run request.

Two paths:

- ``resume_run_id`` -- HTTP-fetch ``GET /api/runs/<id>`` against the
  resumeai sibling and pull the ``tailored`` field out of the JSON
  response.
- ``resume_payload`` -- the caller supplied the JSON inline; decode it
  here and return.

Both produce a plain ``dict[str, object]`` that the cover-letter agent
+ verifier consume; we don't import the resumeai class so coverletterai
stays a runtime-independent of resumeai (only a content-format
dependency).

Missing resume is a soft failure: the orchestrator proceeds with
``None`` and the agent writes a more generic letter.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, cast

import httpx

if TYPE_CHECKING:
    from coverletterai.runs.models import CoverLetterRequest

_log = logging.getLogger(__name__)

DEFAULT_RESUMEAI_BASE_URL = "http://resumeai:8765"
DEFAULT_TIMEOUT_SECONDS = 10.0


class ResumeResolverError(RuntimeError):
    """Raised when the resolver itself errors (bad payload, network, etc.)."""


def resolve_tailored_resume(
    request: CoverLetterRequest,
    *,
    resumeai_base_url: str = DEFAULT_RESUMEAI_BASE_URL,
    http_client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, object] | None:
    """Return the tailored-resume JSON object for the cover-letter run.

    ``None`` when neither ``resume_run_id`` nor ``resume_payload`` is
    supplied. Raises :class:`ResumeResolverError` when a supplied source
    can't be resolved (bad JSON, 404, network error) -- the orchestrator
    is responsible for funnelling that into a FAILED run with a clear
    error message.
    """
    if request.resume_payload:
        return _load_inline_payload(request.resume_payload)

    if request.resume_run_id:
        return _fetch_by_id(
            request.resume_run_id,
            base_url=resumeai_base_url,
            http_client=http_client,
            timeout=timeout,
        )

    return None


def _load_inline_payload(raw: str) -> dict[str, object]:
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ResumeResolverError(
            f"resume_payload was not valid JSON: {exc.msg} — got {raw[:200]!r}"
        ) from exc
    if not isinstance(data, dict):
        raise ResumeResolverError(
            f"resume_payload must be a JSON object — got {type(data).__name__}"
        )
    return cast("dict[str, object]", data)


def _fetch_by_id(
    run_id: str,
    *,
    base_url: str,
    http_client: httpx.Client | None,
    timeout: float,
) -> dict[str, object]:
    url = f"{base_url.rstrip('/')}/api/runs/{run_id}"
    _log.info("resolving resume_run_id=%s via %s", run_id, url)
    try:
        client = http_client or httpx.Client(timeout=timeout)
        response = client.get(url)
    except httpx.HTTPError as exc:
        raise ResumeResolverError(f"resumeai HTTP error: {exc}") from exc

    if response.status_code == 404:
        raise ResumeResolverError(f"resumeai has no run with id {run_id!r} (HTTP 404 at {url})")
    if response.status_code >= 400:
        raise ResumeResolverError(
            f"resumeai returned HTTP {response.status_code} for {url}: {response.text[:200]!r}"
        )

    try:
        run_payload: Any = response.json()
    except ValueError as exc:
        raise ResumeResolverError(f"resumeai response was not JSON: {exc}") from exc
    if not isinstance(run_payload, dict):
        raise ResumeResolverError(
            f"resumeai response was not a JSON object — got {type(run_payload).__name__}"
        )
    tailored = run_payload.get("tailored")
    if tailored is None:
        raise ResumeResolverError(
            f"resumeai run {run_id!r} has no tailored resume yet "
            f"(status: {run_payload.get('status')})"
        )
    if not isinstance(tailored, dict):
        raise ResumeResolverError(
            f"resumeai run {run_id!r}.tailored was not an object — got {type(tailored).__name__}"
        )
    return cast("dict[str, object]", tailored)
