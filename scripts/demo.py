"""Run the bundled ClipMind demo end to end.

Examples:
    python scripts/demo.py
    python scripts/demo.py --brand "Systems Studio" --n-clips 2
    python scripts/demo.py --no-wait --json

The API server must already be running. In mock mode the run costs $0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx
from clipmind_api import (
    DEFAULT_API_URL,
    DEFAULT_PLATFORMS,
    DEFAULT_WEB_URL,
    ApiFailure,
    attach_brand,
    create_demo_project,
    get_project,
    health,
    list_brands,
    make_client,
    progress_line,
    project_url,
    start_process,
    usage,
    wait_for_job,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and process the ClipMind demo recording.")
    parser.add_argument("--api-url", default=os.getenv("CLIPMIND_API_URL", DEFAULT_API_URL))
    parser.add_argument("--web-url", default=os.getenv("CLIPMIND_WEB_URL", DEFAULT_WEB_URL))
    parser.add_argument("--brand", help="Attach an existing brand profile by name.")
    parser.add_argument("--n-clips", type=int, default=3)
    parser.add_argument(
        "--platforms",
        default=",".join(DEFAULT_PLATFORMS),
        help="Comma-separated platform list (instagram,youtube,tiktok,linkedin,x).",
    )
    parser.add_argument("--min-clip-s", type=int, default=12)
    parser.add_argument("--max-clip-s", type=int, default=35)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--no-wait", action="store_true", help="Create the project and job, then exit.")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable result.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    platforms = [item.strip().lower() for item in args.platforms.split(",") if item.strip()]
    result: dict[str, Any] = {}

    try:
        with make_client(args.api_url) as client:
            info = health(client)
            if not args.json:
                print(
                    f"ClipMind {info['version']} | provider={info['provider']} "
                    f"| mock={info['mock_mode']} | budget=${info['max_budget_usd']:.2f}"
                )

            brand = None
            if args.brand:
                brand = next(
                    (item for item in list_brands(client) if item["name"].casefold() == args.brand.casefold()),
                    None,
                )
                if not brand:
                    raise ApiFailure(f"Brand profile not found: {args.brand}")

            project = create_demo_project(client, brand["id"] if brand else None)
            if brand and not project.get("brand_profile_id"):
                project = attach_brand(client, project["id"], brand["id"])

            job = start_process(
                client,
                project["id"],
                n_clips=args.n_clips,
                platforms=platforms,
                min_clip_s=args.min_clip_s,
                max_clip_s=args.max_clip_s,
                brand_profile_id=brand["id"] if brand else None,
            )
            if not args.json:
                print(f"Project {project['id']} created; job {job['id']} queued.")
                print(f"Open {project_url(args.web_url, project['id'])}\n")

            if args.no_wait:
                result = {
                    "project_id": project["id"],
                    "project_url": project_url(args.web_url, project["id"]),
                    "job_id": job["id"],
                    "status": job["status"],
                }
            else:
                last_stage = ""
                last_progress = -1

                def on_update(update: dict[str, Any]) -> None:
                    nonlocal last_stage, last_progress
                    stage = str(update.get("stage") or "")
                    progress = int(float(update.get("progress") or 0))
                    if stage != last_stage or progress >= last_progress + 5 or update["status"] != "running":
                        print(progress_line(update))
                        last_stage = stage
                        last_progress = progress

                job = wait_for_job(client, job["id"], timeout=args.timeout, on_update=on_update)
                project = get_project(client, project["id"])
                spend = usage(client)
                clips = project.get("clips") or []
                rendered = [clip for clip in clips if clip.get("status") == "rendered"]
                result = {
                    "project_id": project["id"],
                    "project_url": project_url(args.web_url, project["id"]),
                    "job_id": job["id"],
                    "status": job["status"],
                    "clips": len(clips),
                    "rendered": len(rendered),
                    "platforms": sorted({v["platform"] for clip in clips for v in clip.get("copy_variants", [])}),
                    "cost_usd": spend["total_cost_usd"],
                    "error": job.get("error"),
                }
                if not args.json:
                    print()
                    print(f"Status: {job['status']} | clips: {len(clips)} | rendered: {len(rendered)}")
                    print(f"Model spend: ${spend['total_cost_usd']:.4f} | calls: {spend['calls']}")
                    for index, clip in enumerate(clips, start=1):
                        print(
                            f"  {index}. {clip['title']} "
                            f"({clip['end'] - clip['start']:.1f}s, {clip['status']})"
                        )
                    print(f"\nOpen the studio: {result['project_url']}")
                if job["status"] != "completed":
                    print(f"Job failed: {job.get('error')}", file=sys.stderr)
                    return 1
    except (ApiFailure, httpx.HTTPError) as exc:
        print(f"Demo failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
