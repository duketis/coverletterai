"""Runtime settings for the coverletterai app.

A thin subclass of ``tailor_core.settings.BaseRuntimeSettings``; v0.1 has no
extra resume-app-specific keys, so the subclass is effectively a typed alias.
We keep it for symmetry with resumeai (which adds ``template_name``) and so
the ``SettingsStore[RuntimeSettings]`` parameterisation stays clean.
"""

from __future__ import annotations
