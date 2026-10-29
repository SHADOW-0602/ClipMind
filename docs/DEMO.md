# Demo

A three-minute walkthrough of the complete ClipMind loop: one long recording in, a reviewed clip pack out. The demo uses the bundled 100-second recording with a word-level ground-truth transcript and runs on the configured live provider. The default Groq preset is free.

## Preflight (2 minutes before presenting)

- [ ] `.env` exists and contains `PROVIDER=groq` and a real `MODEL_API_KEY`.
- [ ] `ffmpeg` and `ffprobe` are on `PATH` (`ffmpeg -version` works).
- [ ] Backend is running at `http://localhost:8000` (`/api/health` returns `ok`).
- [ ] Frontend is running at `http://localhost:3000`.
- [ ] The browser is at the dashboard and the sidebar shows the **groq live** badge.
- [ ] Optional: brand profiles are seeded (`python scripts/seed_demo.py`).
- [ ] Optional: clear old demo projects if the dashboard is cluttered.

Start both services from the repository root:

```bash
python scripts/dev.py
```

Or use the Docker stack:

```bash
docker compose up --build
```

If the dashboard is empty, that is fine; the demo creates its own project.

## Three-minute script

### 0:00 - 0:20 | Frame the problem

Open the dashboard at **http://localhost:3000**.

Point out:

- The four totals: projects, clips generated, source analyzed, model spend.
- **Model spend** shows the metered cost of the configured provider. Free-tier presets report `$0.0000`; paid presets show their list prices.
- The product claim: one recording becomes transcript-grounded clips, platform copy, captioned vertical renders, and an honest read on what to improve.

Say: *"The hard part is not clipping. It is trusting the clip. Every quote and timestamp here is checked against the transcript."*

### 0:20 - 0:35 | Start the demo

Click **Run the demo**.

ClipMind creates a project from `backend/samples/demo-short.mp4` and starts the pipeline. The project workspace opens immediately.

Point out the live stage rail and the progress bar. The stages are ingest, transcribe, understand, select, copy/summary, render, and insights. The source player and stage list update over SSE; if the stream drops, the UI falls back to polling.

Expected: the sample skips ASR because its SHA256 matches the bundled transcript manifest. The model stages still call the configured provider and consume quota, so the run takes as long as those calls take.

### 0:35 - 1:15 | Inspect the clip pack

On the **Clips** tab, point out:

- Three vertical clip cards with thumbnails, scores, durations, and platform counts.
- Each card links to the clip studio.
- The sidebar **Project notes** shows the source, duration, clip count, rendered count, and attached brand.

Click the first clip.

### 1:15 - 1:50 | Edit and re-render

In the **Clip studio**:

- The left preview is the rendered 9:16 video with burned-in captions. The **9:16** badge confirms the vertical render.
- The **Moment** card shows the score, duration, rationale, and any review flags.
- The right side opens on **Platform copy**. Switch between Instagram, YouTube Shorts, TikTok, LinkedIn, and X. Point out the caption, hook variants, hashtags, CTA, and character counter.
- Edit a caption. Click **Save changes**. The toast confirms the edit is live.
- Click **Re-render**. The preview overlay shows FFmpeg cutting and burning captions. When it finishes, the **9:16** preview refreshes and **Download rendered clip** is enabled.

Say: *"Brand rules are enforced here too. A banned word is rejected with a 422, not silently saved."*

### 1:50 - 2:20 | Summary, insights, transcript

Go back to the project and open the other tabs.

- **Summary**: TL;DR, takeaways, timestamped chapters, and verified quotes. Clicking a chapter or quote seeks the source player.
- **Insights**: WPM, pause ratio, filler rate, hook delay, and per-clip scorecards. The methodology line makes clear these are modeled estimates, not platform predictions.
- **Transcript**: word-level segments with timings, marked **ground truth** for the bundled sample. Clicking a segment seeks the source.

### 2:20 - 2:40 | Export and cost

Click **Export pack**. The ZIP contains:

```text
manifest.json
summary.md
copy.csv
insights.json
clips/*.mp4
captions/*.srt
thumbnails/*.jpg
```

Open **Usage & spend** in the sidebar. Point out the call ledger, token counts, cache hits, ASR seconds, total spend, remaining budget, and hackathon credits. The ledger records the configured provider and model for every call; free-tier presets report `$0.0000` until you set list prices.

### 2:40 - 3:00 | Brand and close

Open **Brand profiles**. Show the tone, audience, do/don't rules, banned words, and example posts. Explain that these fields flow into every prompt and that banned words are checked again on manual saves.

Close on the dashboard or the exported pack:

> *"ClipMind is not a clipping toy. It is a reviewable pipeline: grounded transcript, validated moments, platform-native copy, deterministic vertical renders, and a cost ledger you can defend."*

## CLI version

If the UI is not available, run the same flow from the terminal. The API must be running.

```bash
# create and process the bundled demo
python scripts/demo.py

# attach an existing brand by name
python scripts/demo.py --brand "Systems Studio"

# create a project and job, then exit without waiting
python scripts/demo.py --no-wait --json
```

Expected output includes the project URL, job status, clip count, rendered count, and model spend:

```text
Status: completed | clips: 3 | rendered: 3
Model spend: $0.0000 | calls: 14
  1. Here is the fix (32.6s, rendered)
  2. That is a much better question (30.7s, rendered)
  3. The goal is a loop (20.1s, rendered)

Open the studio: http://localhost:3000/projects/<id>
```

To seed brand profiles and a completed demo project for screenshots:

```bash
python scripts/seed_demo.py --with-project --wait
```

## What to emphasize

1. **Grounding over generation.** Quotes are checked against the transcript; invented quotes are replaced or dropped.
2. **Deterministic gates around model judgment.** Candidates are generated in code, the model proposes and critiques, and validation decides what survives.
3. **One pipeline, many providers.** Every preset exercises the same orchestration, validation, cost, and render code. Switching providers is an `.env` change.
4. **Vertical output is real.** 1080x1920 MP4 with ASS captions, not a CSS preview.
5. **Cost is a product surface.** Every call is metered, cached calls are tracked, and the budget guard blocks overspend.

## Fallbacks

| Problem | Fix |
| --- | --- |
| Dashboard says the API is not responding | Start the backend on port 8000; check `CORS_ORIGINS` includes `http://localhost:3000` |
| `Run the demo` fails with "Demo media is not generated" | Run `python scripts/generate_samples.py` |
| Pipeline fails at render | Check `ffmpeg -version` and `ffprobe -version`; install FFmpeg 6+ |
| Pipeline fails at transcribe | The sample should use the manifest; check `backend/samples/transcripts.json` and the file SHA256. For arbitrary media, check the provider key and `ASR_PROVIDER`, or install faster-whisper |
| Provider fails at startup | Set `MODEL_API_KEY` for the selected preset, or switch to `PROVIDER=ollama`/`lmstudio` for a local endpoint |
| Port 3000 or 8000 is busy | `python scripts/dev.py` finds free ports; or pass explicit ports to uvicorn/Next |
| Old projects clutter the dashboard | Delete them in the UI, or stop the backend and remove `data/clipmind.db` (this deletes all runtime data) |
| The clip preview is black | Wait for the render to finish; check the backend log for the FFmpeg command and error |
| SSE shows **polling** instead of **live** | A proxy is buffering the stream; polling is the intended fallback and the run still completes |

## Reset between rehearsals

Runtime data lives in `data/` and is gitignored.

```bash
# stop the backend first, then remove the local database and media
rm -rf data
mkdir -p data
```

On Windows PowerShell:

```powershell
Remove-Item -Recurse -Force data
New-Item -ItemType Directory data | Out-Null
```

The next run recreates the database and directories. The bundled samples in `backend/samples/` are not affected.

## Switching providers for the demo

Change `PROVIDER` and the key in `.env`, then restart the backend:

```dotenv
# Free default
PROVIDER=groq
MODEL_API_KEY=gsk_...

# Fully local, no key
# PROVIDER=ollama
# LLM_BASE_URL=http://localhost:11434/v1
# LLM_MODEL=llama3.2

# Native Meta Responses API
# PROVIDER=meta
# META_API_KEY=...
```

The sidebar badge reflects the active preset. Live-provider behavior is implemented from current provider docs but has not been smoke-tested with a real key in this repository; the verification note in [DECISIONS.md](DECISIONS.md) lists the unverified API details.
