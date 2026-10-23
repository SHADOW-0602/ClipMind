from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from sqlmodel import Session, select

from ..models import Clip, InsightReport, MediaAsset, Project, Transcript
from ..providers import get_provider
from ..providers.base import Message
from ..schemas import InsightOutput
from ..services.prompts import load_prompt
from ..services.transcripts import flatten_words

logger = logging.getLogger(__name__)

FILLERS = {"um", "uh", "like", "you know", "sort of", "kind of", "basically", "actually"}
RISK_FLAG_MESSAGES = {
    "self_harm_topic": "contains a sensitive mental-health reference; human review required",
    "medical_claim": "may contain a medical claim; do not auto-publish without review",
    "guaranteed_results": "contains a guaranteed-results claim; edit before publishing",
    "financial_topic": "contains financial subject matter; add a careful review",
    "hate_speech_review": "flagged for a hate-speech review",
}


def _clip_text(transcript: Transcript, start: float, end: float) -> str:
    words = flatten_words(transcript.segments_json or [])
    return " ".join(
        str(word.get("word", "")).strip()
        for word in words
        if float(word.get("end", 0)) > start and float(word.get("start", 0)) < end
    )


def deterministic_metrics(transcript: Transcript, clips: list[Clip]) -> dict:
    words = flatten_words(transcript.segments_json or [])
    if not words:
        return {"wpm": 0, "pause_ratio": 0, "filler_rate": 0, "word_count": 0, "clip_metrics": []}
    duration = max(0.1, float(words[-1].get("end", 0)) - float(words[0].get("start", 0)))
    gaps = []
    for previous, current in zip(words, words[1:], strict=False):
        gaps.append(max(0.0, float(current.get("start", 0)) - float(previous.get("end", 0))))
    speaking_time = max(0.1, duration - sum(gap for gap in gaps if gap >= 0.5))
    wpm = len(words) / speaking_time * 60
    pause_ratio = sum(gap for gap in gaps if gap >= 0.6) / duration
    text = " ".join(str(word.get("word", "")) for word in words).lower()
    filler_count = sum(
        len(re.findall(rf"(?<!\w){re.escape(filler)}(?!\w)", text)) for filler in FILLERS
    )
    filler_rate = filler_count / max(1, len(words))
    clip_metrics = []
    for clip in clips:
        clip_words = [
            word
            for word in words
            if float(word.get("end", 0)) > clip.start and float(word.get("start", 0)) < clip.end
        ]
        clip_duration = max(0.1, clip.end - clip.start)
        clip_wpm = len(clip_words) / clip_duration * 60
        first_words = " ".join(str(word.get("word", "")) for word in clip_words[:14])
        clip_gaps = [
            max(0.0, float(current.get("start", 0)) - float(previous.get("end", 0)))
            for previous, current in zip(clip_words, clip_words[1:], strict=False)
        ]
        clip_pause_ratio = sum(gap for gap in clip_gaps if gap >= 0.6) / clip_duration
        clip_filler = sum(
            1
            for word in clip_words
            if str(word.get("word", "")).lower().strip(".,!?") in FILLERS
        ) / max(1, len(clip_words))
        hook_delay = 0.0
        for word in clip_words:
            if re.search(r"[.!?]$", str(word.get("word", ""))):
                hook_delay = float(word.get("end", clip.start)) - clip.start
                break
        clip_metrics.append(
            {
                "clip_id": clip.id,
                "duration_s": round(clip_duration, 2),
                "wpm": round(clip_wpm, 1),
                "pause_ratio": round(clip_pause_ratio, 3),
                "filler_rate": round(clip_filler, 4),
                "hook_delay_s": round(hook_delay, 2),
                "opening": first_words,
                "length_fit": "good" if 15 <= clip_duration <= 60 else "adjust",
            }
        )
    return {
        "duration_s": round(duration, 1),
        "word_count": len(words),
        "wpm": round(wpm, 1),
        "pause_ratio": round(pause_ratio, 3),
        "filler_rate": round(filler_rate, 4),
        "clip_metrics": clip_metrics,
    }


def _fallback_scores(metrics: dict, clips: list[Clip]) -> dict:
    wpm = float(metrics.get("wpm") or 145)
    pause = float(metrics.get("pause_ratio") or 0.2)
    filler = float(metrics.get("filler_rate") or 0.02)
    pacing = int(max(45, min(95, 100 - abs(wpm - 155) * 0.55 - pause * 25)))
    clarity = int(max(45, min(96, 96 - filler * 900 - pause * 30)))
    clip_rows = []
    for index, clip in enumerate(clips):
        hook = int(max(50, min(96, clip.score + (4 if "?" in clip.hook else 0))))
        clip_rows.append(
            {
                "clip_id": clip.id,
                "clip_index": index,
                "title": clip.title,
                "scores": {
                    "hook_strength": hook,
                    "pacing": pacing,
                    "clarity": clarity,
                    "emotional_peaks": int(max(42, min(94, clip.score - 4))),
                },
                "predicted_performance": "high" if hook >= 82 else "medium" if hook >= 65 else "low",
                "reasoning": "Heuristic estimate from transcript rhythm, opening strength, and clip structure.",
                "improvements": [
                    "Trim the first 0.5s so the hook lands on the first frame.",
                    "Add a mid-clip pattern break to reset attention.",
                    "Test a second hook variant that names the concrete payoff.",
                ],
                "risk_flags": clip.risk_flags_json,
            }
        )
    overall = {
        "hook_strength": int(sum(row["scores"]["hook_strength"] for row in clip_rows) / max(1, len(clip_rows))),
        "pacing": pacing,
        "clarity": clarity,
        "emotional_peaks": int(sum(row["scores"]["emotional_peaks"] for row in clip_rows) / max(1, len(clip_rows))),
    }
    return {
        "headline": "A grounded short-form opportunity",
        "summary": "Scores are estimated from transcript structure and delivery. Treat them as editorial guidance, not platform guarantees.",
        "overall": overall,
        "predicted_performance": "high" if overall["hook_strength"] >= 80 else "medium",
        "confidence": "medium",
        "improvements": [
            "Open each clip on the strongest phrase instead of the start of a breath.",
            "Add on-screen context for any pronoun or reference that depends on earlier conversation.",
            "Test two hooks per clip and keep the one with the clearer concrete payoff.",
        ],
        "clips": clip_rows,
    }


def _clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))


async def generate_insights(
    session: Session,
    project_id: str,
    asset: MediaAsset,
    transcript: Transcript,
    clips: list[Clip],
    *,
    progress=None,
) -> InsightReport:
    project = session.get(Project, project_id)
    if not project:
        raise ValueError("Project not found for insights")
    metrics = deterministic_metrics(transcript, clips)
    context = {
        "source": {
            "filename": asset.original_filename,
            "duration_s": asset.duration_s,
            "kind": asset.kind,
        },
        "metrics": metrics,
        "clips": [
            {
                "index": index,
                "title": clip.title,
                "start": clip.start,
                "end": clip.end,
                "score": clip.score,
                "hook": clip.hook,
                "transcript": _clip_text(transcript, clip.start, clip.end)[:1800],
                "risk_flags": clip.risk_flags_json,
            }
            for index, clip in enumerate(clips)
        ],
    }
    system = load_prompt("insights").replace("{{CONTEXT_JSON}}", json.dumps(context, ensure_ascii=False))
    fallback = _fallback_scores(metrics, clips)
    output = fallback
    try:
        result = await get_provider().generate(
            system=system,
            messages=[
                Message(
                    role="user",
                    content=(
                        "Interpret these clip and transcript metrics. Label predictions as estimates. "
                        "Return one scorecard for every clip index."
                    ),
                )
            ],
            response_schema=InsightOutput.model_json_schema(),
            max_output_tokens=5000,
            cache_key=f"insights:{asset.checksum or asset.id}:{len(clips)}",
        )
        if result.parsed:
            model = InsightOutput.model_validate(result.parsed)
            by_index = {item.clip_index: item for item in model.clips}
            clip_rows = []
            for index, clip in enumerate(clips):
                item = by_index.get(index)
                if item is None:
                    base = next(row for row in fallback["clips"] if row["clip_index"] == index)
                    clip_rows.append(base)
                    continue
                clip_rows.append(
                    {
                        "clip_id": clip.id,
                        "clip_index": index,
                        "title": clip.title,
                        "scores": {
                            "hook_strength": _clamp_score(item.scores.hook_strength),
                            "pacing": _clamp_score(item.scores.pacing),
                            "clarity": _clamp_score(item.scores.clarity),
                            "emotional_peaks": _clamp_score(item.scores.emotional_peaks),
                        },
                        "predicted_performance": item.predicted_performance,
                        "reasoning": item.reasoning,
                        "improvements": item.improvements[:3],
                        "risk_flags": clip.risk_flags_json,
                    }
                )
            output = {
                "headline": model.headline,
                "summary": model.summary,
                "overall": {
                    "hook_strength": _clamp_score(model.overall.hook_strength),
                    "pacing": _clamp_score(model.overall.pacing),
                    "clarity": _clamp_score(model.overall.clarity),
                    "emotional_peaks": _clamp_score(model.overall.emotional_peaks),
                },
                "predicted_performance": model.predicted_performance,
                "confidence": model.confidence,
                "improvements": model.improvements[:3],
                "clips": clip_rows,
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Insights model call failed, using deterministic scorecard: %s", exc)

    for row in output.get("clips", []):
        messages = [RISK_FLAG_MESSAGES[flag] for flag in row.get("risk_flags", []) if flag in RISK_FLAG_MESSAGES]
        row["safety_notes"] = messages
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "headline": output["headline"],
        "summary": output["summary"],
        "overall": output["overall"],
        "predicted_performance": output["predicted_performance"],
        "confidence": output["confidence"],
        "improvements": output["improvements"],
        "clips": output["clips"],
        "metrics": metrics,
        "methodology": (
            "Transcript-first structural analysis: WPM, pause ratio, filler rate, hook delay, "
            "clip length fit, opening language, and the editorial scores. Performance bands are "
            "modeled estimates, not guarantees. No visual or platform-analytics data is implied."
        ),
        "source": {
            "kind": asset.kind,
            "duration_s": asset.duration_s,
            "filename": asset.original_filename,
        },
    }
    existing = session.exec(select(InsightReport).where(InsightReport.project_id == project_id)).first()
    if existing:
        existing.report_json = report
        insight = existing
    else:
        insight = InsightReport(project_id=project_id, report_json=report)
    session.add(insight)
    project.status = "completed"
    project.error = None
    session.add(project)
    session.commit()
    session.refresh(insight)
    if progress:
        await progress(1.0, "Engagement insights ready")
    return insight
