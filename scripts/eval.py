"""Evaluate a ClipMind project against the product's hard requirements.

The eval creates (or reuses) a demo project, waits for the pipeline, then checks
transcript grounding, clip boundaries, platform copy, brand safety, summary,
insights, renders, export contents, and cost accounting.

Examples:
    python scripts/eval.py
    python scripts/eval.py --project-id <id>
    python scripts/eval.py --json --json-out data/evals/latest.json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from clipmind_api import (
    DEFAULT_API_URL,
    DEFAULT_PLATFORMS,
    ApiFailure,
    attach_brand,
    create_demo_project,
    ensure_brand,
    get_project,
    health,
    make_client,
    progress_line,
    start_process,
    usage,
    wait_for_job,
)

PLATFORM_LIMITS = {
    "instagram": 2200,
    "youtube": 5000,
    "tiktok": 2200,
    "linkedin": 3000,
    "x": 280,
}

EVAL_BRAND = {
    "name": "Systems Studio",
    "tone_description": "Direct, warm, practical. Name the constraint before the solution. No hype.",
    "target_audience": "Independent creators and small content teams",
    "voice_dos": ["Lead with a concrete observation", "Name the tradeoff"],
    "voice_donts": ["No fake urgency", "No engagement bait"],
    "banned_words": ["revolutionary", "guaranteed", "hack", "guru"],
    "example_posts": ["Most creators do not have a content problem. They have a system problem."],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ClipMind acceptance evals.")
    parser.add_argument("--api-url", default=os.getenv("CLIPMIND_API_URL", DEFAULT_API_URL))
    parser.add_argument("--project-id", help="Evaluate an existing project instead of running a demo.")
    parser.add_argument("--brand", default=EVAL_BRAND["name"])
    parser.add_argument("--n-clips", type=int, default=3)
    parser.add_argument("--platforms", default=",".join(DEFAULT_PLATFORMS))
    parser.add_argument("--min-clip-s", type=int, default=12)
    parser.add_argument("--max-clip-s", type=int, default=35)
    parser.add_argument("--expect-clips", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--json", action="store_true", help="Print only the JSON report.")
    parser.add_argument(
        "--json-out",
        default="data/evals/latest.json",
        help="Where to write the JSON report (relative to the repository root).",
    )
    return parser.parse_args()


def normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def grounded(quote: str, source: str) -> bool:
    needle = normalize(quote)
    return bool(needle) and needle in normalize(source)


def banned_hits(texts: list[str], banned: list[str]) -> list[str]:
    joined = "\n".join(texts)
    return [
        word
        for word in banned
        if word and re.search(rf"(?<!\w){re.escape(word)}(?!\w)", joined, re.IGNORECASE)
    ]


def ffprobe_dimensions(url: str) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        stream = json.loads(result.stdout)["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except (KeyError, IndexError, ValueError, json.JSONDecodeError):
        return None


class Report:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "passed": bool(ok), "detail": detail})

    @property
    def passed(self) -> int:
        return sum(1 for check in self.checks if check["passed"])

    @property
    def failed(self) -> int:
        return len(self.checks) - self.passed

    def print(self) -> None:
        width = max((len(check["name"]) for check in self.checks), default=10)
        for check in self.checks:
            marker = "PASS" if check["passed"] else "FAIL"
            print(f"[{marker}] {check['name']:<{width}}  {check['detail']}")
        print(f"\n{self.passed}/{len(self.checks)} checks passed, {self.failed} failed")


def evaluate(client: httpx.Client, project_id: str, args: argparse.Namespace, report: Report) -> dict[str, Any]:
    project = get_project(client, project_id)
    clips = project.get("clips") or []
    assets = project.get("assets") or []
    duration = max((float(asset.get("duration_s") or 0) for asset in assets), default=0.0)
    brand = project.get("brand_profile")
    banned = brand.get("banned_words", []) if brand else []

    report.check("project.completed", project.get("status") == "completed", project.get("status", ""))
    report.check("project.has_asset", bool(assets), f"{len(assets)} asset(s)")
    report.check(
        "project.clip_count",
        len(clips) >= args.expect_clips,
        f"{len(clips)} clip(s), expected >= {args.expect_clips}",
    )

    try:
        transcript = client.get(f"/api/projects/{project_id}/transcript")
        transcript.raise_for_status()
        transcript_data = transcript.json()
    except httpx.HTTPError as exc:
        transcript_data = {}
        report.check("transcript.available", False, str(exc))

    segments = transcript_data.get("segments_json") or []
    source_text = transcript_data.get("text") or ""
    words = [
        word
        for segment in segments
        for word in (segment.get("words") or [])
        if isinstance(word, dict)
    ]
    report.check("transcript.segments", bool(segments), f"{len(segments)} segment(s)")
    report.check("transcript.words", bool(words), f"{len(words)} word timing(s)")
    report.check(
        "transcript.word_timing",
        all(
            isinstance(word.get("start"), (int, float))
            and isinstance(word.get("end"), (int, float))
            and word["end"] >= word["start"] >= 0
            for word in words
        ),
        "start/end present and ordered",
    )
    report.check(
        "transcript.provider",
        bool(transcript_data.get("provider")),
        str(transcript_data.get("provider", "")),
    )

    previous_end = -1.0
    for index, clip in enumerate(clips, start=1):
        start = float(clip.get("start") or 0)
        end = float(clip.get("end") or 0)
        clip_duration = end - start
        prefix = f"clip.{index}"
        report.check(
            f"{prefix}.bounds",
            0 <= start < end <= duration + 0.5,
            f"{start:.2f}s -> {end:.2f}s (source {duration:.2f}s)",
        )
        report.check(
            f"{prefix}.duration",
            args.min_clip_s - 0.5 <= clip_duration <= args.max_clip_s + 0.5,
            f"{clip_duration:.2f}s (target {args.min_clip_s}-{args.max_clip_s}s)",
        )
        report.check(
            f"{prefix}.non_overlap",
            start >= previous_end - 0.01,
            f"starts at {start:.2f}s, previous ended at {previous_end:.2f}s" if previous_end >= 0 else "first clip",
        )
        previous_end = max(previous_end, end)
        report.check(
            f"{prefix}.quote_grounded",
            grounded(clip.get("source_quote", ""), source_text),
            (clip.get("source_quote") or "")[:90],
        )
        report.check(
            f"{prefix}.title_hook",
            bool((clip.get("title") or "").strip()) and bool((clip.get("hook") or "").strip()),
            clip.get("title", ""),
        )

        variants = clip.get("copy_variants") or []
        by_platform = {variant.get("platform"): variant for variant in variants}
        requested = {item.strip().lower() for item in args.platforms.split(",") if item.strip()}
        report.check(
            f"{prefix}.platforms",
            requested.issubset(by_platform),
            f"{sorted(by_platform)}",
        )
        for platform in requested:
            variant = by_platform.get(platform)
            if not variant:
                continue
            caption = variant.get("caption") or ""
            limit = PLATFORM_LIMITS.get(platform, 5000)
            report.check(
                f"{prefix}.{platform}.caption_limit",
                len(caption) <= limit,
                f"{len(caption)}/{limit} characters",
            )
            report.check(
                f"{prefix}.{platform}.hooks",
                bool(variant.get("hooks")),
                f"{len(variant.get('hooks') or [])} hook(s)",
            )
            texts = [
                clip.get("title", ""),
                clip.get("hook", ""),
                caption,
                variant.get("cta", ""),
                *[str(tag) for tag in variant.get("hashtags") or []],
                *[str(hook) for hook in variant.get("hooks") or []],
            ]
            hits = banned_hits(texts, banned)
            report.check(
                f"{prefix}.{platform}.brand_safe",
                not hits,
                f"banned hits: {', '.join(hits)}" if hits else "no banned words",
            )

        report.check(
            f"{prefix}.rendered",
            clip.get("status") == "rendered" and bool(clip.get("media_url")),
            f"status={clip.get('status')}",
        )
        report.check(
            f"{prefix}.captions",
            bool(clip.get("srt_url")),
            clip.get("srt_url") or "missing",
        )
        if clip.get("srt_url"):
            try:
                srt = client.get(clip["srt_url"])
                srt.raise_for_status()
                report.check(
                    f"{prefix}.srt_content",
                    "-->" in srt.text and bool(srt.text.strip()),
                    f"{len(srt.text)} characters",
                )
            except httpx.HTTPError as exc:
                report.check(f"{prefix}.srt_content", False, str(exc))
        if clip.get("media_url"):
            dimensions = ffprobe_dimensions(clip["media_url"])
            if dimensions is None:
                report.check(f"{prefix}.vertical_render", False, "ffprobe could not read the render")
            else:
                report.check(
                    f"{prefix}.vertical_render",
                    dimensions == (1080, 1920),
                    f"{dimensions[0]}x{dimensions[1]}",
                )

    try:
        summary_response = client.get(f"/api/projects/{project_id}/summary")
        summary_response.raise_for_status()
        summary = summary_response.json()
    except httpx.HTTPError as exc:
        summary = {}
        report.check("summary.available", False, str(exc))

    report.check("summary.tldr", bool((summary.get("tldr") or "").strip()), (summary.get("tldr") or "")[:90])
    report.check(
        "summary.bullets",
        len(summary.get("bullets") or []) >= 3,
        f"{len(summary.get('bullets') or [])} bullet(s)",
    )
    chapters = summary.get("chapters") or []
    report.check("summary.chapters", bool(chapters), f"{len(chapters)} chapter(s)")
    chapter_starts = [float(chapter.get("start") or 0) for chapter in chapters]
    report.check(
        "summary.chapter_order",
        chapter_starts == sorted(chapter_starts)
        and all(0 <= value <= duration + 0.5 for value in chapter_starts),
        f"starts: {chapter_starts[:6]}",
    )
    quotes = summary.get("quotes") or []
    report.check("summary.quotes", bool(quotes), f"{len(quotes)} quote(s)")
    report.check(
        "summary.quotes_grounded",
        bool(quotes) and all(grounded(str(quote.get("text", "")), source_text) for quote in quotes),
        "every summary quote appears in the transcript",
    )

    try:
        insights_response = client.get(f"/api/projects/{project_id}/insights")
        insights_response.raise_for_status()
        report_data = insights_response.json().get("report") or {}
    except httpx.HTTPError as exc:
        report_data = {}
        report.check("insights.available", False, str(exc))

    metrics = report_data.get("metrics") or {}
    report.check("insights.metrics", float(metrics.get("wpm") or 0) > 0, f"wpm={metrics.get('wpm')}")
    report.check(
        "insights.clip_coverage",
        len(report_data.get("clips") or []) == len(clips),
        f"{len(report_data.get('clips') or [])}/{len(clips)} clips scored",
    )
    report.check(
        "insights.methodology",
        bool((report_data.get("methodology") or "").strip()),
        (report_data.get("methodology") or "")[:90],
    )
    score_rows = report_data.get("clips") or []
    report.check(
        "insights.score_bounds",
        all(
            0 <= float(score or 0) <= 100
            for row in score_rows
            for score in (row.get("scores") or {}).values()
        ),
        f"{len(score_rows)} scorecard(s)",
    )

    try:
        export = client.get(f"/api/projects/{project_id}/export")
        export.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
            names = set(archive.namelist())
            manifest = json.loads(archive.read("manifest.json")) if "manifest.json" in names else {}
        required = {"summary.md", "copy.csv", "insights.json", "manifest.json"}
        report.check("export.required_files", required.issubset(names), f"{sorted(required - names)} missing")
        report.check(
            "export.media",
            any(name.startswith("clips/") and name.endswith(".mp4") for name in names)
            and any(name.startswith("captions/") and name.endswith(".srt") for name in names),
            f"{sum(name.startswith('clips/') for name in names)} clip(s)",
        )
        report.check(
            "export.manifest",
            int(manifest.get("clip_count") or 0) == len(clips),
            f"manifest clip_count={manifest.get('clip_count')}",
        )
    except (httpx.HTTPError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        report.check("export.available", False, str(exc))

    spend = usage(client)
    report.check("usage.calls", spend["calls"] > 0, f"{spend['calls']} call(s)")
    report.check(
        "usage.budget",
        spend["total_cost_usd"] <= spend["budget_usd"] and spend["remaining_usd"] >= 0,
        f"${spend['total_cost_usd']:.4f} of ${spend['budget_usd']:.2f}",
    )
    provider = health(client)["provider"]
    report.check(
        "usage.mock_zero_cost",
        provider != "mock" or spend["total_cost_usd"] == 0,
        f"provider={provider}, cost=${spend['total_cost_usd']:.4f}",
    )

    return {
        "project_id": project_id,
        "project_name": project.get("name"),
        "provider": provider,
        "clips": len(clips),
        "duration_s": duration,
        "cost_usd": spend["total_cost_usd"],
        "brand_profile": brand.get("name") if brand else None,
    }


def main() -> int:
    args = parse_args()
    platforms = [item.strip().lower() for item in args.platforms.split(",") if item.strip()]
    report = Report()
    summary: dict[str, Any] = {}

    try:
        with make_client(args.api_url) as client:
            info = health(client)
            if not args.json:
                print(f"ClipMind eval | {args.api_url} | provider={info['provider']} | mock={info['mock_mode']}")

            if args.project_id:
                project_id = args.project_id
            else:
                brand, _ = ensure_brand(client, {**EVAL_BRAND, "name": args.brand})
                project = create_demo_project(client, brand["id"])
                project = attach_brand(client, project["id"], brand["id"])
                job = start_process(
                    client,
                    project["id"],
                    n_clips=args.n_clips,
                    platforms=platforms,
                    min_clip_s=args.min_clip_s,
                    max_clip_s=args.max_clip_s,
                    brand_profile_id=brand["id"],
                )
                project_id = project["id"]
                if not args.json:
                    print(f"Project {project_id} | job {job['id']}")
                last_stage = ""

                def on_update(update: dict[str, Any]) -> None:
                    nonlocal last_stage
                    if update.get("stage") != last_stage or update["status"] != "running":
                        if not args.json:
                            print("  " + progress_line(update))
                        last_stage = str(update.get("stage"))

                job = wait_for_job(client, job["id"], timeout=args.timeout, on_update=on_update)
                if job["status"] != "completed":
                    report.check("pipeline.completed", False, job.get("error") or job["status"])
                    summary = {"project_id": project_id, "job": job}
                else:
                    report.check("pipeline.completed", True, f"job {job['id']}")

            if not args.json:
                print()
            summary = {**summary, **evaluate(client, project_id, args, report)}
    except (ApiFailure, httpx.HTTPError) as exc:
        report.check("eval.connected", False, str(exc))
        summary = {"error": str(exc)}

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "api_url": args.api_url,
        "summary": summary,
        "passed": report.passed,
        "failed": report.failed,
        "checks": report.checks,
    }
    out_path = Path(args.json_out)
    if not out_path.is_absolute():
        out_path = Path(__file__).resolve().parents[1] / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        report.print()
        print(f"Report written to {out_path}")
        if summary.get("project_id"):
            print(f"Project: {summary['project_id']} | cost: ${summary.get('cost_usd', 0):.4f}")

    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
