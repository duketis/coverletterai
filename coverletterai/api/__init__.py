"""FastAPI surface for coverletterai.

Routes:

- ``POST /api/tailor`` -- create + kick off a run.
- ``GET  /api/runs/{run_id}`` -- fetch a run record.
- ``GET  /api/runs/{run_id}/pdf`` -- download the rendered cover-letter PDF.
- ``GET  /api/runs`` -- recent runs.

UI templates land later; v0.1 is JSON-first.
"""

from __future__ import annotations
