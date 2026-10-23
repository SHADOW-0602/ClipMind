from __future__ import annotations

import json
import logging
import re
from collections import Counter

from sqlmodel import Session, delete

from ..models import MediaAsset, Project, TopicSegment, Transcript
from ..providers import get_provider
from ..providers.base import ImageInput, Message
from ..schemas import UnderstandOutput
from ..services.prompts import load_prompt
from ..services.storage import resolve_path

logger = logging.getLogger(__name__)

STOP = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with", "is", "are",
    "was", "were", "it", "this", "that", "you", "your", "we", "our", "i", "me", "my", "as",
    "at", "be", "have", "has", "had", "do", "does", "did", "from", "by", "not", "so", "if",
    "then", "than", "can", "will", "just", "about", "what", "when", "how", "why", "who",
}


def _topic_from(text: str, index: int) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text.lower())
    counts = Counter(word for word in words if word not in STOP)
    keywords = [word for word, _ in counts.most_common(3)]
    return " ".join(word.title() for word in keywords) if keywords else f"Part {index + 1}"


def _fallback_segments(transcript: Transcript, duration: float) -> list[dict]:
    segments = transcript.segments_json or []
    if not segments:
        return []
    target = 90.0
    groups: list[list[dict]] = []
    current: list[dict] = []
    group_start = float(segments[0].get("start", 0))
    for segment in segments:
        if current and float(segment.get("end", 0)) - group_start > target:
            groups.append(current)
            current = []
            group_start = float(segment.get("start", 0))
        current.append(segment)
    if current:
        groups.append(current)
    result = []
    for index, group in enumerate(groups):
        text = " ".join(str(item.get("text", "")) for item in group).strip()
        if not text:
            continue
        result.append(
            {
                "start": float(group[0].get("start", 0)),
                "end": min(duration, float(group[-1].get("end", duration))),
                "topic": _topic_from(text, index),
                "summary": text[:280],
                "sentiment": "neutral",
                "energy_score": 0.6,
                "speaker_intent": "Share a useful perspective",
                "quotable": "?" in text or "!" in text,
            }
        )
    return result


def _cues(transcript: Transcript) -> list[dict]:
    return [
        {
            "start": round(float(segment.get("start", 0)), 2),
            "end": round(float(segment.get("end", 0)), 2),
            "text": str(segment.get("text", "")).strip(),
            "speaker": segment.get("speaker"),
        }
        for segment in transcript.segments_json or []
        if str(segment.get("text", "")).strip()
    ]


def _validate_segments(raw: list, duration: float) -> list[dict]:
    valid: list[dict] = []
    last_end = 0.0
    for segment in sorted(raw, key=lambda item: item.start):
        start = max(0.0, min(float(segment.start), duration))
        end = max(start, min(float(segment.end), duration))
        if end - start < 3:
            continue
        if start < last_end - 0.25:
            start = last_end
        if end - start < 2:
            continue
        if end <= last_end:
            continue
        valid.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "topic": segment.topic.strip()[:160] or "Untitled segment",
                "summary": segment.summary.strip()[:600],
                "sentiment": segment.sentiment,
                "energy_score": round(float(segment.energy_score), 2),
                "speaker_intent": segment.speaker_intent.strip()[:300],
                "quotable": bool(segment.quotable),
            }
        )
        last_end = end
    return valid


async def understand_asset(
    session: Session,
    project_id: str,
    asset_id: str,
    transcript: Transcript,
    progress=None,
) -> list[TopicSegment]:
    asset = session.get(MediaAsset, asset_id)
    project = session.get(Project, project_id)
    if not asset or not project:
        raise ValueError("Project or asset not found for understanding stage")
    duration = asset.duration_s or max(
        (float(segment.get("end", 0)) for segment in transcript.segments_json or []), default=0.0
    )

    session.exec(delete(TopicSegment).where(TopicSegment.asset_id == asset_id))
    session.commit()

    keyframes = asset.frames_json or []
    context = {
        "duration_s": round(duration, 2),
        "segments": _cues(transcript),
        "keyframes": [{"timestamp": frame.get("timestamp")} for frame in keyframes],
    }
    system = load_prompt("understand_segments").replace(
        "{{CONTEXT_JSON}}", json.dumps(context, ensure_ascii=False)
    )
    images: list[ImageInput] = []
    for frame in keyframes[:4]:
        path = resolve_path(frame.get("path"))
        if path and path.exists():
            images.append(ImageInput(path=path, mime_type="image/jpeg"))
    provider = get_provider()
    output = _fallback_segments(transcript, duration)
    try:
        if progress:
            await progress(0.2, "Reading topics, speakers, and energy")
        result = await provider.generate(
            system=system,
            messages=[
                Message(
                    role="user",
                    content=(
                        "Analyze the supplied transcript cues and return the structured topic map. "
                        f"This asset is {duration:.1f} seconds long."
                    ),
                )
            ],
            images=images or None,
            response_schema=UnderstandOutput.model_json_schema(),
            max_output_tokens=5000,
            cache_key=f"understand:{asset.checksum or asset.id}",
        )
        if result.parsed:
            parsed = UnderstandOutput.model_validate(result.parsed)
            output = _validate_segments(parsed.segments, duration) or output
        if progress:
            await progress(0.9, f"Identified {len(output)} topic segments")
    except Exception as exc:  # noqa: BLE001 - deterministic fallback keeps pipeline alive
        logger.warning("Understand stage fell back to heuristic segments: %s", exc)
        project.error = f"Understanding used a heuristic fallback: {exc}"

    rows: list[TopicSegment] = []
    for segment in output:
        row = TopicSegment(
            asset_id=asset_id,
            start=float(segment["start"]),
            end=float(segment["end"]),
            topic=str(segment["topic"]),
            summary=str(segment.get("summary", "")),
            sentiment=str(segment.get("sentiment", "neutral")),
            energy_score=float(segment.get("energy_score", 0.5)),
            speaker_intent=str(segment.get("speaker_intent", "")),
            quotable=bool(segment.get("quotable", False)),
        )
        session.add(row)
        rows.append(row)
    session.add(project)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows
