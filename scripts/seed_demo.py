"""Seed ClipMind with brand profiles and, optionally, a completed demo project.

Examples:
    python scripts/seed_demo.py
    python scripts/seed_demo.py --with-project --wait
    python scripts/seed_demo.py --with-project --wait --force --json

Idempotent: brand profiles are matched by name and updated in place. A demo
project is reused unless --force is passed. The default Groq preset is free.
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
    DEFAULT_WEB_URL,
    ApiFailure,
    attach_brand,
    create_demo_project,
    ensure_brand,
    health,
    list_projects,
    make_client,
    progress_line,
    project_url,
    start_process,
    wait_for_job,
)

DEMO_NAME_PREFIX = "The Creator Operating System"

BRAND_PROFILES: list[dict[str, Any]] = [
    {
        "name": "Systems Studio",
        "tone_description": (
            "Direct, warm, practical. Short sentences. Name the constraint before the solution. "
            "No hype and no vague promises."
        ),
        "target_audience": "Independent creators and small content teams",
        "voice_dos": [
            "Lead with a concrete observation",
            "Use numbers when they are available",
            "Name the tradeoff",
            "End with one useful next step",
        ],
        "voice_donts": [
            "No fake urgency",
            "No engagement bait",
            "No generic inspiration",
        ],
        "banned_words": ["revolutionary", "guaranteed", "hack", "guru"],
        "example_posts": [
            "Most creators do not have a content problem. They have a system problem.",
            "Start with capture. Polish comes later.",
        ],
    },
    {
        "name": "Field Notes",
        "tone_description": (
            "Curious, analytical, and plainspoken. Explain the mechanism, then the implication. "
            "Comfortable saying what is still unknown."
        ),
        "target_audience": "Researchers, product leads, and technical operators",
        "voice_dos": [
            "Separate observation from interpretation",
            "Use a specific example",
            "State the confidence level",
        ],
        "voice_donts": [
            "Do not overclaim",
            "Do not use jargon as shorthand for thinking",
        ],
        "banned_words": ["unprecedented", "silver bullet", "secret sauce"],
        "example_posts": [
            "The interesting part is not the output. It is the feedback loop that produced it.",
        ],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed brand profiles and a demo ClipMind project.")
    parser.add_argument("--api-url", default=os.getenv("CLIPMIND_API_URL", DEFAULT_API_URL))
    parser.add_argument("--web-url", default=os.getenv("CLIPMIND_WEB_URL", DEFAULT_WEB_URL))
    parser.add_argument("--with-project", action="store_true", help="Create a demo project as well.")
    parser.add_argument("--wait", action="store_true", help="Wait for the demo pipeline to finish.")
    parser.add_argument("--force", action="store_true", help="Create a new demo project even if one exists.")
    parser.add_argument("--brand", default="Systems Studio", help="Brand profile to attach to the demo.")
    parser.add_argument("--n-clips", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result: dict[str, Any] = {"brands": [], "project": None}

    try:
        with make_client(args.api_url) as client:
            info = health(client)
            if not args.json:
                print(f"Seeding ClipMind at {args.api_url} (provider={info['provider']})")

            brands: list[dict[str, Any]] = []
            for payload in BRAND_PROFILES:
                brand, action = ensure_brand(client, payload)
                brands.append(brand)
                result["brands"].append({"id": brand["id"], "name": brand["name"], "action": action})
                if not args.json:
                    print(f"  brand {action}: {brand['name']} ({brand['id']})")

            if args.with_project:
                existing = next(
                    (
                        project
                        for project in list_projects(client)
                        if project["name"].startswith(DEMO_NAME_PREFIX)
                        and project.get("status") == "completed"
                        and project.get("clip_count", 0) > 0
                    ),
                    None,
                )
                if existing and not args.force:
                    result["project"] = {
                        "id": existing["id"],
                        "url": project_url(args.web_url, existing["id"]),
                        "status": existing["status"],
                        "reused": True,
                    }
                    if not args.json:
                        print(f"  demo project reused: {existing['name']} ({existing['id']})")
                else:
                    selected = next(
                        (brand for brand in brands if brand["name"].casefold() == args.brand.casefold()),
                        brands[0],
                    )
                    project = create_demo_project(client, selected["id"])
                    project = attach_brand(client, project["id"], selected["id"])
                    job = start_process(
                        client,
                        project["id"],
                        n_clips=args.n_clips,
                        brand_profile_id=selected["id"],
                    )
                    if not args.json:
                        print(f"  demo project created: {project['name']} ({project['id']})")
                        print(f"  pipeline job: {job['id']}")
                    if args.wait:
                        last_stage = ""

                        def on_update(update: dict[str, Any]) -> None:
                            nonlocal last_stage
                            if update.get("stage") != last_stage or update["status"] != "running":
                                if not args.json:
                                    print("    " + progress_line(update))
                                last_stage = str(update.get("stage"))

                        job = wait_for_job(client, job["id"], timeout=args.timeout, on_update=on_update)
                    result["project"] = {
                        "id": project["id"],
                        "url": project_url(args.web_url, project["id"]),
                        "job_id": job["id"],
                        "status": job["status"],
                        "reused": False,
                    }
                    if job["status"] not in {"queued", "running", "completed"}:
                        print(f"  pipeline failed: {job.get('error')}", file=sys.stderr)
                        return 1
    except (ApiFailure, httpx.HTTPError) as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    elif result["project"]:
        print(f"\nOpen: {result['project']['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
