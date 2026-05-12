# coverletterai

AI-driven cover-letter tailoring service. Reads a job description and a
tailored resume, then produces a 1-page LaTeX-rendered cover letter that
lines up with the resume's bullets.

Sibling service to [resumeai](https://github.com/duketis/resumeai). Both
consume the shared library
[ai-tailor-core](https://github.com/duketis/ai-tailor-core).

## What it does

1. Accept a job description (URL or paste-in) and a tailored resume
   (either an uploaded JSON / PDF or a by-ref lookup of a resumeai run).
2. Load the user's career context tree (resume base, work history,
   projects, prior cover letters, git audits) via
   `tailor_core.context.loader`.
3. Drive a tailoring agent (Anthropic `claude` CLI subprocess on the
   Max-subscription OAuth path) that returns a structured
   `TailoredCoverLetter` pydantic model.
4. Render the structured output to LaTeX via Jinja2 and compile to a
   1-page PDF with [Tectonic](https://tectonic-typesetting.github.io/).
5. Run a QC pass: a second LLM call reviews the letter for fabrications,
   contradictions with the resume, and tone. A vision pass checks layout.
6. Persist the run record + PDF on disk so jobai (eventually) can pull
   a batch of letters for a batch of jobs.

## How to run

Docker compose:

```bash
docker compose up -d
```

The service binds port `8766` (resumeai is on `8765` so both can run
side-by-side). Auth comes from a long-lived
`CLAUDE_CODE_OAUTH_TOKEN` in `.env` (generated via `claude setup-token`).

Local Python:

```bash
pip install -e ../ai-tailor-core   # editable sibling
pip install -e ".[dev]"
uvicorn coverletterai.api.app:create_app --factory --host 0.0.0.0 --port 8766
```

## Engineering bar

Python 3.12, mypy strict, ruff strict, signed conventional commits,
100% line + branch coverage on every module.
`./Tools/quality-gate.sh` runs the canonical local check.

## License

MIT. See [LICENSE](LICENSE).
