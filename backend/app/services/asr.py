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
            headers={"Authorization": f"Bearer {settings.model_api_key}"},
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
        ensure_budget(duration_s / 3600 * 0.18)
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


def transcribe_with_whisper(settings: Settings, audio_path: Path) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "faster-whisper is not installed. Run: pip install -e \".[whisper]\" "
            "or configure Meta Voice Transcribe."
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
