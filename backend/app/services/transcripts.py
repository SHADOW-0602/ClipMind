from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from ..schemas import SummaryQuote


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).lower()
    text = re.sub(r"[^a-z0-9\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def quote_is_grounded(quote: str, source_text: str, threshold: float = 0.82) -> bool:
    """Fuzzy check that a quote exists in the source, allowing cleanup edits."""
    if not quote.strip() or not source_text.strip():
        return False
    normalized_quote = normalize_for_match(quote)
    normalized_source = normalize_for_match(source_text)
    if not normalized_quote:
        return False
    if normalized_quote in normalized_source:
        return True
    quote_words = normalized_quote.split()
    source_words = normalized_source.split()
    window = len(quote_words)
    if window == 0:
        return False
    best = 0.0
    # Compare against same-sized sliding windows, capped for long transcripts.
    step = max(1, (len(source_words) - window) // 200)
    for index in range(0, max(1, len(source_words) - window + 1), step):
        ratio = SequenceMatcher(
            None, quote_words, source_words[index : index + window], autojunk=False
        ).ratio()
        best = max(best, ratio)
        if best >= threshold:
            return True
    return best >= threshold


def validate_summary_quotes(
    quotes: list[SummaryQuote], source_text: str, duration: float
) -> list[dict]:
    valid: list[dict] = []
    for quote in quotes:
        if not quote_is_grounded(quote.text, source_text):
            continue
        start = min(max(0.0, quote.start), max(0.0, duration))
        valid.append({"start": round(start, 3), "text": quote.text.strip()})
    return valid


def synthesize_words(text: str, start: float, end: float) -> list[dict]:
    words = text.split()
    if not words:
        return []
    end = max(start + 0.5, end)
    step = (end - start) / len(words)
    return [
        {"start": round(start + index * step, 3), "end": round(start + (index + 1) * step, 3), "word": word}
        for index, word in enumerate(words)
    ]


def build_segments_from_text(text: str, duration: float | None = None) -> list[dict]:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text.strip()) if sentence.strip()]
    if not sentences:
        return []
    words_per_second = 2.45
    estimated = sum(max(1, len(sentence.split())) for sentence in sentences) / words_per_second
    total = duration or max(estimated, 1.0)
    effective_wps = sum(max(1, len(sentence.split())) for sentence in sentences) / total
    cursor = 0.0
    segments: list[dict] = []
    for sentence in sentences:
        word_count = max(1, len(sentence.split()))
        seg_duration = word_count / max(effective_wps, 0.1)
        start = round(cursor, 3)
        end = round(min(total, cursor + seg_duration), 3)
        if end <= start:
            break
        segments.append(
            {
                "start": start,
                "end": end,
                "text": sentence,
                "speaker": "A",
                "words": synthesize_words(sentence, start, end),
            }
        )
        cursor = end
    return segments


def flatten_words(segments: list[dict]) -> list[dict]:
    words: list[dict] = []
    for segment in segments:
        segment_words = segment.get("words") or []
        if segment_words:
            words.extend(segment_words)
            continue
        start, end = float(segment.get("start", 0)), float(segment.get("end", 0))
        words.extend(synthesize_words(str(segment.get("text", "")), start, end))
    return sorted(words, key=lambda item: float(item.get("start", 0)))


def transcript_text(segments: list[dict]) -> str:
    return " ".join(str(segment.get("text", "")).strip() for segment in segments).strip()


def timestamp_label(seconds: float) -> str:
    seconds = max(0, seconds)
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{sec:02d}" if hours else f"{minutes}:{sec:02d}"


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def ass_timestamp(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, centiseconds = divmod(centiseconds, 360_000)
    minutes, centiseconds = divmod(centiseconds, 6_000)
    secs, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ClipMind,Arial,54,&H00FFFFFF,&H00FFFFFF,&H000A0B10,&H90000000,-1,0,0,0,100,100,0,0,1,2.5,0,2,80,80,190,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_ass(segments: list[dict], clip_start: float = 0.0, clip_end: float | None = None) -> str:
    """Build a styled ASS caption file with explicit 1080x1920 PlayRes.

    SRT has no canvas size; libass would fall back to a 384x288 virtual canvas
    and scale FontSize/MarginV unpredictably. An ASS header keeps captions at
    the intended pixel size on the vertical render.
    """
    cues = sentence_cues(segments)
    lines: list[str] = [ASS_HEADER.rstrip()]
    for cue in cues:
        start = float(cue["start"])
        end = float(cue["end"])
        if clip_end is not None and (end <= clip_start or start >= clip_end):
            continue
        start = max(start, clip_start) - clip_start
        end = min(end, clip_end if clip_end is not None else end) - clip_start
        if end <= start:
            continue
        text = str(cue["text"]).replace("{", "(").replace("}", ")").replace("\n", "\\N")
        lines.append(
            f"Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(end)},ClipMind,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"


def sentence_cues(segments: list[dict], min_chars: int = 18, max_duration: float = 6.0) -> list[dict]:
    """Group word-level transcript data into readable caption cues."""
    cues: list[dict] = []
    for segment in segments:
        words = segment.get("words") or []
        if not words:
            text = str(segment.get("text", "")).strip()
            if text:
                cues.append({"start": float(segment.get("start", 0)), "end": float(segment.get("end", 0)), "text": text})
            continue
        current: list[dict] = []
        for word in words:
            current.append(word)
            text = " ".join(str(item.get("word", "")) for item in current).strip()
            duration = float(current[-1].get("end", 0)) - float(current[0].get("start", 0))
            punctuation_end = text.endswith((".", "!", "?", ";", ":"))
            if (len(text) >= min_chars and (punctuation_end or duration >= max_duration)) or duration >= 8:
                cues.append(
                    {
                        "start": float(current[0].get("start", 0)),
                        "end": float(current[-1].get("end", 0)),
                        "text": text,
                    }
                )
                current = []
        if current:
            cues.append(
                {
                    "start": float(current[0].get("start", 0)),
                    "end": float(current[-1].get("end", 0)),
                    "text": " ".join(str(item.get("word", "")) for item in current).strip(),
                }
            )
    return cues


def build_srt(segments: list[dict], clip_start: float = 0.0, clip_end: float | None = None) -> str:
    cues = sentence_cues(segments)
    lines: list[str] = []
    index = 1
    for cue in cues:
        start = float(cue["start"])
        end = float(cue["end"])
        if clip_end is not None and (end <= clip_start or start >= clip_end):
            continue
        if end <= clip_start:
            continue
        start = max(start, clip_start) - clip_start
        end = min(end, clip_end if clip_end is not None else end) - clip_start
        if end <= start:
            continue
        lines.extend([str(index), f"{srt_timestamp(start)} --> {srt_timestamp(end)}", cue["text"], ""])
        index += 1
    return "\n".join(lines).strip() + "\n"


def snap_to_words(
    start: float,
    end: float,
    words: list[dict],
    min_s: float,
    max_s: float,
    duration: float,
) -> tuple[float, float]:
    if not words:
        snapped_start = max(0.0, min(start, max(0.0, duration - min_s)))
        return round(snapped_start, 2), round(min(duration, snapped_start + min(max_s, max(min_s, end - start))), 2)
    sorted_words = sorted(words, key=lambda item: float(item.get("start", 0)))
    # Start at the nearest word start at or before the requested point, favouring onset.
    start_candidates = [w for w in sorted_words if abs(float(w["start"]) - start) <= 1.2]
    chosen_start = float(start)
    if start_candidates:
        chosen_start = min(start_candidates, key=lambda w: abs(float(w["start"]) - start))["start"]
    chosen_start = max(0.0, min(float(chosen_start), max(0.0, duration - min_s)))
    # Find a word ending at/after the requested end, but keep within max duration.
    end_candidates = [
        float(w["end"])
        for w in sorted_words
        if float(w["end"]) >= chosen_start + min_s and float(w["end"]) <= chosen_start + max_s
    ]
    if end_candidates:
        target = chosen_start + max(min_s, min(max_s, end - chosen_start))
        chosen_end = min(end_candidates, key=lambda candidate: abs(candidate - target))
    else:
        chosen_end = min(duration, chosen_start + min(max_s, max(min_s, end - chosen_start)))
    if chosen_end - chosen_start < min_s:
        chosen_end = min(duration, chosen_start + min_s)
    if chosen_end <= chosen_start:
        chosen_end = min(duration, chosen_start + min_s)
    return round(float(chosen_start), 2), round(float(chosen_end), 2)


def dedupe_intervals(intervals: list[tuple[float, float]], min_gap: float = 1.0) -> list[tuple[float, float]]:
    selected: list[tuple[float, float]] = []
    for start, end in sorted(intervals, key=lambda item: item[0]):
        if any(not (end <= other_start - min_gap or start >= other_end + min_gap) for other_start, other_end in selected):
            continue
        selected.append((start, end))
    return selected
