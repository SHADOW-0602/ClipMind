from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.services.storage import resolve_inside_data
from app.utils.media import probe_media

BACKEND = Path(__file__).resolve().parents[1]
SAMPLE = BACKEND / "samples" / "demo-short.mp4"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="demo sample media not generated")


def test_sample_media_pipeline(client):
    project = client.post("/api/projects", json={"name": "Sample Media Acceptance"}).json()
    with SAMPLE.open("rb") as handle:
        uploaded = client.post(
            f"/api/projects/{project['id']}/upload",
            files={"file": (SAMPLE.name, handle, "video/mp4")},
            data={"rights_attested": "true"},
        )
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()
    assert asset["kind"] == "video"
    assert asset["duration_s"] > 30

    started = client.post(
        f"/api/projects/{project['id']}/process",
        json={
            "n_clips": 1,
            "platforms": ["instagram"],
            "min_clip_s": 12,
            "max_clip_s": 35,
        },
    )
    assert started.status_code == 200, started.text
    job_id = started.json()["id"]

    deadline = time.time() + 300
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.4)
    assert job and job["status"] == "completed", job

    project_data = client.get(f"/api/projects/{project['id']}").json()
    assert project_data["clips"]
    clip = project_data["clips"][0]
    assert clip["status"] == "rendered", clip
    info = probe_media(Path(resolve_inside_data(clip["render_path"])))
    video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)

    transcript = client.get(f"/api/projects/{project['id']}/transcript").json()
    assert transcript["provider"] == "sample-ground-truth"
    words = transcript["segments_json"][0].get("words") or []
    assert words and "word" in words[0]
