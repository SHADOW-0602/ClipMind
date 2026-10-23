from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def brand_block(brand: dict | None) -> str:
    if not brand:
        return "No brand profile selected. Use a confident, warm, clear creator voice."
    return "\n".join(
        [
            f"Brand name: {brand.get('name', '')}",
            f"Tone: {brand.get('tone_description', '')}",
            f"Target audience: {brand.get('target_audience', '')}",
            f"Always: {'; '.join(brand.get('voice_dos', [])) or 'be specific and useful'}",
            f"Never: {'; '.join(brand.get('voice_donts', [])) or 'use hype without evidence'}",
            f"Banned words (must not appear): {', '.join(brand.get('banned_words', [])) or 'none'}",
            "Example posts:\n" + ("\n".join(f"- {post}" for post in brand.get("example_posts", [])) or "- none"),
        ]
    )
