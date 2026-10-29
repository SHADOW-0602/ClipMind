# Submission

ClipMind is a complete, runnable multimodal content-intelligence studio built for the Meta Model API hackathon. It runs on a live model provider and supports multiple switchable APIs; the default Groq preset is free. This page is the submission checklist, the evidence map, and the honest list of what is and is not verified.

## One-line description

ClipMind turns one long recording into transcript-grounded clips, platform-native copy, captioned 9:16 renders, summaries, and engagement insights, with brand rules and a hard model budget.

## Short description

Creators do not lack content; they lack a trustworthy way to find the publishable moment inside a long recording. ClipMind ingests video, audio, or text, builds a word-level transcript, proposes and critiques candidate moments, validates every quote and boundary against the source, writes platform-specific copy, renders 1080x1920 captioned clips, summarizes the source, and scores the result. Brand profiles enforce voice and banned words, and every model call is metered against a hard budget. ClipMind always runs against a live provider; `PROVIDER` switches between Groq, Gemini, OpenRouter, Ollama, LM Studio, Mistral, Cerebras, DeepSeek, Together, OpenAI, xAI, Fireworks, Perplexity, Meta, or a custom OpenAI-compatible endpoint.

## Submission checklist

| Deliverable | Status | Where |
| --- | --- | --- |
| Working full-stack app | Done | `backend/`, `frontend/` |
| Multi-provider live layer | Done | `backend/app/providers/openai_compatible.py`, `config.py` |
| Free default provider | Done | `PROVIDER=groq` in `.env.example` |
| Real Meta provider | Implemented, not live-tested | `backend/app/providers/meta.py` |
| Video, audio, and text ingest | Done | `backend/app/api/uploads.py`, `pipeline/ingest.py` |
| Word-level transcript | Done | `pipeline/transcribe.py`, `services/asr.py` |
| Clip selection with validation | Done | `pipeline/select_clips.py` |
| Platform copy | Done | `pipeline/generate_copy.py` |
| 9:16 captioned renders | Done | `pipeline/render.py` |
| Summary and insights | Done | `pipeline/summarize.py`, `pipeline/insights.py` |
| Export pack | Done | `api/export.py` |
| Brand profiles and banned words | Done | `api/brand.py`, `api/clips.py` |
| Cost tracking and budget guard | Done | `services/costs.py`, `providers/openai_compatible.py` |
| Demo data and one-click demo | Done | `backend/samples/`, `POST /api/demo-project` |
| Backend tests | Done, 22 passed | `backend/tests/` |
| Browser smoke test | Done, 3 passed through the Compose UI (local stub) | `frontend/e2e/smoke.spec.ts` |
| Acceptance eval | Done; 81/81 on live Groq and against a local HTTP stub | `scripts/eval.py`, [EVALS.md](EVALS.md) |
| Docker Compose | Rebuilt and verified: backend healthy, frontend HTTP 200 | `docker-compose.yml` |
| Makefile | Included | `Makefile` |
| README | Done | `README.md` |
| Architecture / API / decisions / credits | Done | `docs/` |
| `.env.example` | Done | `.env.example` |
| Demo script | Done | [DEMO.md](DEMO.md) |
| Progress log | Done | [PROGRESS.md](PROGRESS.md) |

## How a reviewer runs it

```bash
cp .env.example .env
# Add your key from https://console.groq.com/keys
# MODEL_API_KEY=gsk_...
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -e "./backend[dev]"
cd frontend && npm ci && cd ..

python scripts/dev.py
```

Open **http://localhost:3000** and click **Run the demo**.

Prerequisites: Python 3.11+, Node.js 20+, FFmpeg 6+ on `PATH`, and a free Groq API key for the default preset. Switch to `PROVIDER=ollama` or `lmstudio` for a keyless local endpoint.

To verify without the UI:

```bash
# backend
cd backend && ..\.venv\Scripts\python.exe -m pytest -q

# acceptance eval (API must be running)
cd .. && .\.venv\Scripts\python.exe scripts\eval.py

# browser smoke test (servers must be running)
cd frontend && npm run test:e2e
```

## Evidence

Latest local verification on **2026-10-29** after the provider refactor:

| Evidence | Result |
| --- | --- |
| Backend tests | 22 passed |
| Ruff / compileall | clean |
| Frontend typecheck / lint | clean |
| Production build | success, 8 app routes |
| Live provider run | Groq free tier: 3 clips, 3 rendered, 69 calls, $0.0000; Gemini chat validated with structured JSON |
| Docker Compose | rebuilt and verified: backend healthy, frontend HTTP 200 |
| Browser smoke | 3 passed through the containerized UI (local stub) |
| Acceptance eval | 81/81 on live Groq and against a local OpenAI-compatible stub (host and Compose) |

The acceptance eval writes `data/evals/latest.json`; runtime data is gitignored. The check categories and limitations are in [EVALS.md](EVALS.md).

## Judging map

### Technical execution

- **Grounded pipeline, not a prompt wrapper.** Deterministic candidate windows, model proposal, self-critique, quote grounding, word-boundary snapping, and boundary clamping. See [ARCHITECTURE.md](ARCHITECTURE.md).
- **Real media path.** FFmpeg probe/normalize, audio extraction, keyframes, ASR chunking, ASS captions, blurred landscape canvas, thumbnails, and SRT/ASS generation.
- **Provider abstraction.** One `LLMProvider` interface, an OpenAI-compatible adapter shared by most presets, and a native Meta Responses provider. The same orchestration and accounting run for every preset.
- **Structured output.** JSON schema requests, validation, one repair pass, `json_object` fallback when an endpoint rejects schemas, and deterministic fallbacks.
- **Durable-ish jobs.** Persisted stages/events/checkpoints, retry-once behavior, auto-resume on startup, SSE with polling fallback.
- **Tests that inspect artifacts.** The eval reads SRT text, probes MP4 dimensions, opens the export ZIP, and checks the usage ledger.

### Product depth

- **The full creator loop.** Ingest, transcript, selection, copy, render, summary, insights, export, brand voice, cost.
- **Review surfaces.** Per-clip rationale, source quote, score, risk flags, platform character limits, hook variants, and a transcript that seeks the source.
- **Trust properties.** A fabricated quote is replaced or dropped; banned words are rejected on generation and manual save; engagement scores are labeled estimates.
- **Cost as a feature.** Per-call ledger, cache hits, ASR seconds, budget guard, and remaining hackathon credits.
- **Brand profiles.** Tone, audience, do/don't rules, examples, and banned words flow into prompts and are enforced again in code.

### Design

- Dark studio UI with a lime accent, editorial typography, and a consistent panel system.
- Dashboard, upload flow, live pipeline rail, project workspace, clip studio, brand profiles, usage, and settings are all implemented, not static mockups.
- Responsive layouts, keyboard-accessible dialogs, visible focus states, and reduced-motion support.
- Empty, loading, error, queued, running, failed, and completed states are designed.
- Screenshots: [dashboard](images/dashboard.png), [clip studio](images/clip-studio.png).

### Use of the Meta Model API

- `PROVIDER=meta` targets current documented model IDs: `muse-spark-1.3` for reasoning/copy/summary and `muse-voice-transcribe-1.0` for speech-to-text.
- Uses the Responses API with `text.format` JSON schema output, Bearer auth, retries on 408/409/429/5xx, and a repair pass.
- Prices are configuration, not hard-coded: input, cached input, output, and ASR per hour.
- The default Groq preset and the other OpenAI-compatible presets keep the same interface, so reviewers can run the product on a free key or a local model.

### Feasibility and scale

- **Demo scale is honest.** SQLite, an in-process queue, and a single node. The README and decisions doc say so.
- **Production path is clear.** Postgres, a durable queue, object storage, auth, per-user quotas, and a render worker pool. The pipeline stages are already checkpointed and separable.
- **Cost controls are real.** A paid run cannot silently exceed `MAX_BUDGET_USD`; the call is refused with a readable error.
- **No overclaiming.** Groq was exercised live end to end and Gemini at the adapter level; the remaining vendor and scale gaps are called out below.

## What is not verified

Be explicit in the submission. These are not hidden:

1. **Other vendors and large media.** Groq's free tier was exercised end to end: demo, Whisper ASR, and 81/81 acceptance checks. Gemini's OpenAI-compatible chat was validated with structured JSON. Meta's native Responses provider, Gemini transcription (its preset uses local Whisper), Files API behavior for large video, sustained rate-limit behavior, and current paid prices remain unexercised. See the `TODO(verify)` list in [DECISIONS.md](DECISIONS.md).
2. **Docker scope.** Compose was rebuilt and verified after the provider refactor with the local stub: backend healthy, frontend HTTP 200, eval 81/81, and Playwright 3/3. The live Groq run was on the host. This covers one Windows host with Linux containers, not Kubernetes, multi-host orchestration, image scanning, or production resource limits.
3. **Arbitrary media transcription.** The bundled demo is fully grounded by its manifest. Arbitrary uploads require the configured remote ASR to succeed or local `faster-whisper` to be installed.
4. **Engagement accuracy.** Scores are structural estimates, not measured platform performance.
5. **Scale and security.** No load testing, no authentication, no multi-tenancy, no fuzzing.

## Pre-submit actions

- [x] Run the full automated suite one more time on the submission machine.
- [ ] Confirm `.env` is not committed and contains no secrets.
- [x] Confirm `data/`, `node_modules/`, `.venv/`, `.next/`, and test artifacts are ignored.
- [ ] Confirm the README quickstart works from a clean clone with a free Groq key.
- [x] Rebuild Compose after the provider refactor and run the eval and Playwright against the containerized stack (local stub).
- [ ] Run `docker compose up --build` with a real key and verify `/api/health`.
- [ ] Run one live project and the acceptance eval, then update the verification note.
- [ ] Capture a fresh screenshot if the UI changed.
- [ ] Tag the release (for example, `v0.1.0-hackathon`).

## Suggested submission copy

**Title:** ClipMind - the trustworthy clip factory for long recordings

**Tagline:** One recording in. A grounded, on-brand, captioned clip pack out.

**Description:** ClipMind ingests long video, audio, or text and builds a word-level transcript. It generates candidate moments deterministically, asks a model to propose and critique selections, then validates every quote and timestamp before anything is rendered. Each surviving clip gets platform-native copy, a 1080x1920 captioned MP4, a summary, and a structural engagement score. Brand profiles enforce voice and banned words, and every model call is metered against a hard budget. ClipMind runs on a live provider and switches between Groq, Gemini, OpenRouter, Ollama, OpenAI, Meta, and other APIs through environment configuration; the default Groq preset is free.

**Tech:** Python 3.11, FastAPI, Pydantic v2, SQLModel/SQLite, FFmpeg/libass, Next.js 16 App Router, React 19, TypeScript, Tailwind CSS 4, Playwright, Docker Compose.

**Repo:** this repository. Start with [README.md](../README.md), then [DEMO.md](DEMO.md) and [ARCHITECTURE.md](ARCHITECTURE.md).
