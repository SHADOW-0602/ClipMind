# Submission

ClipMind is a complete, runnable multimodal content-intelligence studio built for the Meta Model API hackathon. This page is the submission checklist, the evidence map, and the honest list of what is and is not verified.

## One-line description

ClipMind turns one long recording into transcript-grounded clips, platform-native copy, captioned 9:16 renders, summaries, and engagement insights, with brand rules and a hard model budget.

## Short description

Creators do not lack content; they lack a trustworthy way to find the publishable moment inside a long recording. ClipMind ingests video, audio, or text, builds a word-level transcript, proposes and critiques candidate moments, validates every quote and boundary against the source, writes platform-specific copy, renders 1080x1920 captioned clips, summarizes the source, and scores the result. Brand profiles enforce voice and banned words, and every model call is metered against a hard budget. The whole product runs offline in mock mode at $0; switching to the Meta Model API is an environment change.

## Submission checklist

| Deliverable | Status | Where |
| --- | --- | --- |
| Working full-stack app | Done | `backend/`, `frontend/` |
| Mock mode, end to end, $0 | Done | `.env.example`, `backend/app/providers/mock.py` |
| Real Meta provider | Implemented, not live-tested | `backend/app/providers/meta.py` |
| Video, audio, and text ingest | Done | `backend/app/api/uploads.py`, `pipeline/ingest.py` |
| Word-level transcript | Done | `pipeline/transcribe.py`, `services/asr.py` |
| Clip selection with validation | Done | `pipeline/select_clips.py` |
| Platform copy | Done | `pipeline/generate_copy.py` |
| 9:16 captioned renders | Done | `pipeline/render.py` |
| Summary and insights | Done | `pipeline/summarize.py`, `pipeline/insights.py` |
| Export pack | Done | `api/export.py` |
| Brand profiles and banned words | Done | `api/brand.py`, `api/clips.py` |
| Cost tracking and budget guard | Done | `services/costs.py`, `providers/meta.py` |
| Demo data and one-click demo | Done | `backend/samples/`, `POST /api/demo-project` |
| Backend tests | Done, 12 passed | `backend/tests/` |
| Browser smoke test | Done, 3 passed | `frontend/e2e/smoke.spec.ts` |
| Acceptance eval | Done, 81/81 | `scripts/eval.py`, [EVALS.md](EVALS.md) |
| Docker Compose | Included, not built here | `docker-compose.yml` |
| Makefile | Included | `Makefile` |
| README | Done | `README.md` |
| Architecture / API / decisions / credits | Done | `docs/` |
| `.env.example` | Done | `.env.example` |
| Demo script | Done | [DEMO.md](DEMO.md) |
| Progress log | Done | [PROGRESS.md](PROGRESS.md) |

## How a reviewer runs it

```bash
cp .env.example .env
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

Prerequisites: Python 3.11+, Node.js 20+, FFmpeg 6+ on `PATH`. No API key is required. The default `.env.example` is mock mode.

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

Latest local run on **2026-10-23**:

| Evidence | Result |
| --- | --- |
| Backend tests | 12 passed |
| Ruff / compileall | clean |
| Frontend typecheck / lint | clean |
| Production build | success, 8 app routes |
| Playwright smoke | 3 passed |
| Acceptance eval | 81/81 passed, 0 failed |
| Demo project | `683b1a3d8e574568bf14840da1544af7` |
| Demo source | 100.374s, word-level ground truth, 213 word timings |
| Renders | 3 clips at 1080x1920 |
| Model spend | $0.0000 in mock mode |
| Export | manifest, summary, CSV, insights, MP4s, SRTs, thumbnails |

The acceptance eval writes `data/evals/latest.json`; runtime data is gitignored. The check categories and limitations are in [EVALS.md](EVALS.md).

## Judging map

### Technical execution

- **Grounded pipeline, not a prompt wrapper.** Deterministic candidate windows, model proposal, self-critique, quote grounding, word-boundary snapping, and boundary clamping. See [ARCHITECTURE.md](ARCHITECTURE.md).
- **Real media path.** FFmpeg probe/normalize, audio extraction, keyframes, ASR chunking, ASS captions, blurred landscape canvas, thumbnails, and SRT/ASS generation.
- **Provider abstraction.** One interface for mock and Meta, selected by `get_provider()`. The same orchestration and accounting run in both modes.
- **Structured output.** JSON schema requests, validation, one repair pass, and deterministic fallbacks.
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
- Dashboard, upload flow, live pipeline rail, project workspace, clip studio, brand profiles, usage, and settings are all implemented, not mocked screens.
- Responsive layouts, keyboard-accessible dialogs, visible focus states, and reduced-motion support.
- Empty, loading, error, queued, running, failed, and completed states are designed.
- Screenshots: [dashboard](images/dashboard.png), [clip studio](images/clip-studio.png).

### Use of the Meta Model API

- Targets current documented model IDs: `muse-spark-1.3` for reasoning/copy/summary and `muse-voice-transcribe-1.0` for speech-to-text.
- Uses the Responses API with `text.format` JSON schema output, Bearer auth, retries on 408/409/429/5xx, and a repair pass.
- Prices are configuration, not hard-coded: input, cached input, output, and ASR per hour.
- The mock provider is a first-class implementation of the same interface, so reviewers can exercise the product without a key.

### Feasibility and scale

- **Demo scale is honest.** SQLite, an in-process queue, and a single node. The README and decisions doc say so.
- **Production path is clear.** Postgres, a durable queue, object storage, auth, per-user quotas, and a render worker pool. The pipeline stages are already checkpointed and separable.
- **Cost controls are real.** A paid run cannot silently exceed `MAX_BUDGET_USD`; the call is refused with a readable error.
- **No overclaiming.** Live Meta behavior and Docker were not verified in this environment; both are called out below.

## What is not verified

Be explicit in the submission. These are not hidden:

1. **Live Meta API.** No real key was available. The Meta provider is implemented from current docs, but the request/response envelope, ASR word timings, Files API behavior for large video, rate-limit headers, and current prices have not been exercised against `api.meta.ai`. See the `TODO(verify)` list in [DECISIONS.md](DECISIONS.md).
2. **Docker.** The Dockerfiles and Compose file are included, but this Windows environment did not run `docker compose up --build`. Treat the container path as untested until it is run on the target machine.
3. **Arbitrary media in mock mode.** The bundled demo is fully grounded. An arbitrary upload in mock mode uses a canned transcript unless its SHA256 matches a sample manifest or `FORCE_WHISPER=true` with faster-whisper installed.
4. **Engagement accuracy.** Scores are structural estimates, not measured platform performance.
5. **Scale and security.** No load testing, no authentication, no multi-tenancy, no fuzzing.

## Pre-submit actions

- [ ] Run the full acceptance suite one more time on the submission machine.
- [ ] Confirm `.env` is not committed and contains no secrets.
- [ ] Confirm `data/`, `node_modules/`, `.venv/`, `.next/`, and test artifacts are ignored.
- [ ] Confirm the README quickstart works from a clean clone.
- [ ] If Docker is available, run `docker compose up --build` and click through the demo.
- [ ] If a Meta key is available, run one live project and update the verification note; otherwise keep the honest limitation.
- [ ] Capture a fresh screenshot if the UI changed.
- [ ] Tag the release (for example, `v0.1.0-hackathon`).

## Suggested submission copy

**Title:** ClipMind - the trustworthy clip factory for long recordings

**Tagline:** One recording in. A grounded, on-brand, captioned clip pack out.

**Description:** ClipMind ingests long video, audio, or text and builds a word-level transcript. It generates candidate moments deterministically, asks a model to propose and critique selections, then validates every quote and timestamp before anything is rendered. Each surviving clip gets platform-native copy, a 1080x1920 captioned MP4, a summary, and a structural engagement score. Brand profiles enforce voice and banned words, and every model call is metered against a hard budget. The entire product runs offline in mock mode at $0; switching to the Meta Model API is an environment change.

**Tech:** Python 3.11, FastAPI, Pydantic v2, SQLModel/SQLite, FFmpeg/libass, Next.js 16 App Router, React 19, TypeScript, Tailwind CSS 4, Playwright, Docker Compose.

**Repo:** this repository. Start with [README.md](../README.md), then [DEMO.md](DEMO.md) and [ARCHITECTURE.md](ARCHITECTURE.md).
