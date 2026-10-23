from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session, delete, select

from ..models import (
    BrandProfile,
    Clip,
    CopyVariant,
    InsightReport,
    MediaAsset,
    Project,
    Summary,
    TopicSegment,
    Transcript,
)
from ..providers import get_provider
from ..providers.base import Message
from ..schemas import ClipSelectionOutput, CritiqueOutput
from ..services.prompts import brand_block, load_prompt
from ..services.storage import resolve_inside_data
from ..services.transcripts import (
    flatten_words,
    quote_is_grounded,
    snap_to_words,
    transcript_text,
)

logger = logging.getLogger(__name__)

HOOK_PATTERNS = re.compile(
    r"^(what|why|how|the biggest|the best|the worst|most|nobody|everyone|here'?s|you|"
    r"if you|imagine|stop|let me|one thing|the problem|the truth|i used to|there'?s)",
    re.IGNORECASE,
)
FILLERS = {"um", "uh", "like", "you know", "sort of", "kind of", "basically", "actually"}
SENSITIVE = {
    "suicide": "self_harm_topic",
    "kill yourself": "self_harm_topic",
    "cure": "medical_claim",
    "guarantee": "guaranteed_results",
    "guaranteed": "guaranteed_results",
    "invest": "financial_topic",
    "diagnos": "medical_topic",
    "hate": "hate_speech_review",
}
STOP = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with", "is", "are",
    "was", "were", "it", "this", "that", "you", "your", "we", "our", "i", "me", "my", "as",
    "at", "be", "have", "has", "had", "do", "does", "did", "from", "by", "not", "so", "if",
    "then", "than", "can", "will", "just", "about", "what", "when", "how", "why", "who",
    "there", "they", "them", "he", "she", "his", "her", "its", "would", "could", "should",
}


@dataclass
class Candidate:
    start: float
    end: float
    title: str
    quote: str
    score: float
    text: str
    hook: str = ""
    risk_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "title": self.title,
            "hook": self.hook,
            "quote": self.quote,
            "score": round(self.score, 1),
            "risk_flags": self.risk_flags,
        }


def _clip_text(words: list[dict], start: float, end: float) -> str:
    selected = [
        str(word.get("word", "")).strip()
        for word in words
        if float(word.get("end", 0)) > start and float(word.get("start", 0)) < end
    ]
    return re.sub(r"\s+", " ", " ".join(selected)).strip()


def _keywords(text: str, limit: int = 5) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9'’-]{2,}", text.lower())
    counts = Counter(word for word in words if word not in STOP and word not in FILLERS)
    return [word for word, _ in counts.most_common(limit)]


def _title_from(text: str) -> str:
    cleaned = re.sub(r"^(so|and|but|okay|well|you know|i mean)[,\s]+", "", text.strip(), flags=re.I)
    cleaned = re.sub(r"^(um|uh)[,\s]+", "", cleaned, flags=re.I)
    patterns = [
        r"the [a-z0-9-]+(?:\s+[a-z0-9-]+){0,2} (?:rule|trap|problem|framework|mistake|secret|loop)",
        r"one idea[,\s]+(?:three|two|five) formats",
        r"[a-z0-9-]+(?:\s+[a-z0-9-]+){0,2} is (?:the|a) [a-z0-9-]+(?:\s+[a-z0-9-]+){0,2}",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            title = match.group(0)
            if len(title) > 78:
                title = title[:75].rsplit(" ", 1)[0]
            return title[0].upper() + title[1:]
    first_clause = re.split(r"[,.;!?]", cleaned)[0].strip()
    if 18 <= len(first_clause) <= 82:
        return first_clause[0].upper() + first_clause[1:]
    keywords = _keywords(text, 4)
    if len(keywords) >= 2:
        return f"{(keywords[0] + ' and ' + keywords[1]).title()}: What Actually Matters"
    return "A Moment Worth Revisiting"


def _best_quote(text: str, limit: int = 320) -> str:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
    for sentence in sentences:
        if 28 <= len(sentence) <= limit:
            return sentence
    if sentences:
        return sentences[0][:limit]
    return text[:limit]


def _risk_flags(text: str) -> list[str]:
    lowered = text.lower()
    return sorted({flag for needle, flag in SENSITIVE.items() if needle in lowered})


def _score_window(text: str, duration: float, starts_naturally: bool) -> float:
    score = 52.0
    if HOOK_PATTERNS.search(text):
        score += 10
    if 24 <= duration <= 44:
        score += 8
    elif 18 <= duration <= 55:
        score += 4
    else:
        score -= 6
    if re.search(r"\b\d+\b", text):
        score += 5
    if re.search(r"\byou\b", text, re.IGNORECASE):
        score += 3
    if re.search(r"\b(but|instead|mistake|problem|because|surprising|actually|nobody)\b", text, re.I):
        score += 5
    if re.search(r"[!?]", text):
        score += 2
    if text.endswith((".", "!", "?")):
        score += 3
    else:
        score -= 5
    filler_hits = sum(len(re.findall(rf"\b{re.escape(filler)}\b", text, re.I)) for filler in FILLERS)
    score -= min(10, filler_hits * 1.5)
    if not starts_naturally:
        score -= 5
    if 120 <= len(text.split()) / max(duration, 1) * 60 <= 190:
        score += 4
    score += min(4, len(_keywords(text, 8)) * 0.5)
    return max(0.0, min(98.0, score))


def generate_candidates(
    transcript: Transcript,
    *,
    min_s: int,
    max_s: int,
    limit: int = 24,
) -> list[Candidate]:
    segments = transcript.segments_json or []
    if not segments:
        return []
    duration = max(float(segment.get("end", 0)) for segment in segments)
    words = flatten_words(segments)
    units = [
        {
            "start": max(0.0, float(segment.get("start", 0))),
            "end": min(duration, float(segment.get("end", 0))),
            "text": str(segment.get("text", "")).strip(),
        }
        for segment in segments
        if str(segment.get("text", "")).strip()
    ]
    candidates: list[Candidate] = []
    for index, unit in enumerate(units):
        target_durations = (30.0, 38.0, 46.0)
        for target in target_durations:
            end_limit = min(duration, unit["start"] + max_s)
            end = unit["end"]
            j = index
            while j + 1 < len(units) and units[j + 1]["end"] <= end_limit and end - unit["start"] < target:
                j += 1
                end = units[j]["end"]
            window_duration = end - unit["start"]
            if window_duration < min_s:
                continue
            if window_duration > max_s:
                end = unit["start"] + max_s
                window_duration = end - unit["start"]
            start, end = snap_to_words(
                unit["start"], end, words, min_s=min_s, max_s=max_s, duration=duration
            )
            text = _clip_text(words, start, end)
            if not text:
                continue
            candidate = Candidate(
                start=start,
                end=end,
                title=_title_from(text),
                quote=_best_quote(text),
                score=_score_window(text, end - start, bool(HOOK_PATTERNS.search(text))),
                text=text,
                hook=_hook_from(text),
                risk_flags=_risk_flags(text),
            )
            candidates.append(candidate)
            if window_duration >= target:
                break
    # De-duplicate nearly identical windows and keep the best per start cluster.
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    chosen: list[Candidate] = []
    for candidate in candidates:
        if any(
            candidate.start < existing.end - 1 and candidate.end > existing.start + 1
            for existing in chosen
        ):
            continue
        chosen.append(candidate)
        if len(chosen) >= limit:
            break
    return chosen


def _selected_from_candidate(candidate: Candidate, words: list[dict], duration: float, min_s: int, max_s: int) -> dict:
    start, end = snap_to_words(candidate.start, candidate.end, words, min_s, max_s, duration)
    text = _clip_text(words, start, end)
    return {
        "start": start,
        "end": end,
        "title": candidate.title,
        "hook": candidate.hook or _hook_from(text),
        "source_quote": _best_quote(text),
        "score": candidate.score,
        "rationale": "Chosen for a clear entry point, concrete idea, and resolved ending.",
        "risk_flags": candidate.risk_flags,
        "critique": {"verdict": "pass", "notes": "Passed deterministic transcript and boundary checks."},
    }


def _hook_from(text: str) -> str:
    first = re.split(r"(?<=[.!?])\s+", text.strip())[0]
    if 20 <= len(first) <= 115:
        return first.rstrip(".")
    keywords = _keywords(text, 4)
    if keywords:
        return f"The overlooked truth about {' '.join(keywords[:2])}"
    return "This changes how you think about the work"


def _non_overlapping(proposals: list[dict], min_gap: float = 0.5) -> list[dict]:
    selected: list[dict] = []
    for proposal in sorted(proposals, key=lambda item: float(item.get("score", 0)), reverse=True):
        if any(
            float(proposal["start"]) < float(existing["end"]) - min_gap
            and float(proposal["end"]) > float(existing["start"]) + min_gap
            for existing in selected
        ):
            continue
        selected.append(proposal)
    return sorted(selected, key=lambda item: float(item["start"]))


def _validated_proposal(
    proposal: Any,
    *,
    words: list[dict],
    duration: float,
    min_s: int,
    max_s: int,
    full_text: str,
) -> dict | None:
    try:
        start = float(proposal.start)
        end = float(proposal.end)
    except (AttributeError, TypeError, ValueError):
        return None
    start, end = snap_to_words(start, end, words, min_s, max_s, duration)
    if end <= start:
        return None
    text = _clip_text(words, start, end)
    if not text:
        return None
    quote = str(getattr(proposal, "quote", "") or "").strip()
    risk_flags = list(getattr(proposal, "risk_flags", []) or [])
    if not quote_is_grounded(quote, full_text):
        quote = _best_quote(text)
        risk_flags.append("quote_corrected")
    title = str(getattr(proposal, "title", "") or "").strip() or _title_from(text)
    hook = str(getattr(proposal, "hook", "") or "").strip() or _hook_from(text)
    score = float(getattr(proposal, "score", 75))
    return {
        "start": start,
        "end": min(duration, max(start + min_s, end)),
        "title": title[:120],
        "hook": hook[:180],
        "source_quote": quote,
        "score": max(0.0, min(100.0, score)),
        "rationale": str(getattr(proposal, "rationale", "") or "")[:800],
        "risk_flags": sorted(set(risk_flags)),
        "critique": {"verdict": "pass", "notes": "Grounded quote and valid boundaries."},
    }


def _apply_brand_guard(item: dict, brand: BrandProfile | None) -> dict:
    if not brand or not brand.banned_words:
        return item
    changed = False
    for key in ("title", "hook"):
        value = str(item.get(key, ""))
        for word in brand.banned_words:
            if not word:
                continue
            pattern = rf"(?<!\w){re.escape(word)}(?!\w)"
            if re.search(pattern, value, re.IGNORECASE):
                value = re.sub(pattern, "this", value, flags=re.IGNORECASE)
                changed = True
        item[key] = value
    quote = str(item.get("source_quote", ""))
    for word in brand.banned_words:
        if not word:
            continue
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", quote, re.IGNORECASE):
            # A scrubbed quote would no longer be grounded; omit it instead.
            item["source_quote"] = ""
            changed = True
            break
    if changed:
        item["risk_flags"] = sorted(set(item.get("risk_flags", [])) | {"brand_word_scrubbed"})
    return item


async def select_clips(
    session: Session,
    project_id: str,
    asset_id: str,
    transcript: Transcript,
    *,
    n_clips: int = 8,
    min_s: int = 15,
    max_s: int = 60,
    brand: BrandProfile | None = None,
    progress=None,
    feedback: str = "",
) -> list[Clip]:
    project = session.get(Project, project_id)
    asset = session.get(MediaAsset, asset_id)
    if not project or not asset:
        raise ValueError("Project or asset missing for clip selection")
    duration = asset.duration_s or max(
        (float(segment.get("end", 0)) for segment in transcript.segments_json or []), default=0.0
    )
    words = flatten_words(transcript.segments_json or [])
    full_text = transcript.text or transcript_text(transcript.segments_json or [])
    candidates = generate_candidates(transcript, min_s=min_s, max_s=max_s, limit=max(n_clips * 3, 18))
    if progress:
        await progress(0.08, f"Scoring {len(candidates)} candidate moments")

    topics = session.exec(select(TopicSegment)).all()
    topic_context = [
        {
            "start": segment.start,
            "end": segment.end,
            "topic": segment.topic,
            "summary": segment.summary,
            "energy": segment.energy_score,
        }
        for segment in topics
        if segment.asset_id == asset_id
    ]
    brand_dict = brand.model_dump() if brand else None
    context = {
        "n_clips": n_clips,
        "min_clip_s": min_s,
        "max_clip_s": max_s,
        "duration_s": round(duration, 2),
        "topics": topic_context,
        "candidates": [candidate.to_dict() for candidate in candidates],
        "feedback": feedback,
    }
    system = (
        load_prompt("select_clips")
        .replace("{{CONTEXT_JSON}}", json.dumps(context, ensure_ascii=False))
        .replace("{{BRAND_BLOCK}}", brand_block(brand_dict))
    )
    provider = get_provider()
    selected: list[dict] = []
    try:
        result = await provider.generate(
            system=system,
            messages=[
                Message(
                    role="user",
                    content=(
                        f"Choose up to {n_clips} non-overlapping clips between {min_s} and {max_s} seconds. "
                        f"Feedback to honor: {feedback or 'none'}."
                    ),
                )
            ],
            response_schema=ClipSelectionOutput.model_json_schema(),
            max_output_tokens=5000,
            cache_key=f"select:{asset.checksum or asset.id}:{n_clips}:{min_s}:{max_s}:{feedback[:40]}",
        )
        if result.parsed:
            parsed = ClipSelectionOutput.model_validate(result.parsed)
            for proposal in parsed.clips:
                validated = _validated_proposal(
                    proposal,
                    words=words,
                    duration=duration,
                    min_s=min_s,
                    max_s=max_s,
                    full_text=full_text,
                )
                if validated:
                    selected.append(validated)
        if progress:
            await progress(0.55, f"Proposed {len(selected)} clips")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Model clip selection failed, using deterministic candidates: %s", exc)

    # Self-critique loop against transcript + brand. The model cannot bypass the
    # deterministic checks above; critique can only trim/reject, never invent.
    if selected:
        critique_context = {
            "brand": brand_dict,
            "candidates": [
                {
                    "title": item["title"],
                    "quote": item["source_quote"],
                    "start": item["start"],
                    "end": item["end"],
                }
                for item in selected
            ],
        }
        critique_system = (
            load_prompt("critique_clips")
            .replace("{{BRAND_BLOCK}}", brand_block(brand_dict))
            .replace("{{CONTEXT_JSON}}", json.dumps(critique_context, ensure_ascii=False))
        )
        try:
            critique_result = await provider.generate(
                system=critique_system,
                messages=[Message(role="user", content="Critique each clip before final selection.")],
                response_schema=CritiqueOutput.model_json_schema(),
                max_output_tokens=2500,
                cache_key=f"critique:{asset.checksum or asset.id}:{len(selected)}",
            )
            if critique_result.parsed:
                critique = CritiqueOutput.model_validate(critique_result.parsed)
                kept: list[dict] = []
                for index, item in enumerate(selected):
                    verdict = next((entry for entry in critique.clips if entry.clip_index == index), None)
                    if verdict:
                        item["critique"] = {
                            "verdict": verdict.verdict,
                            "notes": verdict.notes,
                            "fixes": verdict.fixes,
                        }
                        if verdict.verdict == "reject":
                            project.error = f"Self-critique rejected one clip: {verdict.notes}"
                            continue
                        if verdict.fixes:
                            item["risk_flags"] = sorted(set(item["risk_flags"] + verdict.fixes[:3]))
                    kept.append(item)
                selected = kept
            if progress:
                await progress(0.86, "Brand and quote critique complete")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Critique stage skipped after error: %s", exc)

    # Ensure output quality even if the model returns too few clips.
    if len(selected) < min(n_clips, 3):
        for candidate in candidates:
            if any(
                candidate.start < item["end"] - 1 and candidate.end > item["start"] + 1
                for item in selected
            ):
                continue
            selected.append(_selected_from_candidate(candidate, words, duration, min_s, max_s))
            if len(selected) >= min(n_clips, 3):
                break

    selected = _non_overlapping(selected)[:n_clips]
    selected.sort(key=lambda item: float(item.get("score", 0)), reverse=True)
    selected = selected[:n_clips]
    selected.sort(key=lambda item: float(item["start"]))
    selected = [_apply_brand_guard(item, brand) for item in selected]

    if not selected and duration >= min_s:
        start = 0.0
        end = min(duration, max(min_s, min(duration, 45.0)))
        text = _clip_text(words, start, end)
        selected = [
            {
                "start": start,
                "end": end,
                "title": _title_from(text),
                "hook": _hook_from(text),
                "source_quote": _best_quote(text),
                "score": 60.0,
                "rationale": "Single available moment from a short source.",
                "risk_flags": _risk_flags(text),
                "critique": {"verdict": "pass", "notes": "Short-source fallback."},
            }
        ]

    old_clips = session.exec(select(Clip).where(Clip.project_id == project_id)).all()
    for old_clip in old_clips:
        session.exec(delete(CopyVariant).where(CopyVariant.clip_id == old_clip.id))
        for stored in (old_clip.render_path, old_clip.srt_path, old_clip.thumbnail_path):
            if not stored:
                continue
            try:
                path = resolve_inside_data(stored)
                if path:
                    path.unlink(missing_ok=True)
            except ValueError:
                pass
    session.exec(delete(Clip).where(Clip.project_id == project_id))
    session.exec(delete(Summary).where(Summary.project_id == project_id))
    session.exec(delete(InsightReport).where(InsightReport.project_id == project_id))
    session.commit()
    rows: list[Clip] = []
    for item in selected:
        clip = Clip(
            project_id=project_id,
            asset_id=asset_id,
            start=float(item["start"]),
            end=float(item["end"]),
            title=str(item["title"]),
            hook=str(item["hook"]),
            source_quote=str(item.get("source_quote", "")),
            score=float(item["score"]),
            rationale=str(item.get("rationale", "")),
            status="selected",
            risk_flags_json=list(item.get("risk_flags", [])),
            critique_json=item.get("critique", {}),
        )
        session.add(clip)
        rows.append(clip)
    project.status = "clips_ready"
    session.add(project)
    session.commit()
    for row in rows:
        session.refresh(row)
    if progress:
        await progress(1.0, f"Selected {len(rows)} clips")
    logger.info("Selected %d clips for project %s", len(rows), project_id)
    return rows
