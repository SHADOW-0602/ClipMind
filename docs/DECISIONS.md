# Decisions

This is a lightweight architecture decision record. Each entry states the decision, why it was made, and what it costs.

## 1. Live providers behind one adapter, selected by preset

**Decision:** ClipMind always runs against a live provider. `PROVIDER` selects a preset (`groq`, `gemini`, `openrouter`, `ollama`, `lmstudio`, `mistral`, `cerebras`, `deepseek`, `together`, `openai`, `openai_compatible`, `xai`, `fireworks`, `perplexity`, `custom`, or `meta`). Most presets use one OpenAI-compatible Chat Completions adapter; `meta` uses the native Responses API.

**Why:** the product must be reviewable end to end without a vendor lock-in or a separate demo path. A preset fills endpoint, model, ASR route, and prices, while explicit `LLM_*`/`ASR_*` variables still win. The default Groq preset is free. It uses `openai/gpt-oss-120b`, Groq's free-tier replacement for the retired Llama 3.3 70B, with `max_completion_tokens` and `reasoning_effort=low` so reasoning stays inside the pipeline's output budgets.

**Cost:** every run consumes a provider quota. A missing key fails startup rather than silently falling back to fake output. Tests inject a deterministic `StubProvider` through `set_provider_override()`; that hook is test-only and not selectable from the application environment.

## 2. Meta Model API remains an optional native provider

**Decision:** support the current Meta Model API docs (`https://dev.meta.ai/docs`) as `PROVIDER=meta`:

- base URL `https://api.meta.ai/v1`
- auth `Authorization: Bearer MODEL_API_KEY`
- reasoning/copy/summary model `muse-spark-1.3` (1.2 and 1.1 also documented)
- speech-to-text `muse-voice-transcribe-1.0`
- image model `muse-image-1.0` and segmentation `sam-3.1` are documented but not used by the current pipeline
- structured output on `POST /responses` via `text.format = {"type":"json_schema","name":...,"schema":...,"strict":false}`

**Why:** the original plan referenced older model generations and assumed no audio model. The current docs supersede that; using `muse-spark-1.3` and optional `muse-voice-transcribe-1.0` keeps the implementation aligned with the platform.

**Cost:** model IDs and prices are configuration, so a future rename is an `.env` change. The live Meta API was not exercised without a key; see the verification list at the end.

## 3. Structured JSON with validation and repair

**Decision:** every model task requests a JSON schema and validates the response. Invalid JSON triggers one repair pass; invalid semantics are corrected or dropped by pipeline code.

**Why:** clip quotes, timestamps, and captions are user-visible claims. Free-form text is not safe to persist without a contract.

**Cost:** schema descriptions add prompt tokens, and strict validation can reject a creative output that a human would accept. The repair pass and deterministic fallbacks keep the pipeline moving.

## 4. Deterministic candidates + model proposal + self-critique

**Decision:** generate candidate windows from transcript words and structural signals first. The model sees those candidates and proposes selections, then a critique pass reviews them. Pipeline code validates every proposal.

**Why:** letting the model choose arbitrary timestamps produces ungrounded or out-of-range clips. Candidate generation makes the search space inspectable and cheap; the model adds judgment about which moments matter.

**Cost:** the model cannot discover a moment outside the candidate windows. The candidate limit (`n_clips * 3`, at least 18) is a tuning knob.

## 5. Quote grounding is a hard gate

**Decision:** `quote_is_grounded()` normalizes punctuation/case and requires the quote to appear in the transcript. Ungrounded quotes are replaced with the best grounded sentence from the clip; a quote containing a banned word is omitted.

**Why:** a fabricated quote is worse than no quote. This is the core trust property of the product.

**Cost:** light cleanup is allowed, but paraphrase is not. Some model-proposed quotes are discarded.

## 6. ASS captions, not SRT force_style

**Decision:** generate an ASS file with explicit `PlayResX: 1080`, `PlayResY: 1920`, font size, outline, and bottom alignment. Burn it with FFmpeg's `ass` filter. Keep an SRT for download/export.

**Why:** SRT `force_style` produced inconsistent caption sizing and positioning across FFmpeg builds. ASS gives deterministic layout at the target resolution.

**Cost:** two subtitle artifacts per clip; ASS is an extra generated file (not exported, but retained for debugging).

## 7. Landscape sources get a blurred canvas

**Decision:** landscape video is scaled to fill a 1080×1920 blurred, darkened background, with the full frame scaled to width 1080 and centered. Portrait/square sources use a center crop.

**Why:** a hard center crop cuts titles, faces, and slides. The blurred canvas preserves the complete frame while satisfying the vertical format.

**Cost:** more FFmpeg work and a stylized look that may not suit every brand.

## 8. SQLite + SQLModel, in-process queue

**Decision:** one SQLite database in WAL mode, SQLModel tables, and an `asyncio.Queue` with `JOB_CONCURRENCY` workers inside the FastAPI process. Jobs persist stages/events/checkpoints as JSON.

**Why:** zero infrastructure, simple local setup, and enough durability for a demo. Checkpoints and auto-resume make restarts tolerable.

**Cost:** no horizontal scaling, no cross-process workers, and SQLite write contention under heavy load. A production version would use Postgres and a durable queue.

## 9. Pin SQLAlchemy below 2.1 on Windows

**Decision:** `sqlalchemy>=2.0.30,<2.1`.

**Why:** SQLAlchemy 2.1.6's C extension import was blocked by Windows Application Control in the build environment; 2.0.55 works through its pure-Python fallback.

**Cost:** misses 2.1 features. Revisit when the environment allows the extension.

## 10. Brand rules enforced twice

**Decision:** brand tone/audience/examples are injected into prompts; banned words are scrubbed after generation and rejected again on manual `PATCH /api/clips/{id}`.

**Why:** a model can ignore a prompt; a deterministic check cannot be talked out of a violation. Manual edits are the easiest place for a banned word to sneak in.

**Cost:** whole-word matching can miss morphological variants (e.g., plural forms) unless they are listed. The brand editor documents the matching behavior.

## 11. Hard budget guard

**Decision:** check cumulative spend before each model call and during ASR; abort with `BudgetExceeded` rather than overspend. Record every call with tokens, latency, cache hit, purpose, and cost.

**Why:** hackathon credits are finite and model calls are easy to loop. Cost visibility is also a product feature.

**Cost:** a call that would cross the limit is refused even if it is the last step needed for a complete run. The UI explains the failure.

## 12. Bundled sample ground truth

**Decision:** ship a 100-second demo video, a long demo, an audio file, and SHA256-keyed word-level transcript manifests. `transcribe_asset()` checks the manifest before calling remote or local ASR.

**Why:** a demo that shows captions must actually be grounded. Canned text with synthetic timings would undermine the core claim.

**Cost:** sample media adds repository size (~14 MB). The manifest is tied to exact file bytes; regenerating media invalidates it unless the manifest is regenerated too.

## 13. Next.js App Router + SSE with polling fallback

**Decision:** Next 16 App Router, React 19, Tailwind 4, shadcn-style primitives, and a custom `useJobStream` hook that prefers SSE and falls back to polling.

**Why:** SSE gives immediate stage updates without a WebSocket server; polling keeps the UI usable behind proxies that buffer streams.

**Cost:** two code paths for progress. The fallback is intentionally simple and polls the job endpoint.

## 14. No authentication in the demo

**Decision:** no login, accounts, or per-user isolation. The API binds to localhost in the documented setup.

**Why:** auth is not part of the product hypothesis being demonstrated, and adding it would distract from the pipeline. This is explicitly a demo constraint, not a production claim.

**Cost:** do not expose this deployment publicly. A real product needs auth, authorization, per-user storage quotas, and audit logs.

## 15. Engagement scores are estimates

**Decision:** call them modeled estimates in the UI, docs, export manifest, and insights methodology. Do not present them as predicted platform performance.

**Why:** there is no platform telemetry or causal validation. Overclaiming would be dishonest.

**Cost:** the insights feature is less flashy, but defensible.

## Verification list (`TODO(verify)`)

Groq and Gemini were exercised with real keys on 2026-10-29. The remaining gaps:

- OpenAI-compatible `POST /chat/completions` with structured JSON: verified live on Groq (`openai/gpt-oss-120b`) and Gemini (`gemini-2.5-flash`). Other presets remain unverified.
- End-to-end `POST /responses` call with `muse-spark-1.3` for `PROVIDER=meta`, including the exact `text.format` acceptance and response envelope.
- Whisper-compatible `/audio/transcriptions`: verified on Groq with `whisper-large-v3-turbo` (100s sample, 29 segments, 213 words, `segments: null` plus top-level `words`). Chunk boundary behavior near 10-minute cuts and other gateways remain unverified.
- Muse Voice Transcribe request/response shape, chunk boundary behavior, and word timestamp fidelity near 10-minute cuts.
- Whether large video inputs require the Files API instead of inline data URLs (the main path uses transcripts and still frames; a TODO is in `providers/meta.py`).
- Current pricing and model availability at run time. Groq's free tier reported `$0`; paid presets ship list prices and should be checked before a paid run.
- Rate-limit headers and retry-after behavior under sustained load. A single-request Groq header was observed; sustained throttling was not tested.

Search the repository for `TODO(verify)` before claiming live-provider coverage.
