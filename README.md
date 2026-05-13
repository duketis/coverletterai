# coverletterai

> AI-driven cover-letter tailoring. Reads a job description and a tailored resume, then produces a 1-page LaTeX-rendered cover letter that lines up with the resume's bullets without contradicting them.

`coverletterai` is the cover-letter counterpart to [resumeai](https://github.com/duketis/resumeai). Both consume the shared library [ai-tailor-core](https://github.com/duketis/ai-tailor-core); both are part of a small family of personal AI tools by [Jonathan Duketis](https://github.com/duketis).

## What it does

Given a job description (URL or paste-in) **and** a tailored resume to ground the letter in:

1. **Resolve the resume.** Either by-ref (`resume_run_id` → HTTP fetch against a running resumeai sibling at `http://resumeai:8765/api/runs/<id>`) or inline (`resume_payload`: a JSON-encoded `TailoredResume` blob the caller hands in). Both paths are documented; `jobai` will use by-ref, manual / API callers can use either.
2. **Parse the JD** via the shared `tailor_core.jd` pipeline → typed `JobRequirements`.
3. **Load the user's career context** via `tailor_core.context.loader` — the same `UserContext/` tree resumeai reads (`resume.yaml`, `work_history/*.md`, `projects/*.md`, `cover_letters/*.md`, `git_audit/*.md`). The directory is bind-mounted from the resumeai checkout, read-only.
4. **Run a Claude-powered cover-letter agent** that emits a structured `TailoredCoverLetter` pydantic model. The agent's hard rules forbid fabricating any employer / metric / project, contradicting any resume bullet, and using stale openings ("I am writing to apply", "I am passionate about", "I would welcome the opportunity to"). Body paragraphs (1-4) must each ground in a specific resume bullet.
5. **Render to PDF** by feeding the structured output through a Jinja2 LaTeX template and compiling with [Tectonic](https://tectonic-typesetting.github.io/) → 1-page letter, filename `Cover Letter - <Company> - <Title>.pdf`.
6. **QC the output.** A text-mode LLM-judge pass catches fabrications, resume contradictions, generic body paragraphs, cliché openings, and length problems. A programmatic page-count check pins the cap at 1 page. A vision pass rasterises the PDF and asks Claude for layout-only feedback (1-page fit, header alignment, signoff position, even spacing, no margin overflow).

## Status

**Pre-1.0, end-to-end pipeline shipping.** `docker compose up -d` brings the FastAPI app up on `:8766` (resumeai is on `:8765`; both run side-by-side via docker-compose with both containers attached to `ai-tailor-network`).

**Headline numbers (2026-05-13):**
- 135 unit tests locally, 100% line + branch coverage (the heavy lifting — JD ingest, run orchestration, verifier scaffold, user-context loader — lives in [ai-tailor-core](https://github.com/duketis/ai-tailor-core), which has 357)
- mypy strict, ruff strict, ruff-format clean
- CI green on every push (ruff + ruff-format + mypy + pytest)
- Three smoke paths exercised end-to-end against a live SEEK JD: JD-only (`~110s`), by-payload (`~50s`), by-ref against a resumeai run (`~50s`); the by-ref path produces a letter that opens by naming the hiring company and pulls bullets from the just-generated tailored resume rather than from a hardcoded prompt.

## Architecture (high level)

```
[Job description URL or text]              [Tailored resume]
              │                                  │
              │                          (resume_run_id ─┐
              │                           OR             │
              │                           resume_payload)│
              ▼                                  ▼
[ tailor_core.jd ] ── deterministic + LLM extractor → JobRequirements
              │           │
              │           ▼
              │   [ coverletterai.runs.resume_resolver ]
              │           - resume_payload: json.loads + validate as TailoredResume
              │           - resume_run_id : HTTP GET http://resumeai:8765/api/runs/<id>
              │                              and pull the .tailored field
              │           │
              ▼           ▼
[ tailor_core.context ] ── resume.yaml + work_history + projects + git_audit (read-only)
              │
              ▼
[ coverletterai.agent ] ── single-shot Claude cover-letter agent → TailoredCoverLetter
              │              (claude CLI subprocess, Max-subscription OAuth path)
              │              HARD RULES: no fabrication, no resume contradiction,
              │              every body paragraph echoes a real resume bullet,
              │              no cliché openings, 350-450 words total
              ▼
[ coverletterai.renderer ] ── Jinja2 LaTeX template → Tectonic → 1-page PDF
              │
              ▼
[ tailor_core.verifier ] ── text-mode LLM-judge pass (catches fabrications +
              │                resume contradictions + clichés)
              │            ── programmatic page-count check (target_max_pages=1)
              │            ── vision-mode pass (rasterise + Anthropic SDK)
              ▼
[ Run record in SQLite ] ── status, requirements, tailored letter, verification, PDF URL
[ FastAPI surface ] ── POST /api/tailor + GET /api/runs/{id} + GET /api/runs/{id}/pdf
```

The pipeline skeleton (JD fetch + parse, context load, run lifecycle, event publishing, error funnelling, vision-verification dispatch) lives in `tailor_core.runs.orchestrator.BaseOrchestrator`. This repo's `CoverLetterOrchestrator` is a four-method subclass — `_tailor` / `_render` / `_verify` / `_verify_visually` — plus an extra resume-resolver call before tailoring.

## How to test it

```bash
# 1. One-time: generate a Max-subscription OAuth token on the host.
claude setup-token         # writes the token; copy it into .env as CLAUDE_CODE_OAUTH_TOKEN

# 2. Bring up the container.
docker compose up -d

# 3a. JD-only (no resume grounding — most generic letter)
curl -X POST http://localhost:8766/api/tailor \
  -H 'Content-Type: application/json' \
  -d '{"jd_text": "<paste the JD body here>"}'

# 3b. By-ref against a resumeai run (cover letter grounded in resume bullets)
#     Requires resumeai container running on :8765 and attached to ai-tailor-network.
curl -X POST http://localhost:8766/api/tailor \
  -H 'Content-Type: application/json' \
  -d '{"jd_url": "https://au.seek.com/job/12345", "resume_run_id": "run_..."}'

# 3c. By-payload (inline tailored resume JSON — no resumeai dependency at runtime)
curl -X POST http://localhost:8766/api/tailor \
  -H 'Content-Type: application/json' \
  -d '{"jd_text": "<JD>", "resume_payload": "{\"name\": \"Jane\", ...}"}'

# 4. Poll progress
curl http://localhost:8766/api/runs/<run_id>

# 5. Download the PDF
curl -o cover-letter.pdf http://localhost:8766/api/runs/<run_id>/pdf
# or open from disk:
open runs/<run_id>/*.pdf
```

The resumeai → coverletterai chain (full integration): kick off resumeai with the JD URL, wait for it to terminal, take its `run_id`, post a coverletterai request with that `resume_run_id`. The cover letter opens by naming the hiring company and lifts specific phrasing from the just-tailored resume's bullets.

## Why these choices

- **LaTeX + Tectonic, not Google Docs / docx.** Layout decouples from content length; a longer paragraph rebuilds the document instead of shoving the layout around. Tectonic is a single-binary engine that needs zero external state.
- **`claude` CLI subprocess, not the per-token API.** Uses the Anthropic Max subscription. Auth flows through a long-lived `CLAUDE_CODE_OAUTH_TOKEN` generated once via `claude setup-token`. The vision verifier uses the Anthropic Python SDK with the same OAuth token.
- **Two resume-resolution paths, not one.** By-ref keeps `jobai`'s batch orchestration trivial (just pass the resumeai run id around) and the resumeai instance stays the source of truth. By-payload keeps coverletterai usable standalone — manual callers or a future bot that already holds the tailored resume don't need a resumeai instance running.
- **Single fixed letter style (for now).** No `template_name` settings toggle yet — one LaTeX template, one prompt. A toggle lands the day a second style materialises.
- **Separate SQLite DB from resumeai.** `~/.coverletterai/coverletterai.db`. Each app owns its data; cross-app association via run ids that `jobai` (eventually) tracks.

## Engineering bar

Same bar as the sibling repos. Staff/lead-engineer-at-a-top-tier-company, no shortcuts:

- Python 3.12, `mypy --strict`, `ruff` strict (lint + format), `from __future__ import annotations` everywhere
- TDD-first, 100% line + branch coverage on every change
- Conventional commits, granular history, GPG-signed
- CI from day one: ruff + ruff-format + mypy + pytest on every push and PR

## Quality gate (run before every commit)

```bash
./Tools/quality-gate.sh
```

That sets up a scratch venv at `/tmp/coverletterai-tools` on first run, installs the sibling `ai-tailor-core` checkout editable so live edits drive the test run, then runs `ruff check` + `ruff format --check` + `mypy` + `pytest` — the same set CI runs.

## Acknowledgements

Built with [Claude Code](https://claude.com/claude-code).
