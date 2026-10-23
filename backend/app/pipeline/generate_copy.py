from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlmodel import Session, select

from ..models import BrandProfile, Clip, CopyVariant, Project, Transcript
from ..providers import get_provider
from ..providers.base import Message
from ..schemas import PLATFORMS, CopyOutput
from ..services.prompts import brand_block, load_prompt
from ..services.transcripts import flatten_words, quote_is_grounded

logger = logging.getLogger(__name__)

PLATFORM_HASHTAGS = {
    "instagram": ["#Reels", "#CreatorTips", "#Storytelling", "#ContentStrategy", "#BehindTheScenes"],
    "youtube": ["#Shorts", "#CreatorEconomy", "#YouTubeShorts", "#ContentTips", "#Growth"],
    "tiktok": ["#TikTokCreators", "#CreatorTips", "#StoryTime", "#ContentHacks", "#LearnOnTikTok"],
    "linkedin": ["#ContentStrategy", "#CreatorEconomy", "#Marketing", "#Leadership", "#B2B"],
    "x": ["#ContentStrategy", "#Creators", "#Marketing", "#AI", "#BuildInPublic"],
}


def clip_transcript(transcript: Transcript, start: float, end: float) -> str:
    words = flatten_words(transcript.segments_json or [])
    return re.sub(
        r"\s+",
        " ",
        " ".join(
            str(word.get("word", "")).strip()
            for word in words
            if float(word.get("end", 0)) > start and float(word.get("start", 0)) < end
        ),
    ).strip()


def _brand_dict(brand: BrandProfile | None) -> dict | None:
    return brand.model_dump(mode="json") if brand else None


def _banned_hits(texts: list[str], banned: list[str]) -> list[str]:
    joined = "\n".join(texts)
    hits: list[str] = []
    for word in banned:
        if word and re.search(rf"(?<!\w){re.escape(word)}(?!\w)", joined, re.IGNORECASE):
            hits.append(word)
    return hits


def _scrub_banned(text: str, banned: list[str]) -> str:
    for word in banned:
        if not word:
            continue
        text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", "this", text, flags=re.IGNORECASE)
    return text


def _hashtags(raw: list[str], platform: str, banned: list[str]) -> list[str]:
    tags: list[str] = []
    for raw_tag in raw:
        tag = raw_tag.strip()
        tag = re.sub(r"[^A-Za-z0-9_]", "", tag.lstrip("#"))
        if not tag:
            continue
        tag = "#" + tag[:40]
        if tag.lower() not in {existing.lower() for existing in tags}:
            tags.append(tag)
    for fallback in PLATFORM_HASHTAGS.get(platform, PLATFORM_HASHTAGS["instagram"]):
        if len(tags) >= 5:
            break
        if fallback.lower() not in {tag.lower() for tag in tags}:
            tags.append(fallback)
    tags = [tag for tag in tags if not _banned_hits([tag], banned)]
    return tags[:8]


def _truncate_caption(caption: str, platform: str, hashtags: list[str]) -> str:
    caption = caption.strip()
    if platform == "x":
        suffix = " " + " ".join(hashtags[:2])
        budget = max(80, 278 - len(suffix))
        if len(caption) > budget:
            caption = caption[: budget - 1].rsplit(" ", 1)[0].rstrip(".,;") + "…"
        return (caption + suffix).strip()[:280]
    if len(caption) > 2400:
        return caption[:2397].rsplit(" ", 1)[0] + "…"
    return caption


def _fallback_copy(
    *,
    clip: Clip,
    text: str,
    platform: str,
    brand: BrandProfile | None,
) -> dict[str, Any]:
    muted = _scrub_banned(text, brand.banned_words if brand else [])
    quote = muted[:220].strip()
    title = _scrub_banned(clip.title, brand.banned_words if brand else [])
    hooks = [
        clip.hook or title,
        f"What most people get wrong about {title.lower()}",
        f"The 30-second version of {title.lower()}",
    ]
    hooks = [_scrub_banned(hook, brand.banned_words if brand else [])[:115] for hook in hooks]
    hashtags = PLATFORM_HASHTAGS.get(platform, PLATFORM_HASHTAGS["instagram"])
    if platform == "linkedin":
        caption = (
            f"{hooks[0]}\n\nMost teams treat this as a tactic. The better frame is a system:\n\n"
            f"{quote}\n\nWhich part would you test first?\n\n{' '.join(hashtags[:5])}"
        )
    elif platform == "x":
        caption = f"{hooks[0]}\n\n{quote[:130]}\n\n{hashtags[0]} {hashtags[1]}"
    else:
        caption = (
            f"{hooks[0]}\n\n{quote}\n\nSave this for your next planning session.\n\n"
            f"{' '.join(hashtags[:5])}"
        )
    return {
        "caption": caption,
        "hooks": hooks,
        "hashtags": hashtags,
        "cta": "Save this and share it with someone building something similar.",
    }


def _validate_copy(
    data: dict[str, Any],
    *,
    clip: Clip,
    text: str,
    platform: str,
    brand: BrandProfile | None,
) -> tuple[dict[str, Any], list[str]]:
    banned = brand.banned_words if brand else []
    try:
        output = CopyOutput.model_validate(data)
    except Exception:  # noqa: BLE001
        output = CopyOutput.model_validate(
            _fallback_copy(clip=clip, text=text, platform=platform, brand=brand)
        )
    caption = output.caption.strip()
    hooks = [hook.strip() for hook in output.hooks if hook.strip()][:3]
    if len(hooks) < 3:
        hooks.extend(
            [
                f"The overlooked part of {clip.title.lower()}",
                f"A better way to think about {clip.title.lower()}",
                "The detail most people skip",
            ][: 3 - len(hooks)]
        )
    hashtags = _hashtags(output.hashtags, platform, banned)
    cta = output.cta.strip()
    hits = _banned_hits([caption, cta, *hooks, *hashtags], banned)
    caption = _scrub_banned(_truncate_caption(caption, platform, hashtags), banned)
    hooks = [_scrub_banned(hook, banned)[:120] for hook in hooks]
    cta = _scrub_banned(cta, banned)
    hashtags = [tag for tag in hashtags if not _banned_hits([tag], banned)]
    cleaned = {
        "caption": caption,
        "hooks": hooks,
        "hashtags": hashtags,
        "cta": cta,
    }
    # Voice don'ts are softer than banned words. Flag rather than silently rewrite.
    return cleaned, [hit for hit in hits if hit]


async def generate_copy_for_clips(
    session: Session,
    project_id: str,
    clips: list[Clip],
    platforms: list[str],
    brand: BrandProfile | None,
    *,
    progress=None,
    feedback: str = "",
    only_clip_id: str | None = None,
) -> None:
    project = session.get(Project, project_id)
    if not project or not clips:
        return
    asset = session.exec(select(Transcript).where(Transcript.asset_id == clips[0].asset_id)).first()
    if not asset:
        raise ValueError("Transcript missing for copy generation")
    provider = get_provider()
    brand_dict = _brand_dict(brand)
    total = max(1, len(clips) * len(platforms))
    done = 0
    for clip in clips:
        if only_clip_id and clip.id != only_clip_id:
            continue
        text = clip_transcript(asset, clip.start, clip.end)
        for platform in platforms:
            if platform not in PLATFORMS:
                continue
            context = {
                "platform": platform,
                "clip": {
                    "start": clip.start,
                    "end": clip.end,
                    "title": clip.title,
                    "hook": clip.hook,
                    "transcript": text,
                    "quote": clip.source_quote,
                },
                "brand": brand_dict,
                "feedback": feedback,
            }
            system = (
                load_prompt("generate_copy")
                .replace("{{BRAND_BLOCK}}", brand_block(brand_dict))
                .replace("{{CONTEXT_JSON}}", json.dumps(context, ensure_ascii=False))
            )
            output: dict[str, Any]
            try:
                result = await provider.generate(
                    system=system,
                    messages=[
                        Message(
                            role="user",
                            content=(
                                f"Write {platform} copy for this {clip.end - clip.start:.1f}-second clip. "
                                f"Feedback: {feedback or 'none'}."
                            ),
                        )
                    ],
                    response_schema=CopyOutput.model_json_schema(),
                    max_output_tokens=1800,
                    cache_key=f"copy:{clip.id}:{platform}:{feedback[:30]}",
                )
                output = result.parsed or _fallback_copy(
                    clip=clip, text=text, platform=platform, brand=brand
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Copy generation failed for %s/%s: %s", clip.id, platform, exc)
                output = _fallback_copy(clip=clip, text=text, platform=platform, brand=brand)

            cleaned, hits = _validate_copy(
                output, clip=clip, text=text, platform=platform, brand=brand
            )
            if hits:
                retry_context = dict(context)
                retry_context["brand_check_violations"] = hits
                retry_system = (
                    load_prompt("generate_copy")
                    .replace("{{BRAND_BLOCK}}", brand_block(brand_dict))
                    .replace("{{CONTEXT_JSON}}", json.dumps(retry_context, ensure_ascii=False))
                )
                try:
                    retry = await provider.generate(
                        system=retry_system,
                        messages=[
                            Message(
                                role="user",
                                content=(
                                    "Rewrite once. Remove every banned word while keeping the meaning. "
                                    "Return the same JSON shape."
                                ),
                            )
                        ],
                        response_schema=CopyOutput.model_json_schema(),
                        max_output_tokens=1800,
                        cache_key=f"copy-retry:{clip.id}:{platform}",
                    )
                    if retry.parsed:
                        cleaned, _ = _validate_copy(
                            retry.parsed, clip=clip, text=text, platform=platform, brand=brand
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Brand retry failed: %s", exc)

            existing = session.exec(
                select(CopyVariant).where(
                    CopyVariant.clip_id == clip.id, CopyVariant.platform == platform
                )
            ).first()
            if existing:
                existing.caption = cleaned["caption"]
                existing.hooks = cleaned["hooks"]
                existing.hashtags = cleaned["hashtags"]
                existing.cta = cleaned["cta"]
                existing.version += 1
                session.add(existing)
            else:
                session.add(
                    CopyVariant(
                        clip_id=clip.id,
                        platform=platform,
                        caption=cleaned["caption"],
                        hooks=cleaned["hooks"],
                        hashtags=cleaned["hashtags"],
                        cta=cleaned["cta"],
                    )
                )
            session.commit()
            done += 1
            if progress:
                await progress(0.05 + 0.9 * done / total, f"Writing {platform} copy")
    project.status = "content_ready"
    session.add(project)
    session.commit()
    if progress:
        await progress(1.0, "Platform copy ready")


def quote_check(quote: str, transcript: Transcript) -> bool:
    return quote_is_grounded(quote, transcript.text)
