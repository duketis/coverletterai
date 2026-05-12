"""Resume-resolver tests: by-id HTTP fetch + inline payload + error paths."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest

from coverletterai.runs.models import CoverLetterRequest
from coverletterai.runs.resume_resolver import (
    ResumeResolverError,
    resolve_tailored_resume,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


# -- inline payload --------------------------------------------------------


def test_returns_decoded_payload_when_inline_supplied() -> None:
    payload = json.dumps({"name": "Jane", "skills": ["Python"]})
    req = CoverLetterRequest(jd_text="JD", resume_payload=payload)
    out = resolve_tailored_resume(req)
    assert out == {"name": "Jane", "skills": ["Python"]}


def test_raises_when_payload_not_json() -> None:
    req = CoverLetterRequest(jd_text="JD", resume_payload="not json")
    with pytest.raises(ResumeResolverError, match="not valid JSON"):
        resolve_tailored_resume(req)


def test_raises_when_payload_not_an_object() -> None:
    req = CoverLetterRequest(jd_text="JD", resume_payload="[1, 2]")
    with pytest.raises(ResumeResolverError, match="must be a JSON object"):
        resolve_tailored_resume(req)


# -- no source ------------------------------------------------------------


def test_returns_none_when_no_resume_source_supplied() -> None:
    assert resolve_tailored_resume(CoverLetterRequest(jd_text="JD")) is None


# -- by-id HTTP -----------------------------------------------------------


def _httpx_client_returning(
    response: httpx.Response,
) -> httpx.Client:
    transport = httpx.MockTransport(lambda _request: response)
    return httpx.Client(transport=transport)


def test_returns_tailored_payload_when_by_id_succeeds() -> None:
    req = CoverLetterRequest(jd_text="JD", resume_run_id="run_abc")
    body = {"tailored": {"name": "Jane"}, "status": "succeeded"}
    client = _httpx_client_returning(httpx.Response(200, json=body))
    out = resolve_tailored_resume(
        req,
        resumeai_base_url="http://resumeai:8765",
        http_client=client,
    )
    assert out == {"name": "Jane"}


def test_raises_on_404() -> None:
    req = CoverLetterRequest(jd_text="JD", resume_run_id="run_abc")
    client = _httpx_client_returning(httpx.Response(404, text="not found"))
    with pytest.raises(ResumeResolverError, match="no run with id"):
        resolve_tailored_resume(req, http_client=client)


def test_raises_on_500() -> None:
    req = CoverLetterRequest(jd_text="JD", resume_run_id="run_abc")
    client = _httpx_client_returning(httpx.Response(500, text="boom"))
    with pytest.raises(ResumeResolverError, match="HTTP 500"):
        resolve_tailored_resume(req, http_client=client)


def test_raises_on_non_json_response() -> None:
    req = CoverLetterRequest(jd_text="JD", resume_run_id="run_abc")
    client = _httpx_client_returning(httpx.Response(200, text="<html/>"))
    with pytest.raises(ResumeResolverError, match="was not JSON"):
        resolve_tailored_resume(req, http_client=client)


def test_raises_on_non_object_response() -> None:
    req = CoverLetterRequest(jd_text="JD", resume_run_id="run_abc")
    client = _httpx_client_returning(httpx.Response(200, json=[1, 2, 3]))
    with pytest.raises(ResumeResolverError, match="not a JSON object"):
        resolve_tailored_resume(req, http_client=client)


def test_raises_when_tailored_field_missing() -> None:
    req = CoverLetterRequest(jd_text="JD", resume_run_id="run_abc")
    body = {"status": "rendering"}
    client = _httpx_client_returning(httpx.Response(200, json=body))
    with pytest.raises(ResumeResolverError, match="no tailored resume yet"):
        resolve_tailored_resume(req, http_client=client)


def test_raises_when_tailored_not_an_object() -> None:
    req = CoverLetterRequest(jd_text="JD", resume_run_id="run_abc")
    body = {"tailored": "weird string"}
    client = _httpx_client_returning(httpx.Response(200, json=body))
    with pytest.raises(ResumeResolverError, match="not an object"):
        resolve_tailored_resume(req, http_client=client)


def test_wraps_httpx_error(mocker: MockerFixture) -> None:
    req = CoverLetterRequest(jd_text="JD", resume_run_id="run_abc")

    class _ExplodingClient:
        def get(self, _url: str) -> httpx.Response:
            raise httpx.ConnectError("boom")

    mocker.patch("httpx.Client", return_value=_ExplodingClient())
    with pytest.raises(ResumeResolverError, match="HTTP error"):
        resolve_tailored_resume(req)
