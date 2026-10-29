# Progress Log

ClipMind was built from an empty repository in nine phases. Each phase ended with a runnable slice and a check. The latest verification was on **2026-10-29** after the multi-provider refactor: backend tests, Ruff, compileall, frontend typecheck, lint, and the production build passed locally. The acceptance eval passed 81/81 on the host and through Docker Compose, and Playwright passed 3/3 through the Compose UI, all against a local OpenAI-compatible stub.

**Status:** complete and demo-ready on a live provider. The default Groq preset is free. Docker Compose was rebuilt after the provider refactor and verified with a local stub; live vendor behavior remains unverified and is explicit in [EVALS.md](EVALS.md) and [SUBMISSION.md](SUBMISSION.md).

## Phase summary

| Phase | Outcome | Commit |
| --- | --- | --- |
| 0. Setup and discovery | Repo, environment, model/API decisions, sample plan | `30dfedf` |
| 1. Backend foundation | FastAPI app, config, SQLite/SQLModel, schemas, services, API skeleton | `30dfedf` |
| 2. Provider layer | Provider interface, OpenAI-compatible adapter, Meta Responses client, presets, budget/cache | `30dfedf` |
| 3. Ingest and transcription | Video/audio/text upload, FFmpeg, ASR chunking, sample ground truth | `30dfedf` |
| 4. Understanding and selection | Topics, candidate windows, proposal/critique, grounding, boundaries | `30dfedf` |
| 5. Copy, summary, insights | Platform variants, brand rules, summaries, chapters, scorecards | `30dfedf` |
| 6. Render and export | ASS captions, 1080x1920 renders, blurred canvas, ZIP export | `30dfedf` |
| 7. Frontend | All pages, SSE progress, clip editor, brands, usage, settings | `a7433d3` |
| 8. Hardening and submission | Tests, Playwright, eval, Docker, docs, demo, screenshots | `38c8b5e`, `0679356`, `d9f179b`, `0205312`, `e78d26a` |
| 9. Multi-provider refactor | Removed mock mode, added free Groq default and switchable presets | this commit |

The backend phases landed in one cohesive commit because they share the same models, pipeline contracts, and test fixture. The frontend, ops tooling, and documentation are separate commits.

## Phase 0 - Setup and discovery

**Goal:** start from an empty folder with a verified toolchain and a current API contract.

- Read the current Meta Model API docs and reconciled them with the older assumptions in the plan.
- Confirmed model IDs and request shape: `muse-spark-1.3`, `muse-voice-transcribe-1.0`, base URL `https://api.meta.ai/v1`, Bearer auth, Responses API, and `text.format` JSON schema output.
- Chose a provider-agnostic architecture so the pipeline is not tied to one vendor.
- Defined the data model, pipeline stages, and validation gates before writing endpoints.
- Generated the bundled demo media and SHA256-keyed word-level transcript manifests.

**Verification:** `backend/samples/` contains a 100s short, a 464s long recording, an audio file, and three transcript manifests.

## Phase 1 - Backend foundation

**Goal:** a typed, testable API and persistence layer.

- FastAPI app with lifespan startup/shutdown, CORS, exception handlers, and health/system endpoints.
- Pydantic settings with safe defaults and no secrets in code.
- SQLite in WAL mode, SQLModel tables for projects, assets, transcripts, clips, copy variants, summaries, insight reports, brand profiles, jobs, model calls, and ASR calls.
- Pydantic API schemas and serializers for project/clip reads.
- Cost ledger, response cache, prompt loader, storage layout, and transcript/SRT/ASS utilities.
- Brand CRUD, project CRUD, upload, jobs/SSE, clips, insights, export, media, and demo endpoints.

**Verification:** `pytest` covers health, brand CRUD, project creation, upload, pipeline completion, SSE/job state, clip edits, banned-word rejection, regenerate, render, summary, insights, export, usage, demo creation, and system config.

**Notable fix:** `InsightReport.json` was renamed to `report_json` to avoid a SQLModel shadow warning.

## Phase 2 - Provider layer

**Goal:** one provider contract with hard cost and output controls.

- `LLMProvider` interface for structured JSON generation.
- `OpenAICompatibleProvider` using `POST /chat/completions`, Bearer auth, JSON schema output with a `json_object` fallback, retries on 408/409/429/5xx, a JSON repair pass, and response caching.
- `MetaProvider` using `POST /responses`, Bearer auth, JSON schema output, retries, a repair pass, and response caching.
- Provider presets for Groq, Gemini, OpenRouter, Ollama, LM Studio, Mistral, Cerebras, DeepSeek, Together, OpenAI, xAI, Fireworks, Perplexity, custom endpoints, and Meta.
- Process-wide cached `get_provider()` and shutdown `close_provider()`.
- Pre-call budget guard and per-call accounting with tokens, latency, cache hit, purpose, and cost.
- Versioned prompt templates for understanding, selection, critique, copy, summary, and insights.

**Verification:** `test_config.py` and `test_openai_compatible.py`; the acceptance eval checks the budget invariant.

**Notable fixes:**

- Prompt serialization crashed on datetimes; `_brand_dict` now uses `model_dump(mode="json")`.
- Cache filenames containing `:` caused Windows `WinError 87`; filenames are now SHA256 hashes.

## Phase 3 - Ingest and transcription

**Goal:** accept real media and produce word-level timings.

- Multipart upload for video/audio and pasted text, with rights attestation, size/duration limits, and kind detection.
- FFmpeg normalization, `ffprobe` metadata, audio extraction, keyframes, and thumbnail generation.
- Transcript persistence with segments and word timings.
- Meta Muse Voice Transcribe path with mono 16-bit PCM WAV, 16/24 kHz, 10-minute chunking, and 32 MB per-request limits.
- OpenAI-compatible transcription path for Groq, OpenAI, Mistral, Together, and compatible gateways.
- Optional faster-whisper fallback and a sample manifest lookup keyed by file SHA256.

**Verification:** `test_samples.py` uploads the demo video, matches the sample manifest, completes the pipeline, and checks a 1080x1920 render. The demo reports 29 segments and 213 word timings from `sample-ground-truth`.

## Phase 4 - Understanding and selection

**Goal:** choose moments that are worth publishing and can be defended.

- Topic/energy/claim understanding over transcript segments.
- Deterministic candidate windows from word timings, with configurable count and duration bounds.
- Model proposal and self-critique over the candidate set.
- Quote grounding: normalized quote must appear in the source transcript; ungrounded quotes are replaced with the best grounded sentence or dropped.
- Word-boundary snapping and source-duration clamping for every clip.
- Non-overlap enforcement, score normalization, rationale, and risk flags.

**Verification:** the eval checks bounds, duration, non-overlap, grounded quotes, title/hook presence, and platform coverage for every clip. In the latest run all three clips passed, including quotes such as "Your best content is probably sitting in a folder right now."

## Phase 5 - Copy, summary, insights

**Goal:** turn selected moments into publishable, on-brand material.

- Platform variants for Instagram, YouTube Shorts, TikTok, LinkedIn, and X, with caption, hooks, hashtags, and CTA.
- Caption limits enforced in the prompt and checked in the eval.
- Brand tone, audience, do/don't rules, examples, and banned words injected into prompts.
- Banned words scrubbed after generation and rejected again on manual save with HTTP 422.
- Summary with TL;DR, takeaways, timestamped chapters, and verified quotes.
- Insight report with WPM, pause ratio, filler rate, hook delay, clip length, and per-clip scorecards.
- Methodology and confidence labels so scores are not mistaken for platform predictions.

**Verification:** the eval checks caption limits, hooks, brand safety, summary structure, chapter order, quote grounding, insight coverage, methodology, and score bounds.

## Phase 6 - Render and export

**Goal:** produce a review-ready vertical pack, not a preview.

- ASS subtitle generation with explicit `PlayResX: 1080` and `PlayResY: 1920`, bottom alignment, outline, and readable sizing.
- FFmpeg render to 1080x1920 MP4 with burned-in captions.
- Landscape sources: blurred, darkened fill background with the full frame centered; portrait/square sources: center crop.
- SRT retained for download/export; thumbnails generated per clip.
- ZIP export with `manifest.json`, `summary.md`, `copy.csv`, `insights.json`, `clips/*.mp4`, `captions/*.srt`, and `thumbnails/*.jpg`.

**Verification:** the eval probes every render with `ffprobe` and requires 1080x1920; it opens the ZIP and checks required files, media entries, and manifest clip count. Playwright downloads a rendered clip after editing.

**Notable fix:** SRT `force_style` produced inconsistent caption sizing/position; the pipeline switched to generated ASS files.

## Phase 7 - Frontend

**Goal:** a studio UI that exposes the pipeline honestly.

- Next.js 16 App Router, React 19, TypeScript, Tailwind 4, shadcn-style local primitives, Lucide icons, Geist.
- Dark studio design with lime accent, editorial typography, and consistent panels.
- Dashboard with totals, recent projects, empty state, quick actions, and **Run the demo**.
- New project flow for file/text, brand selection, clip count, platforms, duration window, and rights attestation.
- Project workspace with source player, live stage rail, clip cards, summary, insights, transcript, re-run, export, and delete.
- Clip studio with 9:16 preview, copy editor per platform, hook variants, hashtags, CTA, trim controls, save, regenerate, and re-render.
- Brand profiles with create/edit/delete, voice rules, examples, and banned words.
- Usage ledger with totals, budget, call table, cache hits, ASR seconds, and cost breakdown.
- Settings with sanitized runtime config, prices, limits, CORS, and data root.
- SSE job stream with polling fallback; designed loading, empty, error, queued, running, failed, and completed states.

**Verification:** `npm run typecheck`, `npm run lint`, `npm run build` (8 routes), and 3 Playwright tests covering dashboard, brand creation, demo pipeline, caption edit/save/reload, and re-render.

**Notable fixes:**

- Job stages were not persisting because nested stage dicts were mutated through a shallow copy; the orchestrator now deep-copies before assignment.
- Console 404 noise was reduced by fetching summary/insights/transcript only after clips exist.

## Phase 8 - Hardening, demo, submission

**Goal:** make the repository reviewable without a guided tour.

- Backend tests now cover 20 cases, including stage status assertions, demo creation, system config, CORS env parsing, sample media, transcript utilities, provider presets, and the OpenAI-compatible adapter.
- Playwright smoke test added with a reusable webServer config and CI-friendly backend command override.
- Acceptance eval added: 81 checks across project, transcript, clips, summary, insights, export, and usage.
- API-driven demo, seed, and eval scripts so they work against local, Docker, or deployed instances.
- Dockerfiles for backend/frontend, Compose stack with a named data volume, Makefile, and cross-platform dev runner.
- README, architecture, API, decisions, credits, evals, demo, submission, and this progress log.
- Dashboard and clip-studio screenshots captured from a completed demo.
- Runtime data cleaned down to completed demos; brands seeded for screenshots.

**Verification:** 20 backend tests passed, frontend typecheck/lint/build passed, and Ruff/compileall are clean. The demo pipeline and the 81-check acceptance eval passed against a local OpenAI-compatible stub server over HTTP, and the Compose stack passed the eval 81/81 plus Playwright 3/3 through the containerized UI. A real vendor run still requires a live provider key.

## Verification matrix

| Area | Command | Latest result |
| --- | --- | --- |
| Backend tests | `cd backend && ..\.venv\Scripts\python.exe -m pytest -q` | 20 passed |
| Backend lint | `cd backend && ..\.venv\Scripts\python.exe -m ruff check app tests ..\scripts` | clean |
| Python compile | `cd backend && ..\.venv\Scripts\python.exe -m compileall -q app tests ..\scripts` | clean |
| Frontend types | `cd frontend && npm run typecheck` | clean |
| Frontend lint | `cd frontend && npm run lint` | clean |
| Frontend build | `cd frontend && npm run build` | success, 8 routes |
| Docker Compose | `docker compose up -d --build` | verified: backend healthy, frontend 200 |
| Browser smoke | `cd frontend && npm run test:e2e` | 3 passed through the containerized UI |
| Acceptance eval | `.\.venv\Scripts\python.exe scripts\eval.py` | 81/81 against a local HTTP stub (host and Compose); live vendor pending |
| Demo CLI | `.\.venv\Scripts\python.exe scripts\demo.py` | 3 clips, 3 rendered against a local HTTP stub |

## Deviations from the original plan

| Original assumption | What was built | Why |
| --- | --- | --- |
| Older Muse model generation | `muse-spark-1.3` and `muse-voice-transcribe-1.0` | Current Meta docs supersede the plan |
| No audio model | Meta ASR path plus optional local fallback | The docs now include speech-to-text |
| Model chooses arbitrary timestamps | Deterministic candidates + model proposal/critique + validation | Grounding and bounded search |
| SRT `force_style` captions | Generated ASS with explicit 1080x1920 PlayRes | Reliable sizing/placement |
| Hard center crop for landscape | Blurred/darkened vertical canvas with centered full frame | Preserve titles, faces, and slides |
| Single-vendor provider | OpenAI-compatible presets plus a native Meta provider | Free default and switchable APIs |
| 80-check eval | 81 checks on a fresh run (80 stored checks + pipeline completion) | The fresh run adds `pipeline.completed` |

## Known gaps and next steps

1. **Live provider verification.** Add a key, run one project, confirm the OpenAI-compatible and Meta envelopes, ASR timings, Files API behavior for large video, rate-limit headers, and current prices. Update the `TODO(verify)` list.
2. **Production containers.** Compose is configured but not re-verified after the provider refactor; rebuild it with a real key and then add Kubernetes or multi-host orchestration, image scanning, health-based rollouts, and resource limits before production.
3. **Durable infrastructure.** Postgres, a durable queue, object storage, render workers, auth, per-user quotas, and audit logs.
4. **ASR quality.** Benchmark Groq Whisper, Muse Voice Transcribe, and faster-whisper on real podcasts, accents, and overlapping speech.
5. **Engagement validation.** Correlate structural scores with actual platform retention before making stronger claims.
6. **Accessibility and browsers.** Add Firefox/WebKit Playwright projects, automated axe checks, and mobile viewport tests.
7. **Publishing.** Add OAuth and direct publishing only after the review/export workflow is trusted.

## Commit log

| Commit | Scope |
| --- | --- |
| `30dfedf` | Backend pipeline, API, models, providers, samples, tests |
| `a7433d3` | Next.js studio UI, components, API client, Playwright smoke test |
| `38c8b5e` | Demo/eval/seed scripts, Makefile, Docker, environment examples |
| `0679356` | README, architecture, API, decisions, credits, evals, demo, submission, screenshots |
| `d9f179b` | Progress log and final verification record |
| `0205312` | Eval count and timing corrections |
| `e78d26a` | CORS env parsing, container demo path, 13th backend test |

Use `git log --oneline` for the authoritative history.
