# Evaluation

ClipMind is checked at three levels: deterministic backend tests, a browser smoke test of the real UI, and an end-to-end acceptance eval that inspects the artifacts produced by the pipeline.

The latest run was on **2026-10-23** against the local mock-mode stack. It passed **81/81** acceptance checks, **12/12** backend tests, and **3/3** Playwright tests. No live Meta API calls were made.

## Latest results

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `cd backend && ..\.venv\Scripts\python.exe -m pytest -q` | **12 passed** in 115.76s |
| Backend lint | `cd backend && ..\.venv\Scripts\python.exe -m ruff check app tests ..\scripts` | **clean** |
| Python compile | `cd backend && ..\.venv\Scripts\python.exe -m compileall -q app tests ..\scripts` | **clean** |
| Frontend types | `cd frontend && npm run typecheck` | **clean** |
| Frontend lint | `cd frontend && npm run lint` | **clean** |
| Frontend build | `cd frontend && npm run build` | **success**, 8 app routes |
| Browser smoke | `cd frontend && npm run test:e2e` | **3 passed** in 2.2m |
| Acceptance eval | `.\.venv\Scripts\python.exe scripts\eval.py --platforms tiktok,linkedin,youtube --min-clip-s 12 --max-clip-s 35` | **81/81 passed**, 0 failed |

The acceptance run used project `683b1a3d8e574568bf14840da1544af7` (`The Creator Operating System`), a 100.374s demo recording, provider `mock`, brand `Systems Studio`, three rendered clips, and **$0.0000** metered spend. The JSON report was written to `data/evals/latest.json` (runtime data is gitignored).

## What the acceptance eval checks

A fresh run creates a demo project, attaches the eval brand, runs the pipeline, and then inspects the public API. The 81 checks break down as follows:

| Area | Checks | Examples |
| --- | --- | --- |
| Pipeline and project | 4 | job completed, source asset exists, at least one clip |
| Transcript | 4 | segments exist, word timings are present and ordered, provider recorded |
| Clips | 57 | bounds within source, target duration, no overlap, grounded quote, title/hook, all requested platforms, caption limits, hook variants, brand safety, rendered media, SRT content, 1080x1920 dimensions |
| Summary | 6 | TL;DR, at least three takeaways, ordered chapters, verified quotes |
| Insights | 4 | WPM metric, one scorecard per clip, methodology text, scores in 0-100 |
| Export | 3 | required files, clip media and SRT entries, manifest clip count |
| Usage | 3 | calls recorded, spend within budget, mock calls cost $0 |

The clip area is the largest because it runs the same platform checks for every clip. With three clips, TikTok, LinkedIn, and YouTube, each clip contributes 19 checks.

### Fresh run vs. stored project

A fresh eval includes `pipeline.completed` and reports **81** checks. When `--project-id` is supplied, the eval skips project creation and that check, so a stored project reports **80**. Both are expected; the README's "81-check" claim refers to a fresh run.

## How to run it

The API must be running. The eval talks to the public HTTP API rather than importing the FastAPI app, so it works against a local server, Docker Compose, or a deployed instance.

```bash
# from the repository root, with the venv Python
.\.venv\Scripts\python.exe scripts\eval.py

# evaluate an existing project without running the pipeline again
.\.venv\Scripts\python.exe scripts\eval.py --project-id <project-id>

# machine-readable output
.\.venv\Scripts\python.exe scripts\eval.py --json
```

Useful flags:

| Flag | Default | Purpose |
| --- | --- | --- |
| `--api-url` | `http://localhost:8000` | Target API |
| `--project-id` | none | Evaluate an existing project |
| `--brand` | `Systems Studio` | Brand profile to create/reuse |
| `--n-clips` | `3` | Clips requested from the pipeline |
| `--platforms` | all five | Comma-separated platform list |
| `--min-clip-s` / `--max-clip-s` | `12` / `35` | Duration window |
| `--expect-clips` | `1` | Minimum clip count |
| `--json-out` | `data/evals/latest.json` | Report path |

Exit code is `0` only when every check passes.

## What each test layer proves

### Backend tests (`backend/tests`)

- `test_api.py` exercises health, brand CRUD, project creation, upload, processing, SSE/job state, clip edits, banned-word rejection, regenerate, render, summary, insights, export, usage, demo creation, and system config.
- `test_samples.py` uploads the bundled demo video, checks the SHA256-keyed ground-truth transcript, completes the pipeline, and verifies a 1080x1920 render.
- `test_transcripts.py` covers timestamp formatting, SRT/ASS generation, quote normalization, and grounding.
- `test_mock_provider.py` covers deterministic provider output and schema-shaped responses.

### Playwright smoke test (`frontend/e2e/smoke.spec.ts`)

1. Dashboard entry points render.
2. A brand profile can be created through the dialog and appears on the brands page.
3. The demo pipeline runs, a clip caption is edited and saved, the page reloads with the edit intact, and the clip re-renders with a downloadable 9:16 video.

The test uses Chromium at a desktop viewport, one worker, and a 240s timeout per test.

### Acceptance eval (`scripts/eval.py`)

The eval is deliberately black-box. It checks what a reviewer can see through the API, including media dimensions via `ffprobe`, SRT text, ZIP contents, and the usage ledger. It does not read the database directly.

## Limitations and non-claims

These results are real for the environment above, but they are not a blanket production guarantee.

- **Mock provider only.** No live Meta key was available. The Meta provider is implemented from current docs but has not been smoke-tested against `api.meta.ai`. `TODO(verify)` items are listed in [DECISIONS.md](DECISIONS.md).
- **One source recording.** The acceptance path uses the bundled 100-second sample with a known transcript manifest. It does not prove ASR accuracy on arbitrary audio.
- **Deterministic mock semantics.** Mock copy is structurally realistic and brand-safe, but it is canned. The eval proves the contracts and rendering path, not creative quality.
- **Modeled engagement.** Insight scores are structural estimates from transcript features, not measured platform performance. The eval checks their presence and bounds, not their predictive accuracy.
- **Single-node operation.** The in-process queue, SQLite storage, and lack of authentication are demo constraints. No load, concurrency, or security testing was performed.
- **One browser.** Playwright runs Chromium only. Safari/Firefox behavior and mobile layouts are not covered.
- **Docker not exercised here.** The Dockerfiles and Compose file are included, but this environment did not run a container build. Treat Docker as unverified until `docker compose up --build` is run on the target machine.
- **No real uploads beyond the sample.** The eval does not fuzz corrupt media, very large files, or unusual codecs. Backend validation rejects unsupported inputs, but the rejection matrix is not exhaustive.
- **No publishing integration.** Export produces a review-ready pack; it does not post to social platforms.

## Interpreting a failure

| Symptom | Likely cause |
| --- | --- |
| `eval.connected` fails | API is not running at `--api-url`, or CORS/host is wrong |
| `pipeline.completed` fails | Check the job error, FFmpeg on `PATH`, and `DATA_DIR` write access |
| `transcript.provider` is `mock-fallback` | The upload bytes do not match a sample manifest; use the demo or install faster-whisper |
| `vertical_render` fails | FFmpeg/libass build issue; inspect the render command and generated ASS file |
| `caption_limit` fails | A platform limit or prompt changed; adjust the prompt/schema, not the check |
| `brand_safe` fails | Banned-word enforcement regressed; verify generation and PATCH both reject |
| `usage.mock_zero_cost` fails | Mock provider is recording nonzero cost, or a live provider is active |

When a check fails, the report includes the observed value. The JSON report is the source of truth for triage; do not edit `latest.json` by hand.
