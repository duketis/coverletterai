"""AI-driven cover-letter tailoring service.

Reads a job description + a tailored resume, then produces a 1-page LaTeX-
rendered cover letter that lines up with the resume's bullets. Sibling to
``resumeai``; both consume ``ai-tailor-core`` for the shared building blocks
(LLM client, JD ingest, run orchestration, verifier scaffolding, user-context
loader).
"""

from __future__ import annotations

__version__ = "0.1.3"

__all__ = ["__version__"]
