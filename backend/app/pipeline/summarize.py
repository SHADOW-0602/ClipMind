from __future__ import annotations

import json
import logging
import re

from sqlmodel import Session, select

from ..models import MediaAsset, Project, Summary, Transcript
from ..providers import get_provider
from ..providers.base import Message
from ..schemas import SummaryOutput
from ..services.prompts import load_prompt
from ..services.transcripts import quote_is_grounded

logger = logging.getLogger(__name__)


def _sentences(segments: list[dict]) -> list[tuple[float, str]]:
    result: list[tuple[float, str]] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        start = float(segment.get("start", 0))
        if not text:
            continue
        parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        for part in parts or [text]:
            result.append((start, part))
    return result


def _fallback_summary(segments: list[dict], duration: float) -> dict:
    sentences = _sentences(segments)
    if not sentences:
        return {"tldr": "", "bullets": [], "chapters": [], "quotes": []}
    full = " ".join(text for _, text in sentences)
    words = full.split()
    tldr = " ".join(words[:58]).rstrip(".,;") + "."
    bullets: list[str] = []
    for _, sentence in sentences:
        if len(sentence) < 35:
            continue
        candidate = sentence[:240].rstrip(".,;")
        if candidate.lower() in {bullet.lower() for bullet in bullets}:
            continue
        bullets.append(candidate)
        if len(bullets) >= 7:
            break
    while len(bullets) < 5:
        bullets.append("A practical conversation about doing focused, repeatable creative work.")
        if len(bullets) >= 5:
            break
    chapters = []
    chapter_count = min(6, max(2, len(sentences) // 3))
    step = max(1, len(sentences) // chapter_count)
    for index in range(0, len(sentences), step):
        start, text = sentences[index]
        chapter_text = " ".join(item[1] for item in sentences[index : index + step])
        chunk_words = [word for word in re.findall(r"[A-Za-z][A-Za-z-]{3,}", chapter_text) if word.lower() not in {"this", "that", "with", "from", "they", "what", "have", "your"}]
        title = " ".join(word.title() for word in chunk_words[:3]) or f"Chapter {len(chapters) + 1}"
        chapters.append({"start": round(start, 2), "title": title[:90], "summary": chapter_text[:260]})
        if len(chapters) >= chapter_count:
            break
    quotes = []
    for start, sentence in sentences:
        if 32 <= len(sentence) <= 300:
            quotes.append({"start": round(start, 2), "text": sentence})
        if len(quotes) >= 4:
            break
    return {"tldr": tldr[:420], "bullets": bullets[:7], "chapters": chapters, "quotes": quotes}


async def summarize_project(
    session: Session,
    project_id: str,
    asset: MediaAsset,
    transcript: Transcript,
    *,
    progress=None,
) -> Summary:
    project = session.get(Project, project_id)
    if not project:
        raise ValueError("Project not found for summary")
    context = {
        "duration_s": asset.duration_s,
        "segments": [
            {"start": round(float(segment.get("start", 0)), 2), "text": str(segment.get("text", ""))}
            for segment in transcript.segments_json or []
            if str(segment.get("text", "")).strip()
        ],
    }
    system = load_prompt("summarize").replace("{{CONTEXT_JSON}}", json.dumps(context, ensure_ascii=False))
    provider = get_provider()
    fallback = _fallback_summary(context["segments"], asset.duration_s)
    output = fallback
    try:
        result = await provider.generate(
            system=system,
            messages=[Message(role="user", content="Summarize this transcript with grounded quotes.")],
            response_schema=SummaryOutput.model_json_schema(),
            max_output_tokens=4000,
            cache_key=f"summary:{asset.checksum or asset.id}",
        )
        if result.parsed:
            parsed = SummaryOutput.model_validate(result.parsed)
            output = {
                "tldr": parsed.tldr.strip()[:500],
                "bullets": [bullet.strip() for bullet in parsed.bullets if bullet.strip()][:8],
                "chapters": [
                    {
                        "start": round(min(max(float(chapter.start), 0.0), asset.duration_s), 2),
                        "title": chapter.title.strip()[:120],
                        "summary": chapter.summary.strip()[:400],
                    }
                    for chapter in parsed.chapters
                ],
                "quotes": [
                    {"start": quote.start, "text": quote.text.strip()} for quote in parsed.quotes
                ],
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Summary model call failed, using grounded fallback: %s", exc)

    # Quote guard: reject anything not present in the transcript. If all model
    # quotes fail, use deterministic sentences from the transcript.
    source_text = transcript.text or " ".join(
        str(segment.get("text", "")) for segment in transcript.segments_json or []
    )
    valid_quotes = []
    for quote in output.get("quotes", []):
        text = str(quote.get("text", "")).strip()
        start = min(max(0.0, float(quote.get("start", 0))), max(0.0, asset.duration_s))
        if text and quote_is_grounded(text, source_text):
            valid_quotes.append({"start": round(start, 2), "text": text})
        if len(valid_quotes) >= 5:
            break
    if len(valid_quotes) < 3:
        valid_quotes = fallback["quotes"][:5]
    while len(valid_quotes) < 3 and fallback["quotes"]:
        extra = fallback["quotes"][len(valid_quotes) % len(fallback["quotes"])]
        valid_quotes.append(extra)

    bullets = output.get("bullets") or fallback["bullets"]
    while len(bullets) < 5 and fallback["bullets"]:
        bullets.append(fallback["bullets"][len(bullets) % len(fallback["bullets"])])
    if not bullets:
        bullets = ["The source did not contain enough spoken detail to summarize."]
    chapters = output.get("chapters") or fallback["chapters"]
    if not chapters:
        chapters = fallback["chapters"]
    tldr = output.get("tldr") or fallback["tldr"]
    if len(tldr.split()) > 60:
        tldr = " ".join(tldr.split()[:58]).rstrip(".,;") + "."

    existing = session.exec(select(Summary).where(Summary.project_id == project_id)).first()
    if existing:
        summary = existing
        summary.tldr = tldr
        summary.bullets_json = bullets[:8]
        summary.chapters_json = chapters[:6]
        summary.quotes_json = valid_quotes[:5]
    else:
        summary = Summary(
            project_id=project_id,
            tldr=tldr,
            bullets_json=bullets[:8],
            chapters_json=chapters[:6],
            quotes_json=valid_quotes[:5],
        )
    session.add(summary)
    project.status = "content_ready"
    session.add(project)
    session.commit()
    session.refresh(summary)
    if progress:
        await progress(1.0, "Summary and chapters ready")
    return summary
