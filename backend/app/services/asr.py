from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from ..config import Settings
from ..services.costs import ensure_budget, log_asr_call
from ..utils.media import extract_audio, run_ffmpeg

logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    pass


def _distribute_words(text: str, start: float, end: float) -> list[dict]:
    words = text.split()
    if not words:
        return []
    duration = max(0.15, end - start)
    weights = [max(1, len(word)) for word in words]
    total = sum(weights)
    cursor = start
    result = []
    for word, weight in zip(words, weights, strict=False):
        word_duration = duration * weight / total
        result.append(
            {
                "start": round(cursor, 3),
                "end": round(cursor + word_duration, 3),
                "word": word,
            }
        )
        cursor += word_duration
    return result


class MetaTranscriber:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.meta_base_url.rstrip("/"),
            timeout=httpx.Timeout(300.0, connect=30.0),
            headers={"Authorization": f"Bearer {settings.resolved_meta_api_key}"},
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def transcribe(self, audio_path: Path, duration_s: float, work_dir: Path) -> dict:
        # Meta requires mono 16-bit PCM WAV at 16 or 24 kHz, max 10 minutes, 32MB.
        if duration_s <= 600 and audio_path.stat().st_size <= 32 * 1024 * 1024:
            return await self._request(audio_path, duration_s)

        chunk_paths: list[Path] = []
        turns: list[dict] = []
        transcript_parts: list[str] = []
        offset = 0
        try:
            while offset < duration_s:
                target = work_dir / f"asr-chunk-{int(offset):05d}.wav"
                length = min(600.0, duration_s - offset)
                run_ffmpeg(
                    [
                        "-ss",
                        f"{offset:.3f}",
                        "-i",
                        str(audio_path),
                        "-t",
                        f"{length:.3f}",
                        "-ac",
                        "1",
                        "-ar",
                        "24000",
                        "-c:a",
                        "pcm_s16le",
                        str(target),
                    ],
                    timeout=600,
                )
                chunk_paths.append(target)
                chunk = await self._request(target, length)
                transcript_parts.append(chunk["text"])
                for turn in chunk["segments"]:
                    turns.append(
                        {
                            **turn,
                            "start": round(turn["start"] + offset, 3),
                            "end": round(turn["end"] + offset, 3),
                            "words": [
                                {
                                    **word,
                                    "start": round(word["start"] + offset, 3),
                                    "end": round(word["end"] + offset, 3),
                                }
                                for word in turn.get("words", [])
                            ],
                        }
                    )
                offset += length
        finally:
            for path in chunk_paths:
                path.unlink(missing_ok=True)
        return {
            "language": "en",
            "text": " ".join(transcript_parts).strip(),
            "segments": turns,
            "provider": "meta-voice-transcribe",
        }

    async def _request(self, audio_path: Path, duration_s: float) -> dict:
        # The API bills per audio-second. Check the budget before each call so a
        # long upload cannot slip past MAX_BUDGET_USD between token calls.
        ensure_budget(duration_s / 3600 * self.settings.meta_asr_usd_per_hour)
        request_payload = {
            "mode": "DIARIZATION",
            "model": self.settings.meta_asr_model,
            "audioEncoding": "WAV",
            "partialMode": "CUMULATIVE",
            "emitAudioProgress": False,
        }
        started = time.perf_counter()
        with audio_path.open("rb") as handle:
            response = await self.client.post(
                "/asr/transcribe",
                data={"request": json.dumps(request_payload)},
                files={"audio": (audio_path.name, handle, "audio/wav")},
            )
        if response.status_code >= 400:
            detail = response.text[:1000]
            raise TranscriptionError(f"Meta Voice Transcribe failed ({response.status_code}): {detail}")
        payload = response.json()
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_asr_call(
            model=self.settings.meta_asr_model,
            audio_seconds=duration_s,
            latency_ms=latency_ms,
            usd_per_hour=self.settings.meta_asr_usd_per_hour,
        )
        turns = payload.get("turns") or []
        segments = []
        for turn in turns:
            start = float(turn.get("startMs", 0)) / 1000
            end = float(turn.get("endMs", 0)) / 1000
            text = str(turn.get("transcript", "")).strip()
            if not text:
                continue
            segments.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": text,
                    "speaker": turn.get("speaker"),
                    "words": _distribute_words(text, start, end),
                }
            )
        if not segments and payload.get("transcript"):
            text = str(payload["transcript"]).strip()
            segments = [
                {
                    "start": 0.0,
                    "end": round(duration_s, 3),
                    "text": text,
                    "speaker": None,
                    "words": _distribute_words(text, 0, duration_s),
                }
            ]
        return {
            "language": "en",
            "text": str(payload.get("transcript") or " ".join(s["text"] for s in segments)),
            "segments": segments,
            "provider": "meta-voice-transcribe",
        }


_whisper_models: dict[tuple[str, str, str], object] = {}


class OpenAICompatibleTranscriber:
    """Transcribe through any OpenAI-compatible /audio/transcriptions endpoint."""

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.model = settings.llm_asr_model
        headers: dict[str, str] = {}
        if settings.resolved_llm_api_key:
            headers["Authorization"] = f"Bearer {settings.resolved_llm_api_key}"
        self.client = client or httpx.AsyncClient(
            base_url=settings.llm_base_url.rstrip("/"),
            timeout=httpx.Timeout(300.0, connect=30.0),
            headers=headers,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def transcribe(self, audio_path: Path, duration_s: float, work_dir: Path) -> dict:
        if not self.model:
            raise TranscriptionError(
                "ASR_PROVIDER=openai_compatible requires LLM_ASR_MODEL. Set it to the "
                "provider's transcription model, or use ASR_PROVIDER=whisper."
            )
        if duration_s <= 600 and audio_path.stat().st_size <= 24 * 1024 * 1024:
            return await self._request(audio_path, duration_s)

        chunk_paths: list[Path] = []
        segments: list[dict] = []
        text_parts: list[str] = []
        offset = 0.0
        try:
            while offset < duration_s:
                target = work_dir / f"asr-chunk-{int(offset):05d}.wav"
                length = min(600.0, duration_s - offset)
                run_ffmpeg(
                    [
                        "-ss",
                        f"{offset:.3f}",
                        "-i",
                        str(audio_path),
                        "-t",
                        f"{length:.3f}",
                        "-ac",
                        "1",
                        "-ar",
                        "16000",
                        "-c:a",
                        "pcm_s16le",
                        str(target),
                    ],
                    timeout=600,
                )
                chunk_paths.append(target)
                chunk = await self._request(target, length)
                text_parts.append(chunk["text"])
                for segment in chunk["segments"]:
                    segments.append(
                        {
                            **segment,
                            "start": round(segment["start"] + offset, 3),
                            "end": round(segment["end"] + offset, 3),
                            "words": [
                                {
                                    **word,
                                    "start": round(word["start"] + offset, 3),
                                    "end": round(word["end"] + offset, 3),
                                }
                                for word in segment.get("words", [])
                            ],
                        }
                    )
                offset += length
        finally:
            for path in chunk_paths:
                path.unlink(missing_ok=True)
        return {
            "language": "en",
            "text": " ".join(text_parts).strip(),
            "segments": segments,
            "provider": f"{self.settings.provider}-asr",
        }

    async def _request(self, audio_path: Path, duration_s: float) -> dict:
        ensure_budget(duration_s / 3600 * self.settings.llm_asr_usd_per_hour)
        started = time.perf_counter()
        payload: dict | None = None
        last_error = ""
        # verbose_json carries segments/words. Some gateways only implement
        # plain json, so retry once with the smaller response shape.
        for response_format in ("verbose_json", "json"):
            data: dict[str, str | list[str]] = {
                "model": self.model,
                "response_format": response_format,
            }
            if response_format == "verbose_json":
                # Whisper-compatible APIs need explicit granularities to return
                # word timings. Providers that reject the field fall back to
                # plain json below.
                data["timestamp_granularities[]"] = ["segment", "word"]
            with audio_path.open("rb") as handle:
                response = await self.client.post(
                    "/audio/transcriptions",
                    data=data,
                    files={"file": (audio_path.name, handle, "audio/wav")},
                )
            if response.status_code < 400:
                try:
                    payload = response.json()
                except ValueError:
                    last_error = response.text[:1000]
                    continue
                break
            last_error = response.text[:1000]
            if response.status_code not in {400, 415, 422}:
                break
        if payload is None:
            raise TranscriptionError(
                f"{self.settings.provider} transcription failed: {last_error}"
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_asr_call(
            model=self.model,
            audio_seconds=duration_s,
            latency_ms=latency_ms,
            usd_per_hour=self.settings.llm_asr_usd_per_hour,
        )
        raw_segments = payload.get("segments") or []
        raw_words = payload.get("words") or []
        segments: list[dict] = []
        for raw in raw_segments:
            text = str(raw.get("text") or "").strip()
            if not text:
                continue
            start = float(raw.get("start") or 0)
            end = float(raw.get("end") or 0)
            words = []
            for word in raw_words:
                word_start = float(word.get("start") or 0)
                word_end = float(word.get("end") or 0)
                if word_start >= start - 0.05 and word_end <= end + 0.05:
                    token = str(word.get("word") or "").strip()
                    if token:
                        words.append(
                            {
                                "start": round(word_start, 3),
                                "end": round(word_end, 3),
                                "word": token,
                            }
                        )
            if not words:
                words = _distribute_words(text, start, end)
            segments.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": text,
                    "speaker": raw.get("speaker"),
                    "words": words,
                }
            )
        if not segments:
            text = str(payload.get("text") or payload.get("transcript") or "").strip()
            if text:
                top_level_words = []
                for word in raw_words:
                    token = str(word.get("word") or "").strip()
                    if not token:
                        continue
                    top_level_words.append(
                        {
                            "start": round(float(word.get("start") or 0), 3),
                            "end": round(float(word.get("end") or 0), 3),
                            "word": token,
                        }
                    )
                segments = [
                    {
                        "start": 0.0,
                        "end": round(duration_s, 3),
                        "text": text,
                        "speaker": None,
                        "words": top_level_words or _distribute_words(text, 0, duration_s),
                    }
                ]
        return {
            "language": str(payload.get("language") or "en"),
            "text": str(payload.get("text") or " ".join(s["text"] for s in segments)).strip(),
            "segments": segments,
            "provider": f"{self.settings.provider}-asr",
        }


def transcribe_with_whisper(settings: Settings, audio_path: Path) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "faster-whisper is not installed. Run: pip install -e \".[whisper]\" "
            "or configure a provider with transcription support (groq, mistral, openai, meta)."
        ) from exc
    key = (settings.whisper_model, settings.whisper_device, settings.whisper_compute_type)
    model = _whisper_models.get(key)
    if model is None:
        logger.info("Loading faster-whisper model %s", settings.whisper_model)
        model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        _whisper_models[key] = model
    segments_iter, info = model.transcribe(  # type: ignore[attr-defined]
        str(audio_path),
        word_timestamps=True,
        vad_filter=True,
        beam_size=3,
    )
    segments = []
    text_parts = []
    for segment in segments_iter:
        words = [
            {"start": round(word.start, 3), "end": round(word.end, 3), "word": word.word.strip()}
            for word in (segment.words or [])
            if word.word.strip()
        ]
        text = (segment.text or "").strip()
        if not text:
            continue
        text_parts.append(text)
        segments.append(
            {
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "text": text,
                "speaker": None,
                "words": words,
            }
        )
    return {
        "language": getattr(info, "language", "en") or "en",
        "text": " ".join(text_parts),
        "segments": segments,
        "provider": "faster-whisper",
    }


def prepare_meta_wav(source: Path, destination: Path) -> None:
    extract_audio(source, destination, sample_rate=24000)


def prepare_openai_wav(source: Path, destination: Path) -> None:
    extract_audio(source, destination, sample_rate=16000)
