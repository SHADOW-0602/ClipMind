# API Reference

Base URL: `http://localhost:8000`. Interactive OpenAPI docs: `/docs`. All request and response bodies are JSON unless noted. Errors use FastAPI's `{"detail": "..."}` shape with a 4xx/5xx status.

## System

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health`, `/api/health` | Liveness, provider preset, model, ASR route, budget |
| `GET` | `/api/system` | Sanitized runtime config for the Settings page (never secrets) |

## Projects

### Create a project

```http
POST /api/projects
Content-Type: application/json

{"name": "Weekly recording", "brand_profile_id": null}
```

Returns `ProjectRead` with `assets`, `clips`, `latest_job`, and `brand_profile`.

### List and read

- `GET /api/projects` → `ProjectListItem[]` (duration, clip count, thumbnail, status).
- `GET /api/projects/{project_id}` → `ProjectRead`.
- `PATCH /api/projects/{project_id}` → update `name` and/or `brand_profile_id`.
- `DELETE /api/projects/{project_id}` → deletes clips, transcripts, jobs, and generated files.

### Upload media or text

```http
POST /api/projects/{project_id}/upload
Content-Type: multipart/form-data

file=<video|audio>
# or
text=<pasted transcript>
rights_attested=true
kind_hint=video|audio|text
```

`rights_attested` must be true. The endpoint rejects an upload while a job is active. Limits are exposed by `GET /api/projects/{project_id}/upload/limits`.

### Start the pipeline

```http
POST /api/projects/{project_id}/process
Content-Type: application/json

{
  "n_clips": 3,
  "platforms": ["instagram", "tiktok", "linkedin"],
  "min_clip_s": 12,
  "max_clip_s": 35,
  "brand_profile_id": null,
  "regenerate": false
}
```

Returns `JobRead` immediately. Only one active job per project is allowed (`409` otherwise).

### Read results

- `GET /api/projects/{project_id}/transcript` → `TranscriptRead` with `segments_json[].words[]`.
- `GET /api/projects/{project_id}/summary` → `tldr`, `bullets`, `chapters`, `quotes`.
- `GET /api/projects/{project_id}/insights` → `{"report": {...}}`.
- `GET /api/projects/{project_id}/export` → ZIP attachment.
- `GET /api/projects/{project_id}/brand` → attached brand profile or 404.

## Jobs and SSE

- `GET /api/jobs/{job_id}` → `JobRead` (`stage`, `status`, `progress`, `stages_json`, `error`).
- `POST /api/jobs/{job_id}/retry` → re-queue a terminal job, preserving completed stages.
- `GET /api/jobs/{job_id}/events` → `text/event-stream`.

SSE events carry an `id` equal to the event sequence:

```text
id: 7
event: progress
data: {"seq":7,"type":"progress","stage":"render","message":"Rendering clip 2 of 3","progress":61.4,"ts":1761234567.2}
```

Event types: `queued`, `stage_start`, `progress`, `stage_retry`, `stage_complete`, `stage_failed`, `job_complete`, `job_failed`, `stream_end`. Use `Last-Event-ID` or `?last_event_id=N` to resume. Heartbeats are sent as SSE comments (`: heartbeat ...`). The stream ends after a terminal status.

## Clips

### Read or edit

```http
PATCH /api/clips/{clip_id}
Content-Type: application/json

{
  "start": 12.4,
  "end": 38.9,
  "title": "The real bottleneck",
  "hook": "You do not have a content problem.",
  "variants": [
    {
      "platform": "linkedin",
      "caption": "...",
      "hooks": ["..."],
      "hashtags": ["#ContentStrategy"],
      "cta": "Which part would you test first?"
    }
  ]
}
```

- Clip length must be at least 8 seconds and end within the source duration.
- Changing start/end clears the existing render and sets status to `selected`.
- Banned words in title/hook/caption/CTA/hashtags return `422` and are not persisted.
- Variants are upserted by `(clip_id, platform)` and increment `version`.

### Regenerate

```http
POST /api/clips/{clip_id}/regenerate
Content-Type: application/json

{"kind": "copy", "platform": "tiktok", "feedback": "Lead with the counterintuitive claim."}
```

`kind` is `copy` or `clip`. `clip` re-picks a different non-overlapping transcript moment using feedback keywords and clears the render. `copy` rewrites the requested platform (or all platforms) while keeping timing and quotes fixed.

### Render and delete

- `POST /api/clips/{clip_id}/render` → force a fresh 1080×1920 render; returns `ClipRead`.
- `DELETE /api/clips/{clip_id}` → removes the clip, variants, and render artifacts.

`ClipRead` includes `copy_variants`, `media_url`, `thumbnail_url`, `srt_url`, `source_quote`, `score`, `rationale`, and `risk_flags_json`.

## Brand profiles

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/brand-profiles` | List, oldest first |
| `POST` | `/api/brand-profiles` | Create |
| `GET` | `/api/brand-profiles/{id}` | Read |
| `PATCH` | `/api/brand-profiles/{id}` | Partial update |
| `DELETE` | `/api/brand-profiles/{id}` | Delete; detaches projects |

```json
{
  "name": "Systems Studio",
  "tone_description": "Direct, warm, practical.",
  "target_audience": "Independent creators",
  "voice_dos": ["Be specific"],
  "voice_donts": ["No hype"],
  "banned_words": ["revolutionary", "guaranteed"],
  "example_posts": ["Most creators do not have a content problem."]
}
```

## Usage and media

- `GET /api/usage` → token totals, ASR cost, total cost, budget, remaining budget/credits, call count.
- `GET /api/usage/calls?limit=50` → recent `ModelCall` and `AsrCall` rows.
- `GET /api/media/{stored_path}` → serves a file only if it resolves inside `DATA_DIR`.

## Demo

```http
POST /api/demo-project
Content-Type: application/json

{"brand_profile_id": null}
```

Creates a project from the bundled `demo-short.mp4` and its known transcript. It does **not** start the pipeline; call `/process` next (the UI does this automatically).

## Export contents

`GET /api/projects/{id}/export` returns a ZIP:

```text
clips/01-title.mp4
captions/01-title.srt
thumbnails/01-title.jpg
copy.csv
summary.md
insights.json
manifest.json
README.txt
```

## Status codes

| Code | Meaning |
| --- | --- |
| `400` | Missing rights attestation, missing media, invalid brand, no upload |
| `404` | Project, clip, brand, job, or media not found |
| `409` | Active job already running, or no alternate clip available |
| `413` | Upload or pasted text too large |
| `422` | Validation failure, including banned words |
| `429` | Write rate limit reached (`RATE_LIMIT_PER_MINUTE`) |
| `500` | Unexpected server error; details are logged server-side |
