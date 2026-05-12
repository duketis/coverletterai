"""Pydantic model for coverletterai runtime settings.

v0.1 carries only the keys ``BaseRuntimeSettings`` provides (``model``). A
``template_name`` toggle will land if and when a second cover-letter style
shows up; for now the LaTeX template is fixed.
"""

from __future__ import annotations

from tailor_core.settings.models import BaseRuntimeSettings


class RuntimeSettings(BaseRuntimeSettings):
    """User-tunable coverletterai settings persisted in the local SQLite DB."""
