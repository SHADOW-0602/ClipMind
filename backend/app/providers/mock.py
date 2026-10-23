from __future__ import annotations

import json
import re
import time
from collections import Counter
from typing import Any

from ..config import Settings
from ..services.costs import log_model_call
from .base import ImageInput, Message, ModelResult, ToolSpec, VideoInput

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with", "is",
    "are", "was", "were", "it", "this", "that", "you", "your", "we", "our", "i", "me",
    "my", "as", "at", "be", "have", "has", "had", "do", "does", "did", "from", "by",
    "not", "so", "if", "then", "than", "can", "will", "just", "about", "what", "when",
    "how", "why", "who", "into", "up", "out", "one", "get", "got",
}

PLATFORM_HASHTAGS = {
    "instagram": ["#Reels", "#CreatorTips", "#BehindTheScenes", "#Storytelling", "#ContentStrategy"],
    "youtube": ["#Shorts", "#CreatorEconomy", "#YouTubeShorts", "#ContentTips", "#Growth"],
    "tiktok": ["#TikTokCreators", "#CreatorTips", "#StoryTime", "#ContentHacks", "#LearnOnTikTok"],
    "linkedin": ["#ContentStrategy", "#CreatorEconomy", "#Marketing", "#Leadership", "#B2B"],
    "x": ["#ContentStrategy", "#Creators", "#Marketing", "#AI", "#BuildInPublic"],
}


def _extract_context(system: str) -> dict[str, Any]:
    marker = "CONTEXT_JSON:"
    end_marker = "END_CONTEXT_JSON"
    start = system.find(marker)
    if start < 0:
        return {}
    start += len(marker)
    end = system.find(end_marker, start)
    blob = system[start:end if end >= 0 else None].strip()
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return {}


def _purpose(system: str) -> str:
    match = re.search(r"TASK:\s*([a-z_]+)", system)
    return match.group(1) if match else "generic"


def _keywords(text: str, limit: int = 6) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text.lower())
    counts = Counter(word for word in words if word not in STOP_WORDS)
    return [word for word, _ in counts.most_common(limit)]


def _scrub(text: str, banned: list[str]) -> str:
    for word in banned:
        if not word.strip():
            continue
        text = re.sub(re.escape(word), "this idea", text, flags=re.IGNORECASE)
    return text


def _clean_hashtag(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", value.title())
    return f"#{cleaned}" if cleaned else ""


class MockProvider:
    """Deterministic, grounded canned responses for offline development and tests."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = "mock-muse-spark"

    async def generate(
        self,
        *,
        system: str,
        messages: list[Message],
        images: list[ImageInput] | None = None,
        video: VideoInput | None = None,
        tools: list[ToolSpec] | None = None,
        response_schema: dict[str, Any] | None = None,
        max_output_tokens: int = 2000,
        cache_key: str | None = None,
    ) -> ModelResult:
        started = time.perf_counter()
        purpose = _purpose(system)
        context = _extract_context(system)
        parsed = self._generate_purpose(purpose, context, messages)
        text = json.dumps(parsed, ensure_ascii=False)
        input_text = system + "\n".join(message.content for message in messages)
        input_tokens = max(1, len(input_text) // 4)
        output_tokens = max(1, len(text) // 4)
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_model_call(
            provider="mock",
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=0,
            cost_usd=0.0,
            latency_ms=latency_ms,
            purpose=purpose,
        )
        return ModelResult(
            text=text,
            parsed=parsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=0,
            cost_usd=0.0,
            latency_ms=latency_ms,
            model=self.model,
            provider="mock",
        )

    def _generate_purpose(
        self, purpose: str, context: dict[str, Any], messages: list[Message]
    ) -> dict[str, Any]:
        if purpose == "understand_segments":
            return self._understand(context)
        if purpose == "select_clips":
            return self._select(context)
        if purpose == "critique_clips":
            return self._critique(context)
        if purpose == "generate_copy":
            return self._copy(context)
        if purpose == "summarize":
            return self._summary(context)
        if purpose == "insights":
            return self._insights(context)
        return {"message": "Mock provider response", "purpose": purpose}

    def _understand(self, context: dict[str, Any]) -> dict[str, Any]:
        input_segments = context.get("segments") or []
        if not input_segments:
            return {"segments": []}
        grouped: list[dict[str, Any]] = []
        chunk_size = max(2, min(5, len(input_segments) // 3 or 2))
        for index in range(0, len(input_segments), chunk_size):
            group = input_segments[index : index + chunk_size]
            text = " ".join(str(item.get("text", "")) for item in group).strip()
            if not text:
                continue
            keywords = _keywords(text, 4)
            topic = " ".join(word.title() for word in keywords[:3]) or f"Part {len(grouped) + 1}"
            summary = text
            if len(summary) > 260:
                summary = summary[:257].rsplit(" ", 1)[0] + "…"
            energy = 0.55 + min(0.35, text.count("!") * 0.08 + text.count("?") * 0.04)
            grouped.append(
                {
                    "start": float(group[0].get("start", 0)),
                    "end": float(group[-1].get("end", group[-1].get("start", 0))),
                    "topic": topic,
                    "summary": summary,
                    "sentiment": "positive" if "!" in text or "love" in text.lower() else "neutral",
                    "energy_score": round(min(0.98, energy), 2),
                    "speaker_intent": "Explain a useful idea and persuade the audience to act.",
                    "quotable": "?" in text or any(char.isdigit() for char in text) or "!" in text,
                }
            )
        return {"segments": grouped}

    def _select(self, context: dict[str, Any]) -> dict[str, Any]:
        candidates = context.get("candidates") or []
        n_clips = int(context.get("n_clips") or 8)
        clips = []
        for candidate in candidates[:n_clips]:
            title = str(candidate.get("title") or "A moment worth sharing").strip()
            quote = str(candidate.get("quote") or "").strip()
            hook = self._hook_from(quote, title)
            clips.append(
                {
                    "start": float(candidate.get("start", 0)),
                    "end": float(candidate.get("end", 0)),
                    "title": title[:90],
                    "hook": hook[:150],
                    "score": round(float(candidate.get("score", 72)), 1),
                    "rationale": (
                        "Self-contained moment with a clear idea, natural entry point, and a "
                        "resolved ending. The opening line creates curiosity without a context gap."
                    ),
                    "quote": quote[:400],
                    "risk_flags": list(candidate.get("risk_flags") or []),
                }
            )
        return {"clips": clips}

    @staticmethod
    def _hook_from(quote: str, title: str) -> str:
        first_sentence = re.split(r"(?<=[.!?])\s+", quote.strip())[0] if quote else ""
        if 20 <= len(first_sentence) <= 110:
            return first_sentence.rstrip(".")
        return f"The part of {title.lower()} most people miss"

    def _critique(self, context: dict[str, Any]) -> dict[str, Any]:
        candidates = context.get("candidates") or []
        brand = context.get("brand") or {}
        banned = [word.lower() for word in brand.get("banned_words") or []]
        results = []
        for index, candidate in enumerate(candidates):
            haystack = f"{candidate.get('title', '')} {candidate.get('quote', '')}".lower()
            flagged = [word for word in banned if word and word in haystack]
            results.append(
                {
                    "clip_index": index,
                    "verdict": "reject" if flagged else "pass",
                    "notes": (
                        f"Brand risk: {', '.join(flagged)}" if flagged else
                        "Starts mid-thought check passed; quote is grounded in the transcript."
                    ),
                    "fixes": flagged,
                }
            )
        return {"clips": results}

    def _copy(self, context: dict[str, Any]) -> dict[str, Any]:
        clip = context.get("clip") or {}
        brand = context.get("brand") or {}
        platform = str(context.get("platform") or "instagram").lower()
        banned = list(brand.get("banned_words") or [])
        quote = str(clip.get("quote") or clip.get("transcript") or "").strip()
        title = str(clip.get("title") or "The insight everyone needs").strip()
        keywords = _keywords(quote + " " + title, 4)
        topic = " ".join(keywords[:2]) or "the bigger picture"
        hook_variants = [
            self._hook_from(quote, title),
            f"What most people get wrong about {topic}",
            f"The 30-second version of {title.lower()}",
        ]
        hooks = [_scrub(hook, banned)[:110] for hook in hook_variants]
        hashtags = PLATFORM_HASHTAGS.get(platform, PLATFORM_HASHTAGS["instagram"])[:]
        for keyword in keywords[:2]:
            tag = _clean_hashtag(keyword)
            if tag and tag not in hashtags:
                hashtags.append(tag)
        hashtags = hashtags[:8]
        if platform == "linkedin":
            caption = (
                f"{hooks[0]}\n\nMost teams treat {topic} like a tactic. The better frame: "
                "build a repeatable system, then let the ideas compound.\n\n"
                f"One practical takeaway from this conversation: {quote[:220].strip()}\n\n"
                f"Which part would you try first?\n\n{' '.join(hashtags[:5])}"
            )
        elif platform == "x":
            caption = f"{hooks[0]}\n\n{quote[:150].strip()}\n\n{hashtags[0]} {hashtags[1]}"
        elif platform == "youtube":
            caption = (
                f"{hooks[0]}\n\n{quote[:210].strip()}\n\n"
                f"Follow for more practical breakdowns.\n\n{' '.join(hashtags[:5])}"
            )
        elif platform == "tiktok":
            caption = (
                f"{hooks[0]} 👀\n\n{quote[:170].strip()}\n\n"
                f"Save this for your next planning session.\n\n{' '.join(hashtags[:5])}"
            )
        else:
            caption = (
                f"{hooks[0]} ✨\n\n{quote[:190].strip()}\n\n"
                f"Save this for later + follow for more.\n\n{' '.join(hashtags[:5])}"
            )
        caption = _scrub(caption.strip(), banned)
        return {
            "caption": caption[:2200],
            "hooks": hooks,
            "hashtags": [_scrub(tag, banned) for tag in hashtags],
            "cta": _scrub("Save this and share it with someone building the same thing.", banned),
        }

    def _summary(self, context: dict[str, Any]) -> dict[str, Any]:
        segments = context.get("segments") or []
        texts = [str(segment.get("text", "")).strip() for segment in segments if segment.get("text")]
        if not texts:
            return {"tldr": "", "bullets": [], "chapters": [], "quotes": []}
        full = " ".join(texts)
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", full) if sentence.strip()]
        tldr_words = " ".join(sentences[:3]).split()[:55]
        tldr = " ".join(tldr_words).rstrip(".,;") + "."
        bullets = []
        for sentence in sentences:
            if len(sentence) < 35:
                continue
            bullet = sentence[:220].rstrip(".,;")
            if bullet and bullet not in bullets:
                bullets.append(bullet)
            if len(bullets) >= 7:
                break
        if not bullets:
            bullets = [texts[0][:240]]
        chapter_count = min(6, max(2, len(texts) // 4))
        step = max(1, len(texts) // chapter_count)
        chapters = []
        for index in range(0, len(texts), step):
            segment = segments[min(index, len(segments) - 1)]
            chapter_text = " ".join(texts[index : index + step])
            chapter_keywords = _keywords(chapter_text, 3)
            chapters.append(
                {
                    "start": float(segment.get("start", 0)),
                    "title": " ".join(word.title() for word in chapter_keywords) or "Key idea",
                    "summary": chapter_text[:240],
                }
            )
            if len(chapters) >= chapter_count:
                break
        quotes = []
        for segment, text in zip(segments, texts, strict=False):
            if 35 <= len(text) <= 260 and ("?" in text or "!" in text or len(quotes) < 3):
                quotes.append({"start": float(segment.get("start", 0)), "text": text})
            if len(quotes) >= 4:
                break
        if not quotes:
            quotes = [{"start": float(segments[0].get("start", 0)), "text": texts[0][:260]}]
        return {
            "tldr": tldr[:400],
            "bullets": bullets,
            "chapters": chapters,
            "quotes": quotes,
        }

    def _insights(self, context: dict[str, Any]) -> dict[str, Any]:
        clips = context.get("clips") or []
        metrics = context.get("metrics") or {}
        wpm = float(metrics.get("wpm") or 145)
        pause_ratio = float(metrics.get("pause_ratio") or 0.18)
        filler_rate = float(metrics.get("filler_rate") or 0.02)
        pace_score = int(max(45, min(95, 100 - abs(wpm - 155) * 0.55)))
        clarity = int(max(48, min(96, 95 - filler_rate * 800 - pause_ratio * 50)))
        results = []
        for index, clip in enumerate(clips):
            score = float(clip.get("score") or 75)
            hook = int(max(50, min(97, score + 4)))
            pacing = max(42, min(96, pace_score + (index % 3) * 2 - 2))
            local_clarity = max(45, min(97, clarity + (index % 2) * 3))
            peaks = int(max(40, min(95, score - 3 + (index % 4) * 2)))
            predicted = "high" if hook >= 82 and score >= 80 else "medium" if hook >= 65 else "low"
            results.append(
                {
                    "clip_index": index,
                    "scores": {
                        "hook_strength": hook,
                        "pacing": pacing,
                        "clarity": local_clarity,
                        "emotional_peaks": peaks,
                    },
                    "predicted_performance": predicted,
                    "reasoning": (
                        "The preview opens with a specific claim, keeps a steady explanation, "
                        "and resolves the thought inside the clip. Prediction is an estimate, "
                        "not a guarantee."
                    ),
                    "improvements": [
                        "Cut the slow lead-in by 0.4–0.8s so the first word lands immediately.",
                        "Punch up the on-screen hook with the concrete number from the clip.",
                        "Add a mid-clip pattern break (zoom or caption emphasis) at the key turn.",
                    ],
                }
            )
        overall = {
            "hook_strength": int(sum(item["scores"]["hook_strength"] for item in results) / max(1, len(results))),
            "pacing": pace_score,
            "clarity": clarity,
            "emotional_peaks": int(sum(item["scores"]["emotional_peaks"] for item in results) / max(1, len(results))),
        }
        return {
            "headline": "Strong raw material with clear, reusable ideas",
            "summary": (
                "The source has a conversational pace, distinct teaching moments, and enough "
                "specific language to support short-form. The best clips lead with a claim, "
                "show one concrete example, then land on a useful takeaway. Scores are modeled "
                "estimates based on transcript rhythm and structure."
            ),
            "overall": overall,
            "predicted_performance": "high" if overall["hook_strength"] >= 80 else "medium",
            "confidence": "medium",
            "improvements": [
                "Record a 3-second cold open for the highest-potential clip instead of starting mid-sentence.",
                "Reduce filler phrases at the start of each answer to raise perceived clarity.",
                "Test two hook variants per platform instead of changing the whole caption.",
            ],
            "clips": results,
        }
