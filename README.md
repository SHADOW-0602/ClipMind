# ClipMind

**Turn one long recording into a publishable clip pack — transcript-grounded, on-brand, and cost-aware.**

ClipMind is a full-stack multimodal content-intelligence studio. Upload a long video, audio file, or pasted transcript. ClipMind produces a word-level transcript, selects the strongest moments, writes platform-native copy, renders 9:16 captioned clips, summarizes the source, and scores the result — with a brand voice and a hard budget guard.

ClipMind always runs against a live model provider. The default preset is **Groq's free tier** — OpenAI-compatible chat plus Whisper transcription with one key. The same code switches to Gemini, OpenRouter, Ollama, LM Studio, Mistral, Cerebras, OpenAI, Meta, or any custom OpenAI-compatible endpoint through environment variables.

![ClipMind dashboard](docs/images/dashboard.png)

## What is in the box

- **Ingest** — video, audio, and pasted text; FFmpeg normalization, metadata probe, keyframes, duration/size limits, rights attestation.
- **Word-level transcript** — provider ASR (Groq Whisper, Mistral Voxtral, OpenAI Whisper, or Meta Voice Transcribe), optional local faster-whisper, or bundled sample ground truth.
- **Grounded clip selection** — deterministic candidate scoring + model proposal + self-critique + quote/boundary validation. A clip cannot survive with an invented quote or an out-of-range timestamp.
- **Platform copy** — Instagram, YouTube Shorts, TikTok, LinkedIn, and X variants with hooks, hashtags, and CTAs; brand tone, audience, examples, and banned words are enforced at generation and on every manual save.
- **Vertical renders** — 1080×1920 MP4 with burned-in ASS captions; landscape sources get a blurred, darkened canvas and a centered full frame; SRT and thumbnails included.
- **Summaries and insights** — TL;DR, takeaways, chapters, verified quotes, structural metrics (WPM, pauses, filler rate), and per-clip scorecards with honest confidence labels.
- **Studio UI** — dashboard, upload flow, live SSE pipeline progress, project workspace, clip editor with trim/copy/regenerate/re-render, brand profiles, usage/cost ledger, and settings.
- **Export** — one ZIP with rendered clips, SRTs, thumbnails, `copy.csv`, `summary.md`, `insights.json`, and a manifest.
- **Cost tracking** — every model and ASR call is metered against `MAX_BUDGET_USD`; cached calls are tracked separately.
- **Ops** — Docker Compose, Makefile, pytest, Playwright smoke test, demo seeder, and an 81-check acceptance eval.

## Quickstart (free tier)

**Prerequisites:** Python 3.11+, Node.js 20+, FFmpeg 6+ on `PATH`. Windows, macOS, and Linux are supported. A free Groq API key is required for the default preset.

```bash
cp .env.example .env
# Put your key from https://console.groq.com/keys in .env:
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

Open **http://localhost:3000**. Click **Run the demo** on the dashboard, or run the demo from the CLI:

```bash
python scripts/demo.py
```

The demo uses a bundled 100-second recording with a SHA256-keyed, word-level ground-truth transcript, so the sample skips ASR. The reasoning, selection, copy, summary, and insights stages call the configured provider and consume your free-tier quota.

If `python scripts/dev.py` is not convenient, run the two services in separate terminals:

```bash
# terminal 1
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# terminal 2
cd frontend
npm run dev
```

## Switch providers

`PROVIDER` selects a preset. A preset fills `LLM_BASE_URL`, `LLM_MODEL`, `LLM_ASR_MODEL`, vision support, and prices, but any value you set explicitly in `.env` still wins.

| Preset | Text model | Transcription | Cost |
| --- | --- | --- | --- |
| `groq` (default) | `openai/gpt-oss-120b` | Groq Whisper | Free tier |
| `gemini` | `gemini-2.5-flash` | local Whisper | Free tier |
| `openrouter` | `meta-llama/llama-3.3-70b-instruct:free` | local Whisper | Free models |
| `ollama` | `llama3.2` | local Whisper | Local |
| `lmstudio` | `local-model` | local Whisper | Local |
| `mistral` | `mistral-small-latest` | Voxtral | Free tier |
| `cerebras` | `llama-3.3-70b` | local Whisper | Free tier |
| `deepseek` | `deepseek-chat` | local Whisper | Paid |
| `together` | Llama 3.3 70B Turbo | Whisper Large v3 | Paid |
| `openai` / `openai_compatible` | `gpt-4o-mini` | `whisper-1` | Paid |
| `xai`, `fireworks`, `perplexity` | provider default | local Whisper | Paid |
| `custom` | your `LLM_MODEL` | your choice | Your endpoint |
| `meta` | `muse-spark-1.3` | Meta Voice Transcribe | Paid |

Example: switch to a fully local setup with no key.

```dotenv
PROVIDER=ollama
# LLM_BASE_URL=http://localhost:11434/v1
# LLM_MODEL=llama3.2
```

Example: use Gemini's free tier, with local Whisper handling transcription.

```dotenv
PROVIDER=gemini
MODEL_API_KEY=your_google_ai_studio_key
```

For any other OpenAI-compatible endpoint, use `PROVIDER=custom` and set both `LLM_BASE_URL` and `LLM_MODEL`. `custom` defaults transcription to local Whisper; set `ASR_PROVIDER=openai_compatible` and `LLM_ASR_MODEL` to use the endpoint's `/audio/transcriptions` route. The adapter uses Chat Completions with JSON-schema output, falls back to `json_object` when an endpoint rejects structured output, retries on 408/409/429/5xx, repairs malformed JSON, caches responses, and checks the budget before each call. See [docs/DECISIONS.md](docs/DECISIONS.md) for provider decisions.

> **Verification note:** the OpenAI-compatible adapter passed an end-to-end HTTP smoke test against a local stub server, including the 81-check acceptance eval. Vendor endpoints (Groq, Gemini, OpenRouter, OpenAI, Meta, and others) have not been exercised with a real key in this repository. Run `python scripts/demo.py` with your key before claiming live-vendor verification.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

- UI: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

The backend container includes FFmpeg and the bundled demo samples, and stores runtime data in the `clipmind-data` volume. Compose reads the repository-root `.env`, so set `MODEL_API_KEY` there before starting. The stack was rebuilt after the multi-provider refactor and verified with a local OpenAI-compatible stub: backend healthy, frontend HTTP 200, acceptance eval 81/81, and Playwright 3/3 through the containerized UI. The host was also verified against live Groq: demo 3 clips/3 rendered/69 calls, acceptance eval 81/81. The container has not yet been rerun against a live vendor key. To reset everything:

```bash
docker compose down -v
```

To build the frontend for a non-local API URL, set `NEXT_PUBLIC_API_URL` before `docker compose build` (it is compiled into the browser bundle).

## How the pipeline works

```text
upload ──► ingest ──► transcribe ──► understand ──► select ──► copy + summary ──► render ──► insights
             │            │              │             │             │                │            │
        normalize,     word-level     topics +      grounded      platform      1080×1920     metrics +
        probe, frames  timings        energy        candidates    variants      captions      scorecards
                                                         │
                                                  quote + boundary
                                                  + brand validation
```

Stages are persisted as JSON checkpoints. A failed stage retries once, then fails the job with a readable error. Interrupted jobs are re-queued on startup (`AUTO_RESUME_JOBS=true`), and completed stages are not repeated. The frontend consumes server-sent events at `/api/jobs/{id}/events` and falls back to polling if SSE drops.

### Grounding and safety

- Candidate moments are generated deterministically from transcript words, then a model proposes and critiques selections.
- Every quote is checked against the source transcript. An ungrounded quote is corrected or dropped; it is never presented as verbatim.
- Clip boundaries snap to word timings and are clamped to the source duration.
- Banned words are checked with whole-word, case-insensitive matching on generation and on manual edits. Violations return `422` and do not persist.
- Risky language produces review flags rather than silent approval.
- Engagement scores are explicitly labeled as modeled estimates, not platform guarantees.

### Cost controls

- Prices are configuration, not hard-coded in prompts: `LLM_INPUT_PRICE_PER_M`, `LLM_CACHED_INPUT_PRICE_PER_M`, `LLM_OUTPUT_PRICE_PER_M`, and `LLM_ASR_USD_PER_HOUR` (or the `META_*` equivalents for `PROVIDER=meta`).
- `MAX_BUDGET_USD` is checked before each model call and during ASR. A run stops with `BudgetExceeded` rather than overspending.
- Every call is stored in SQLite with tokens, latency, cache hit, purpose, and cost. The Usage page and `/api/usage` expose totals, remaining budget, and remaining hackathon credits.
- Free-tier presets report `$0` until you set list prices, so the budget guard cannot protect a paid account accidentally configured as free.

## Acceptance checks

```bash
# Backend: API, pipeline, sample media, grounding, captions
cd backend
..\.venv\Scripts\python.exe -m pytest -q

# Frontend: types, lint, production build
cd frontend
npm run typecheck
npm run lint
npm run build

# Browser smoke test (backend + frontend running)
npm run test:e2e

# End-to-end acceptance eval, writes data/evals/latest.json
cd ..
.\.venv\Scripts\python.exe scripts\eval.py
```

The eval checks the full acceptance contract on a fresh run, including word timings, quote grounding, clip bounds and non-overlap, platform coverage, caption limits, brand safety, 1080×1920 renders, SRT contents, summary quote grounding, insight coverage, export contents, and non-negative cost accounting. See [docs/EVALS.md](docs/EVALS.md) for the latest result.

## Project layout

```text
backend/
  app/
    api/            projects, uploads, jobs/SSE, clips, brands, insights, export, media
    pipeline/       ingest, transcribe, understand, select, copy, summary, render, insights, orchestrator
    providers/      provider interface, OpenAI-compatible adapter, Meta Responses API
    services/       ASR, cache, costs, prompts, storage, transcript/SRT/ASS utilities
    prompts/        versioned prompt templates
    models.py       SQLModel tables
    schemas.py      Pydantic API contracts
  samples/          demo media + SHA256-keyed word-level transcripts
  tests/            pytest acceptance and unit tests
frontend/
  src/app/          dashboard, new project, workspace, clip studio, brands, usage, settings
  src/components/   studio shell, upload, pipeline progress, clip cards, panels, UI primitives
  src/hooks/        SSE job stream with polling fallback
  e2e/              Playwright smoke test
scripts/            dev, demo, seed, eval, sample generation, API helpers
docs/               architecture, API, decisions, credits, evals, progress, demo, submission
```

## Configuration

Copy `.env.example` to `.env`. The most important settings:

| Variable | Default | Meaning |
| --- | --- | --- |
| `PROVIDER` | `groq` | Preset: `groq`, `gemini`, `openrouter`, `ollama`, `lmstudio`, `mistral`, `cerebras`, `deepseek`, `together`, `openai`, `openai_compatible`, `xai`, `fireworks`, `perplexity`, `custom`, `meta` |
| `MODEL_API_KEY` | empty | Shared provider key. Required for key-required presets |
| `LLM_BASE_URL` | preset | OpenAI-compatible endpoint |
| `LLM_MODEL` | preset | Reasoning, selection, copy, summary, insights |
| `LLM_ASR_MODEL` | preset | Remote speech-to-text model |
| `LLM_REASONING_EFFORT` | preset | `low`, `medium`, or `high`; sent only when set |
| `ASR_PROVIDER` | `auto` | `auto`, `openai_compatible`, `meta`, or `whisper` |
| `MAX_BUDGET_USD` | `100` | Hard spend ceiling |
| `DATA_DIR` | `./data` | Uploads, processed media, renders, cache, SQLite |
| `MAX_UPLOAD_MB` | `500` | Upload size limit |
| `MAX_DURATION_S` | `7200` | Source duration limit |
| `JOB_CONCURRENCY` | `1` | In-process worker count |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Allowed browser origins |
| `PUBLIC_API_URL` | `http://localhost:8000` | Base URL used in API-returned media links |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Browser-visible API URL |

See `.env.example` for the complete list, including Meta settings, local Whisper, and rate limiting.

## API

Interactive docs: **http://localhost:8000/docs**. A concise endpoint reference with SSE examples is in [docs/API.md](docs/API.md).

Core endpoints:

- `POST /api/projects`, `GET /api/projects`, `GET/PATCH/DELETE /api/projects/{id}`
- `POST /api/projects/{id}/upload` (multipart file or pasted text)
- `POST /api/projects/{id}/process`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/events`
- `GET /api/projects/{id}/transcript|summary|insights|export`
- `GET/PATCH /api/clips/{id}`, `POST /api/clips/{id}/regenerate|render`
- `GET/POST /api/brand-profiles`, `GET/PATCH/DELETE /api/brand-profiles/{id}`
- `GET /api/usage`, `GET /api/usage/calls`, `GET /api/system`, `GET /api/health`
- `POST /api/demo-project` (one-click demo source)

## Docs

- [Architecture](docs/ARCHITECTURE.md) — components, data model, pipeline, failure handling.
- [API reference](docs/API.md) — requests, responses, SSE, export.
- [Decisions](docs/DECISIONS.md) — what was chosen and why, including unresolved `TODO(verify)` items.
- [Credits](docs/CREDITS.md) — references, learned patterns, and dependency notes.
- [Evals](docs/EVALS.md) — what is checked, latest results, and limitations.
- [Progress](docs/PROGRESS.md) — phase-by-phase build log.
- [Demo script](docs/DEMO.md) — a three-minute walkthrough and preflight checklist.
- [Submission](docs/SUBMISSION.md) — final checklist and judging map.

## Known limitations

- The job queue is in-process and single-node; it is correct for a demo but not a durable distributed queue.
- There is no authentication or multi-tenancy. Do not expose a production deployment without adding both.
- Local Whisper is optional. Install `faster-whisper` with `pip install -e "./backend[whisper]"` when a preset uses local transcription or when remote ASR fails.
- The OpenAI-compatible adapter is exercised over HTTP against a local stub, but no vendor endpoint has been smoke-tested with a real key in this repository; run the demo with your key before claiming live-vendor verification.
- Rendering is CPU-bound and serialized by `JOB_CONCURRENCY=1` by default.
- Engagement predictions are estimates from transcript structure, not platform telemetry.
- Publishing to social platforms is intentionally out of scope; ClipMind exports a review-ready pack.

## Credits

ClipMind was built for the Meta Model API hackathon. The provider layer supports Meta's Responses API plus any OpenAI-compatible Chat Completions endpoint. Model IDs and request shapes follow each provider's current documentation, and learned patterns and references are documented in [docs/CREDITS.md](docs/CREDITS.md). No reference-project code was copied. Demo media and transcripts were generated locally for this repository.
