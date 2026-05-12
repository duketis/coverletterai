"""Cover-letter tailoring agent.

Public surface:

- :class:`~coverletterai.agent.models.TailoredCoverLetter` -- the
  structured output the agent produces.
- :func:`~coverletterai.agent.prompt.build_cover_letter_prompt` -- composes
  the user-prompt the LLM sees.
- :func:`~coverletterai.agent.parser.parse_tailored_cover_letter` --
  decode the LLM's text response into a ``TailoredCoverLetter``.
- :func:`~coverletterai.agent.tailor.tailor_cover_letter` -- end-to-end
  entry point: ``LLM call -> parse -> TailoredCoverLetter``.

The agent is grounded in the candidate's tailored resume (passed in as
structured input) so the letter never contradicts a resume bullet.
"""

from __future__ import annotations
