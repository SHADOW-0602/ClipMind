"""Small shared HTTP client helpers for the ClipMind demo and eval scripts.

The scripts intentionally talk to the public API rather than importing the
FastAPI application. That keeps them useful against a local server, Docker
Compose, or a deployed instance.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_WEB_URL = "http://localhost:3000"
DEFAULT_PLATFORMS = ["instagram", "tiktok", "linkedin"]


class ApiFailure(RuntimeError):
    """Raised when the ClipMind API returns an error or a script times out."""


def make_client(base_url: str = DEFAULT_API_URL, timeout: float = 180.0) -> httpx.Client:
    return httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(timeout, connect=10.0),
        follow_redirects=True,
    )


def _json(response: httpx.Response, label: str) -> Any:
    if response.status_code >= 400:
        raise ApiFailure(f"{label} failed ({response.status_code}): {response.text[:1000]}")
    if not response.content:
        return None
    return response.json()


def health(client: httpx.Client) -> dict[str, Any]:
    return _json(client.get("/api/health"), "health check")


def list_projects(client: httpx.Client) -> list[dict[str, Any]]:
    return _json(client.get("/api/projects"), "list projects")


def get_project(client: httpx.Client, project_id: str) -> dict[str, Any]:
    return _json(client.get(f"/api/projects/{project_id}"), "get project")


def list_brands(client: httpx.Client) -> list[dict[str, Any]]:
    return _json(client.get("/api/brand-profiles"), "list brand profiles")


def ensure_brand(client: httpx.Client, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Create a brand profile, or update the existing profile with the same name."""
    existing = next(
        (brand for brand in list_brands(client) if brand["name"].casefold() == payload["name"].casefold()),
        None,
    )
    if existing:
        updated = _json(
            client.patch(f"/api/brand-profiles/{existing['id']}", json=payload),
            f"update brand {payload['name']}",
        )
        return updated, "updated"
    created = _json(client.post("/api/brand-profiles", json=payload), f"create brand {payload['name']}")
    return created, "created"


def create_demo_project(
    client: httpx.Client, brand_profile_id: str | None = None
) -> dict[str, Any]:
    return _json(
        client.post("/api/demo-project", json={"brand_profile_id": brand_profile_id}),
        "create demo project",
    )


def attach_brand(client: httpx.Client, project_id: str, brand_profile_id: str) -> dict[str, Any]:
    return _json(
        client.patch(
            f"/api/projects/{project_id}",
            json={"brand_profile_id": brand_profile_id},
        ),
        "attach brand profile",
    )


def start_process(
    client: httpx.Client,
    project_id: str,
    *,
    n_clips: int = 3,
    platforms: list[str] | None = None,
    min_clip_s: int = 12,
    max_clip_s: int = 35,
    brand_profile_id: str | None = None,
    regenerate: bool = False,
) -> dict[str, Any]:
    payload = {
        "n_clips": n_clips,
        "platforms": platforms or DEFAULT_PLATFORMS,
        "min_clip_s": min_clip_s,
        "max_clip_s": max_clip_s,
        "brand_profile_id": brand_profile_id,
        "regenerate": regenerate,
    }
    return _json(client.post(f"/api/projects/{project_id}/process", json=payload), "start pipeline")


def get_job(client: httpx.Client, job_id: str) -> dict[str, Any]:
    return _json(client.get(f"/api/jobs/{job_id}"), "get job")


def wait_for_job(
    client: httpx.Client,
    job_id: str,
    *,
    timeout: float = 600.0,
    poll: float = 2.0,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = get_job(client, job_id)
        if on_update:
            on_update(last)
        if last["status"] in {"completed", "failed", "cancelled"}:
            return last
        time.sleep(poll)
    raise ApiFailure(
        f"Job {job_id} did not finish within {timeout:.0f}s "
        f"(last status: {last.get('status') if last else 'unknown'})"
    )


def wait_for_project_job(
    client: httpx.Client,
    project_id: str,
    *,
    timeout: float = 600.0,
    poll: float = 2.0,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Poll a project until its latest job reaches a terminal state."""
    deadline = time.monotonic() + timeout
    last_job: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        project = get_project(client, project_id)
        last_job = project.get("latest_job")
        if last_job:
            if on_update:
                on_update(last_job)
            if last_job["status"] in {"completed", "failed", "cancelled"}:
                return project, last_job
        time.sleep(poll)
    raise ApiFailure(
        f"Project {project_id} did not finish within {timeout:.0f}s "
        f"(last status: {last_job.get('status') if last_job else 'no job'})"
    )


def usage(client: httpx.Client) -> dict[str, Any]:
    return _json(client.get("/api/usage"), "usage")


def project_url(web_url: str, project_id: str) -> str:
    return f"{web_url.rstrip('/')}/projects/{project_id}"


def progress_line(job: dict[str, Any]) -> str:
    stage = job.get("stage") or job.get("status")
    return f"{job.get('progress', 0):5.1f}%  {stage:<14}  {job.get('status')}"
