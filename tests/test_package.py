"""Smoke test: the package imports and exposes ``__version__``."""

from __future__ import annotations

import coverletterai


def test_version_is_a_nonempty_semver_string() -> None:
    assert isinstance(coverletterai.__version__, str)
    assert coverletterai.__version__.count(".") == 2
    assert all(part.isdigit() for part in coverletterai.__version__.split("."))
