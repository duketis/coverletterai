"""Cover-letter QC verifier.

The text verifier is an LLM-judge pass: a second call reviews the agent's
output against the JD + the tailored resume, catching fabrications +
contradictions + length problems. The vision verifier rasterises the
rendered PDF and looks for layout issues (1-page overflow, awkward
spacing, header alignment).

All the heavy lifting (LLM call, JSON parse, schema validate, page-count
check, fallback synthesis, vision rasteriser) lives in
``tailor_core.verifier.scaffold`` / ``tailor_core.verifier.vision``; this
package supplies the cover-letter-flavoured ``SYSTEM_PROMPT`` and a thin
wrapper that wires the inputs together.
"""

from __future__ import annotations
