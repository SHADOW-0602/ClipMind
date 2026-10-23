from __future__ import annotations

import asyncio

from app.config import get_settings
from app.providers.mock import MockProvider


def test_mock_provider_returns_structured_copy_and_scrubs_banned_words():
    provider = MockProvider(get_settings())
    system = """
TASK: generate_copy
CONTEXT_JSON:
{"platform":"instagram","clip":{"title":"A revolutionary new system","quote":"This is a revolutionary way to work.","transcript":"This is a revolutionary way to work."},"brand":{"banned_words":["revolutionary"]}}
END_CONTEXT_JSON
"""
    result = asyncio.run(
        provider.generate(
            system=system,
            messages=[],
            response_schema=None,
            cache_key="test:copy",
        )
    )
    assert result.parsed is not None
    assert "revolutionary" not in str(result.parsed).lower()
    assert result.parsed["hooks"]
    assert result.parsed["hashtags"]
    assert result.cost_usd == 0.0


def test_mock_summary_is_grounded_and_has_five_bullets():
    provider = MockProvider(get_settings())
    system = """
TASK: summarize
CONTEXT_JSON:
{"duration_s":60,"segments":[{"start":0,"text":"A concrete idea about building a content system that compounds over time."},{"start":10,"text":"The second idea explains why measurement should focus on saves and replies rather than raw views."},{"start":20,"text":"The third idea gives a weekly cadence for capturing and publishing honest work."}]}
END_CONTEXT_JSON
"""
    result = asyncio.run(provider.generate(system=system, messages=[]))
    parsed = result.parsed
    assert parsed is not None
    assert len(parsed["bullets"]) >= 1
    assert parsed["chapters"]
    assert parsed["quotes"]
    assert "maybe" not in str(parsed)
