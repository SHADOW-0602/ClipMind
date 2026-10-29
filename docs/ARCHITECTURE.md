# Architecture

ClipMind is a two-service application: a FastAPI backend that owns ingestion, AI calls, media processing, and persistence; and a Next.js App Router frontend that owns the studio experience. The backend is the only component that talks to the configured model provider.

```text
┌──────────────────────────────┐        ┌─────────────────────────────────────┐
│ Next.js studio (:3000)       │        │ FastAPI backend (:8000)             │
│                              │        │                                     │
│ dashboard / new project      │ HTTP   │ /api/projects  /api/uploads         │
│ workspace / clip studio      │───────►│ /api/jobs + SSE /api/clips          │
│ brands / usage / settings    │        │ /api/brand-profiles /api/insights   │
│ SSE + polling fallback       │        │ /api/export /api/media              │
└──────────────────────────────┘        │                                     │
                                        │  ┌───────────────────────────────┐  │
                                        │  │ PipelineRunner (in-process)   │  │
                                        │  │ ingest → transcribe →         │  │
                                        │  │ understand → select →         │  │
                                        │  │ copy/summary → render →       │  │
                                        │  │ insights                      │  │
                                        │  └──────────────┬────────────────┘  │
                                        │                 │                   │
                                        │        ┌────────▼────────┐          │
                                        │        │ Provider layer  │          │
                                        │        │ OpenAI | Meta   │          │
                                        │        └────────┬────────┘          │
                                        │                 │                   │
                                        │        ┌────────▼────────┐          │
                                        │        │ SQLite + files  │          │
                                        │        │ data/           │          │
                                        │        └─────────────────┘          │
                                        └─────────────────────────────────────┘
```

## Backend layering

| Layer | Location | Responsibility |
| --- | --- | --- |
| API | `backend/app/api/` | HTTP contracts, validation, serialization, SSE, ZIP export, media serving |
| Orchestration | `backend/app/pipeline/orchestrator.py` | Job queue, stage checkpoints, progress events, retries, resume, failure persistence |
| Pipeline | `backend/app/pipeline/` | Ingest, ASR, understanding, selection, copy, summary, render, insights |
| Providers | `backend/app/providers/` | `LLMProvider` interface, `OpenAICompatibleProvider` (Chat Completions presets), `MetaProvider` (Responses API) |
| Services | `backend/app/services/` | ASR, cache, cost accounting, prompt loading, storage safety, SRT/ASS utilities |
| Persistence | `backend/app/models.py`, `db.py` | SQLModel tables, SQLite engine, WAL mode, session scope |
| Media | `backend/app/utils/media.py` | FFmpeg/ffprobe wrappers, probing, audio extraction, frame sampling |

Prompts are versioned Markdown files in `backend/app/prompts/`, loaded through `services/prompts.py`. Brand context is serialized with `model_dump(mode="json")` so datetimes and nested values survive prompt injection.

## Request lifecycle

1. `POST /api/projects` creates a project.
2. `POST /api/projects/{id}/upload` validates the rights attestation, size, duration, and type; stores the source under `data/uploads/{project_id}/`; probes it with ffprobe; normalizes video to a browser-friendly MP4 and extracts audio.
3. `POST /api/projects/{id}/process` creates a `Job` with `options_json` and enqueues it on the in-process queue. The request returns immediately.
4. `PipelineRunner` executes stages sequentially, writing `stages_json`, `events_json`, `checkpoint_json`, and `progress` after each update.
5. The frontend opens `GET /api/jobs/{id}/events`. The endpoint replays stored events from the requested sequence and then streams new ones. `use-job-stream.ts` falls back to polling if the stream fails.
6. On completion the project status becomes `completed`; the workspace loads clips, summary, insights, and transcript.

The queue is an `asyncio.Queue` with `JOB_CONCURRENCY` workers (default 1). Jobs are intentionally not dispatched to Celery/Redis: a single process keeps the demo reproducible and removes infrastructure, at the cost of durability and horizontal scaling.

## Pipeline stages

| Stage | Weight | What happens | Hard checks |
| --- | --- | --- | --- |
| `ingest` | 8 | Probe, normalize, extract audio, sample keyframes | Duration/size limits; FFmpeg availability |
| `transcribe` | 18 | Sample ground truth, OpenAI-compatible or Meta ASR, or local faster-whisper | Segments have positive duration; words have start/end |
| `understand` | 16 | Topic segmentation with sentiment, energy, intent, quotability | JSON schema; segment times clamped to source |
| `select` | 16 | Deterministic candidates, model proposal, self-critique, validation | Quote grounded in transcript; boundaries snapped to words; non-overlap; brand scrub |
| `copy` + summary | 16 | Platform variants and source summary | Banned-word scrub; caption truncation; summary quotes grounded |
| `render` | 22 | ASS captions, 1080×1920 FFmpeg render, thumbnail, SRT | Output dimensions checked; render failure marks the clip failed |
| `insights` | 4 | Deterministic metrics + model scorecards | One scorecard per clip; scores clamped to 0–100 |

Each stage has one retry. `BudgetExceeded` is never retried; it fails the job immediately with a readable message.

### Selection and grounding

`select_clips.py` builds overlapping word windows within the requested duration range, scores them with structural signals (hook patterns, numbers, questions, filler rate, energy, keyword density), and de-duplicates overlaps. The model receives the candidates and transcript context and proposes selections. Every proposal is validated:

- `quote_is_grounded()` normalizes punctuation/case and requires the quote to appear in the transcript.
- Start/end are snapped to word boundaries and clamped to `[0, duration]`.
- Overlapping proposals are dropped.
- Banned words in titles/hooks are scrubbed; a quote containing a banned word is omitted rather than falsified.

The final clip stores `source_quote`, `score`, `rationale`, `critique_json`, and `risk_flags_json`.

### Rendering

`render.py` uses FFmpeg with a generated ASS subtitle file. ASS is used instead of SRT `force_style` because it gives deterministic font sizing and positioning at `PlayResX=1080`, `PlayResY=1920`. An SRT is still produced for download and export.

- Portrait/square sources: scale to cover and center-crop to 1080×1920.
- Landscape sources: blurred, darkened background scaled to fill, with the full frame scaled to width 1080 and centered.
- Audio-only sources: a generated dark canvas with a waveform-style visual and captions.
- The output is probed after encoding; anything other than 1080×1920 raises `MediaError`.
- Thumbnails are extracted from the rendered clip.

### Insights

`insights.py` computes deterministic metrics first: duration, word count, WPM, pause ratio, filler rate, hook delay, and per-clip structural metrics. The model then produces per-clip scores and recommendations. Scores are clamped, missing rows fall back to deterministic estimates, and the report is labeled as an estimate. The report is stored as `report_json` (the field was renamed to avoid a SQLModel shadow warning).

## Data model

```text
BrandProfile 1──* Project
Project      1──* MediaAsset 1──* Transcript
Project      1──* Clip 1──* CopyVariant
Project      1──1 Summary
Project      1──1 InsightReport
Project      1──* Job
Job          1──* ModelCall / AsrCall
MediaAsset   1──* TopicSegment
```

| Table | Key fields |
| --- | --- |
| `Project` | name, brand, status, error |
| `MediaAsset` | kind, paths, duration, dimensions, checksum, frames |
| `Transcript` | language, text, `segments_json` with word timings, provider |
| `TopicSegment` | topic, summary, sentiment, energy, intent, quotable |
| `Clip` | start/end, title/hook/quote, score, rationale, render/SRT/thumbnail paths, risk flags |
| `CopyVariant` | platform, caption, hooks, hashtags, CTA, version |
| `Summary` | TL;DR, bullets, chapters, quotes |
| `InsightReport` | full report JSON |
| `Job` | stage, status, progress, options, stages, events, checkpoint |
| `ModelCall` / `AsrCall` | tokens/audio, cost, latency, purpose, cache hit |

SQLite runs in WAL mode with foreign keys and a 5-second busy timeout. `sqlalchemy` is pinned below 2.1 for Windows environments where the 2.1 C extension is blocked by Application Control; 2.0.x falls back to pure Python.

## Storage layout

```text
data/
  clipmind.db                 SQLite database
  uploads/{project_id}/       original sources
  processed/{project_id}/     normalized MP4, extracted audio, keyframes
  renders/{project_id}/       clip MP4, ASS, SRT, JPG
  cache/                      SHA256-keyed provider response cache
  evals/                      latest eval report
```

`services/storage.py` resolves stored paths and refuses paths outside `DATA_DIR`, which protects media serving and deletion from traversal.

## Provider abstraction

`LLMProvider.generate()` accepts a system prompt, messages, optional images/video, a JSON schema, and a cache key. Both live providers return a `ModelResult` with parsed JSON, usage, cost, and latency.

- **OpenAICompatibleProvider** calls `POST /chat/completions` on the preset's base URL with Bearer auth. It requests `response_format = {"type": "json_schema", ...}` and falls back to `json_object` or no format when an endpoint rejects structured output. It retries 408/409/429/5xx with backoff, validates JSON against the schema, performs one repair pass, and records token usage. Vision input is enabled per preset and retried without images when an endpoint rejects them.
- **MetaProvider** calls `POST /responses` on `https://api.meta.ai/v1` with `Authorization: Bearer MODEL_API_KEY`. Structured output is requested with `text.format = {"type": "json_schema", "name": ..., "schema": ..., "strict": false}`. It retries 408/409/429/500/502/503/504 with backoff, validates JSON against the schema, performs one repair pass, and records token usage.
- Responses are cached by a SHA256 of model, prompt, messages, schema, image fingerprints, and explicit cache key.
- `get_provider()` is process-wide cached; `close_provider()` closes the HTTP client on FastAPI shutdown. A missing key for a key-required preset fails startup.
- Tests inject a deterministic `StubProvider` through `set_provider_override()`. It lives under `backend/tests/` and is not part of the application's selectable configuration.

### Speech-to-text strategy

1. Text uploads bypass ASR and get synthetic word timings.
2. Bundled sample media is matched by SHA256 against `backend/samples/transcripts.json` (word-level ground truth).
3. For other media, the ASR route comes from the preset or `ASR_PROVIDER`:
   - `openai_compatible` calls `/audio/transcriptions` on the provider base URL. Audio is converted to mono 16-bit PCM WAV at 16 kHz, split into ≤10-minute chunks, transcribed, and merged with offset timings.
   - `meta` uses Meta Voice Transcribe. Audio is converted to mono 16-bit PCM WAV at 24 kHz and split into ≤10-minute, ≤32 MB chunks.
   - `whisper` runs local faster-whisper.
4. If the remote ASR call fails, faster-whisper is attempted. If neither is available, the job fails with an actionable message.

## Frontend

- Next.js App Router, React 19, TypeScript, Tailwind CSS 4, Lucide icons, and shadcn-style primitives.
- Dark studio design with a lime accent; responsive sidebar and mobile drawer.
- The workspace uses a tabbed layout: Clips, Summary, Insights, Transcript. Summary/insights/transcript are only fetched once clips exist, which avoids noisy 404s during the first run.
- Clip Studio supports platform copy editing, hook variants, hashtags, CTA, trim sliders and numeric inputs, copy regeneration with direction, re-picking a different moment, save, render/re-render, downloads, and brand-safe validation errors.
- SSE is the primary progress channel; `use-job-stream.ts` falls back to polling on error and handles terminal events.
- `output: "standalone"` and security headers are configured in `next.config.ts`.

## Security and limits

- Uploads require an explicit rights attestation.
- Filenames are sanitized; stored paths are resolved inside `DATA_DIR`.
- Upload size (`MAX_UPLOAD_MB`) and duration (`MAX_DURATION_S`) are enforced.
- CORS is restricted by `CORS_ORIGINS`.
- A simple per-client write rate limit (`RATE_LIMIT_PER_MINUTE`) protects the demo API.
- Error responses do not expose API keys; `/api/system` is sanitized.
- There is no auth. A public deployment needs authentication, per-user storage, and a durable queue.

## Failure handling and resume

- Each stage is retried once; failures are persisted to `Job.error` and `Project.error` and surfaced in the UI.
- `checkpoint_json.completed_stages` prevents rerunning completed work after a restart.
- On startup, `AUTO_RESUME_JOBS=true` re-queues queued/running/retrying jobs.
- Render failures are isolated per clip: successful clips remain usable, and the job fails only if every render fails.
- Provider calls have timeouts and retries; budget failures are terminal.

## Testing

- `backend/tests/test_api.py` exercises the full text-to-clip pipeline, stage persistence, brand CRUD, banned-word rejection, copy regeneration, export, and deletion.
- `backend/tests/test_samples.py` uploads the bundled video, verifies sample-ground-truth ASR, completes the pipeline, and probes the render dimensions.
- `backend/tests/test_transcripts.py` covers word timings, SRT, quote grounding, snapping, and overlap removal.
- `backend/tests/test_config.py` covers provider presets and validation.
- `backend/tests/test_openai_compatible.py` covers the Chat Completions adapter, JSON fallback, vision toggle, and transcription parsing.
- `frontend/e2e/smoke.spec.ts` covers the dashboard, brand creation, demo pipeline, clip edit/save, and re-render in Chromium.
- `scripts/eval.py` runs 81 acceptance checks on a fresh project against a live API (80 when re-evaluating a stored project).
