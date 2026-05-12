"""LaTeX renderer: render a :class:`~coverletterai.agent.models.TailoredCoverLetter` to PDF.

Pipeline:

1. Compose the .tex string by feeding the tailored cover-letter into a Jinja2
   template. Every user-derived value passes through ``tex_escape`` first so
   LaTeX control characters can't break the document.
2. Invoke ``tectonic`` as a subprocess to compile the .tex to a PDF.
3. Return a :class:`~tailor_core.runs.models.RenderResult` whose ``doc_url``
   points at the rendered PDF on disk.

The template is fixed at this stage (single style, no Settings toggle). When
a second style materialises the renderer will key off the consumer's
``RuntimeSettings`` -- same hook as resumeai's ``template_name``.
"""

from __future__ import annotations
