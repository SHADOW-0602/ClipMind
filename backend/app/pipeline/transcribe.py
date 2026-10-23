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
    TranscriptionError,
    prepare_meta_wav,
    transcribe_with_whisper,
)
from ..services.storage import resolve_path
from ..services.transcripts import build_segments_from_text, flatten_words
from ..utils.media import extract_audio

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
SAMPLE_TRANSCRIPTS = BACKEND_DIR / "samples" / "transcripts.json"
FALLBACK_SCRIPT = BACKEND_DIR / "samples" / "fallback_script.txt"


def _load_sample_manifest() -> dict:
    if not SAMPLE_TRANSCRIPTS.exists():
        return {}
    try:
        return json.loads(SAMPLE_TRANSCRIPTS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _fallback_text(duration: float) -> str:
    if not FALLBACK_SCRIPT.exists():
        return (
            "This is a mock transcript because no speech-to-text provider is configured. "
            "Switch off MOCK_MODE and add a Meta Model API key to transcribe the real audio. "
            "The rest of the pipeline is fully functional and the demo sample is grounded."
        )
    base = FALLBACK_SCRIPT.read_text(encoding="utf-8").strip()
    target_words = max(6, int(duration * 2.3))
    source_sentences = [part.strip() for part in base.replace("\n", " ").split(".") if part.strip()]
    if not source_sentences:
        return base
    chosen: list[str] = []
    count = 0
    index = 0
    while count < target_words and source_sentences:
        sentence = source_sentences[index % len(source_sentences)]
        chosen.append(sentence.strip() + ".")
        count += len(sentence.split())
        index += 1
        if index > 2000:
            break
    return " ".join(chosen)


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
            if result is None and settings.mock_mode:
                if settings.force_whisper:
                    audio = resolve_path(asset.audio_path or asset.path)
                    if not audio:
                        raise TranscriptionError("Audio track is missing")
                    result = transcribe_with_whisper(settings, audio)
                else:
                    result = _build_text_result(
                        _fallback_text(asset.duration_s), asset.duration_s, "mock-canned"
                    )
                    logger.warning(
                        "Mock mode used a canned transcript for %s. Add the file to "
                        "backend/samples/transcripts.json or enable FORCE_WHISPER for real speech.",
                        asset.original_filename,
                    )
            if result is None:
                audio = resolve_path(asset.audio_path)
                if not audio or not audio.exists():
                    raise TranscriptionError("Audio track is missing; ingestion may have failed")
                meta_error: Exception | None = None
                if settings.use_meta_asr and settings.model_api_key and not settings.force_whisper:
                    try:
                        work_dir = audio.parent
                        meta_wav = work_dir / "audio-meta-24k.wav"
                        prepare_meta_wav(audio, meta_wav)
                        transcriber = MetaTranscriber(settings)
                        try:
                            result = await transcriber.transcribe(meta_wav, asset.duration_s, work_dir)
                        finally:
                            await transcriber.aclose()
                    except Exception as exc:  # noqa: BLE001 - fall back to local provider
                        meta_error = exc
                        logger.warning("Meta Voice Transcribe failed: %s", exc)
                if result is None:
                    try:
                        local_wav = audio
                        if local_wav.suffix.lower() != ".wav":
                            local_wav = audio.parent / "audio-16k.wav"
                            extract_audio(audio, local_wav)
                        result = transcribe_with_whisper(settings, local_wav)
                    except Exception as local_exc:  # noqa: BLE001
                        detail = f"Meta ASR error: {meta_error}; " if meta_error else ""
                        raise TranscriptionError(
                            f"{detail}Local transcription failed: {local_exc}. Install faster-whisper "
                            'with pip install -e ".[whisper]" or configure MODEL_API_KEY.'
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
