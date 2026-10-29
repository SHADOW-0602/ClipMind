from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlmodel import Session, select

from ..config import get_settings
from ..models import MediaAsset, Transcript
from ..services import cache
from ..services.asr import (
    MetaTranscriber,
    OpenAICompatibleTranscriber,
    TranscriptionError,
    prepare_meta_wav,
    prepare_openai_wav,
    transcribe_with_whisper,
)
from ..services.storage import resolve_path
from ..services.transcripts import build_segments_from_text, flatten_words
from ..utils.media import extract_audio

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
SAMPLE_TRANSCRIPTS = BACKEND_DIR / "samples" / "transcripts.json"


def _load_sample_manifest() -> dict:
    if not SAMPLE_TRANSCRIPTS.exists():
        return {}
    try:
        return json.loads(SAMPLE_TRANSCRIPTS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _build_text_result(text: str, duration: float, provider: str) -> dict:
    segments = build_segments_from_text(text, duration)
    return {
        "language": "en",
        "text": text.strip(),
        "segments": segments,
        "provider": provider,
    }


async def transcribe_asset(session: Session, asset_id: str, *, force: bool = False) -> Transcript:
    settings = get_settings()
    asset = session.get(MediaAsset, asset_id)
    if not asset:
        raise TranscriptionError("Media asset not found")
    existing = session.exec(select(Transcript).where(Transcript.asset_id == asset_id)).first()
    if existing and not force:
        return existing
    if force and existing:
        session.delete(existing)
        session.commit()

    if asset.kind == "text":
        path = resolve_path(asset.path)
        if not path or not path.exists():
            raise TranscriptionError("Text source is missing")
        text = path.read_text(encoding="utf-8", errors="replace")
        result = _build_text_result(text, max(5.0, asset.duration_s), "text")
    else:
        cache_key = f"transcript:{asset.checksum}"
        cached = cache.get_json(cache_key)
        if cached and not force:
            result = cached
        else:
            result = None
            manifest = _load_sample_manifest()
            if asset.checksum in manifest:
                result = manifest[asset.checksum]
                result["provider"] = "sample-ground-truth"
            if result is None:
                audio = resolve_path(asset.audio_path)
                if not audio or not audio.exists():
                    raise TranscriptionError("Audio track is missing; ingestion may have failed")
                remote_error: Exception | None = None
                asr_choice = settings.effective_asr_provider
                if asr_choice == "meta" and settings.resolved_meta_api_key:
                    try:
                        work_dir = audio.parent
                        meta_wav = work_dir / "audio-meta-24k.wav"
                        prepare_meta_wav(audio, meta_wav)
                        transcriber = MetaTranscriber(settings)
                        try:
                            result = await transcriber.transcribe(
                                meta_wav, asset.duration_s, work_dir
                            )
                        finally:
                            await transcriber.aclose()
                    except Exception as exc:  # noqa: BLE001 - fall back to local ASR
                        remote_error = exc
                        logger.warning("Meta Voice Transcribe failed: %s", exc)
                elif asr_choice == "meta":
                    remote_error = TranscriptionError("META_API_KEY is not configured")
                elif asr_choice == "openai_compatible":
                    try:
                        work_dir = audio.parent
                        asr_wav = work_dir / "audio-asr-16k.wav"
                        prepare_openai_wav(audio, asr_wav)
                        transcriber = OpenAICompatibleTranscriber(settings)
                        try:
                            result = await transcriber.transcribe(
                                asr_wav, asset.duration_s, work_dir
                            )
                        finally:
                            await transcriber.aclose()
                    except Exception as exc:  # noqa: BLE001 - fall back to local ASR
                        remote_error = exc
                        logger.warning("%s transcription failed: %s", settings.provider, exc)
                if result is None:
                    try:
                        local_wav = audio
                        if local_wav.suffix.lower() != ".wav":
                            local_wav = audio.parent / "audio-16k.wav"
                            extract_audio(audio, local_wav)
                        result = transcribe_with_whisper(settings, local_wav)
                    except Exception as local_exc:  # noqa: BLE001
                        detail = f"Remote ASR error: {remote_error}; " if remote_error else ""
                        raise TranscriptionError(
                            f"{detail}Local transcription failed: {local_exc}. Install "
                            'faster-whisper with pip install -e ".[whisper]" or set '
                            "ASR_PROVIDER to a provider with transcription support."
                        ) from local_exc
            cache.put_json(cache_key, result)

    segments = result.get("segments") or []
    segments = [segment for segment in segments if float(segment.get("end", 0)) > float(segment.get("start", 0))]
    words = flatten_words(segments)
    transcript = Transcript(
        asset_id=asset_id,
        language=str(result.get("language") or "en"),
        text=str(result.get("text") or " ".join(s.get("text", "") for s in segments)).strip(),
        segments_json=segments,
        provider=str(result.get("provider") or "unknown"),
    )
    session.add(transcript)
    asset.status = "ready"
    session.add(asset)
    session.commit()
    session.refresh(transcript)
    logger.info(
        "Transcribed asset %s: %d segments, %d words, provider=%s",
        asset_id,
        len(segments),
        len(words),
        transcript.provider,
    )
    return transcript


def transcript_segments(transcript: Transcript) -> list[dict]:
    return transcript.segments_json or []


def transcript_duration(transcript: Transcript) -> float:
    segments = transcript.segments_json or []
    return max((float(segment.get("end", 0)) for segment in segments), default=0.0)
