from __future__ import annotations

from app.services.transcripts import (
    build_segments_from_text,
    build_srt,
    dedupe_intervals,
    flatten_words,
    quote_is_grounded,
    snap_to_words,
    srt_timestamp,
    synthesize_words,
)


def test_synthesize_words_covers_interval():
    words = synthesize_words("one two three", 1.0, 4.0)
    assert [word["word"] for word in words] == ["one", "two", "three"]
    assert words[0]["start"] == 1.0
    assert words[-1]["end"] == 4.0
    assert all(word["end"] > word["start"] for word in words)


def test_build_segments_from_text_has_word_timings():
    text = "First idea lands. Second idea lands too. Third closes the loop."
    segments = build_segments_from_text(text, duration=30)
    assert len(segments) == 3
    assert segments[0]["start"] == 0
    assert segments[-1]["end"] == 30
    assert len(flatten_words(segments)) == len(text.split())


def test_srt_timestamp_and_build_srt():
    assert srt_timestamp(3661.5) == "01:01:01,500"
    segments = [
        {
            "start": 10.0,
            "end": 14.0,
            "text": "This is a caption with enough length.",
            "words": synthesize_words("This is a caption with enough length.", 10.0, 14.0),
        }
    ]
    srt = build_srt(segments, clip_start=10.0, clip_end=20.0)
    assert "00:00:00,000 --> 00:00:04,000" in srt
    assert "This is a caption" in srt


def test_quote_grounding_accepts_light_cleanup_and_rejects_invention():
    source = "The real bottleneck is the distance between knowing and shipping."
    assert quote_is_grounded("The real bottleneck is the distance between knowing and shipping", source)
    assert quote_is_grounded("real bottleneck is the distance between knowing and shipping", source)
    assert not quote_is_grounded("The real bottleneck is a lack of inspiration", source)


def test_snap_to_words_respects_bounds():
    words = [
        {"start": 0.0, "end": 0.4, "word": "Start"},
        {"start": 1.0, "end": 1.4, "word": "here"},
        {"start": 20.0, "end": 20.4, "word": "end"},
    ]
    start, end = snap_to_words(0.8, 20.4, words, min_s=5, max_s=15, duration=30)
    assert start == 1.0
    assert 5 <= end - start <= 15


def test_dedupe_intervals_drops_overlaps():
    kept = dedupe_intervals([(0, 20), (15, 35), (40, 60)], min_gap=1)
    assert kept == [(0.0, 20.0), (40.0, 60.0)]
