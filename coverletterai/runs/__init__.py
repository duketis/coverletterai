"""Cover-letter-tailoring run orchestration.

The pipeline skeleton lives in ``tailor_core.runs``. This package supplies
the cover-letter-flavoured concrete orchestrator, the request subclass
that carries the ``resume_run_id`` / ``resume_payload`` keys, and the HTTP-
based resume resolver that fetches a previously-tailored resume from a
running resumeai sibling.
"""

from __future__ import annotations
