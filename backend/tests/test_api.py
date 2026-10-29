from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

from app.services.storage import resolve_inside_data
from app.utils.media import probe_media

SAMPLE_TEXT = """
Most creators do not have a content problem. They have a system problem. You already have more ideas than you can use, more recordings than you can edit, and more drafts than you can publish. The bottleneck is not inspiration. The bottleneck is the distance between something you know and something the internet can actually watch.
Start with capture. Most people record when they feel inspired, which means they record less often than they think. A better rule is to create one source of truth every week. That hour can contain a story, a disagreement, a framework, and a confession. Those are the raw materials. The goal of capture is not polish. The goal is volume of thought in one place.
Here is the part that took me years to learn. The best clip is not the best sentence. It is the moment a belief changes. A useful clip starts with tension, then earns a small shift. Maybe the shift is from working harder to working on the right constraint. If a moment does not contain a before and an after, it is probably context, not content.
So when you distill, ask three questions. First, what is the claim? Second, what is the concrete example or number? Third, what is the sentence someone would repeat at dinner? If you cannot answer all three, keep looking. Stop starting clips with warm-up words. Start on the idea.
Distribution is not copy-paste. On LinkedIn, people want a professional argument they can share with their team. On TikTok, they want a fast, human demonstration. On YouTube Shorts, they want a complete little lesson. The clip can stay the same. The framing should not.
Hooks are where most good clips die. A hook is not a summary. A hook is a promise with a little bit of danger in it. You do not need clickbait. You need specificity. The more precisely you describe the problem, the less you have to exaggerate the solution.
Track leading indicators instead of views. Did people stay past the first three seconds? Did they save the clip? Did they send it to someone? Then change one variable at a time. Change the hook, not the hook and the edit and the platform and the posting time. Otherwise you learn nothing and call it bad luck.
You are not behind. You are disorganized. The creators you admire have a shorter path from idea to published asset. That path is a system, and systems can be built. Start with one source of truth. Pick one weekly recording slot. Choose one metric that reflects whether the idea landed. Then let the clips compound.
"""


def create_project(client, name: str, brand_profile_id: str | None = None) -> dict:
    response = client.post(
        "/api/projects",
        json={"name": name, "brand_profile_id": brand_profile_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload_text(client, project_id: str, text: str = SAMPLE_TEXT) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/upload",
        data={"text": text, "rights_attested": "true", "kind_hint": "text"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def wait_for_job(client, job_id: str, timeout: float = 420.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in {"completed", "failed", "cancelled"}:
            return last
        time.sleep(0.4)
    raise AssertionError(f"Job timed out; last state: {last}")


def test_health_and_brand_crud(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["provider"] == "openai_compatible"
    assert body["asr_provider"] == "whisper"

    created = client.post(
        "/api/brand-profiles",
        json={
            "name": "Systems Studio",
            "tone_description": "Direct, warm, practical",
            "voice_dos": ["Be specific"],
            "voice_donts": ["Hype"],
            "banned_words": ["revolutionary"],
            "target_audience": "Independent creators",
        },
    )
    assert created.status_code == 201, created.text
    brand_id = created.json()["id"]

    updated = client.patch(
        f"/api/brand-profiles/{brand_id}",
        json={"tone_description": "Calm and concrete"},
    )
    assert updated.status_code == 200
    assert updated.json()["tone_description"] == "Calm and concrete"

    listed = client.get("/api/brand-profiles")
    assert listed.status_code == 200
    assert any(item["id"] == brand_id for item in listed.json())


def test_full_pipeline_from_text(client):
    brand = client.post(
        "/api/brand-profiles",
        json={"name": "Pipeline Brand", "banned_words": ["revolutionary", "guaranteed"]},
    ).json()
    project = create_project(client, "Pipeline Acceptance", brand["id"])
    asset = upload_text(client, project["id"])
    assert asset["kind"] == "text"
    assert asset["media_url"]

    started = client.post(
        f"/api/projects/{project['id']}/process",
        json={
            "n_clips": 2,
            "platforms": ["instagram", "linkedin"],
            "min_clip_s": 15,
            "max_clip_s": 45,
            "brand_profile_id": brand["id"],
        },
    )
    assert started.status_code == 200, started.text
    job = wait_for_job(client, started.json()["id"])
    assert job["status"] == "completed", job
    assert job["progress"] == 100
    assert job["stages_json"]
    assert all(stage["status"] == "complete" for stage in job["stages_json"]), job["stages_json"]

    project_response = client.get(f"/api/projects/{project['id']}")
    assert project_response.status_code == 200
    project_data = project_response.json()
    assert project_data["status"] == "completed"
    assert project_data["latest_job"]["status"] == "completed"
    assert len(project_data["clips"]) >= 1

    for clip in project_data["clips"]:
        assert 15 <= clip["end"] - clip["start"] <= 45.5
        assert clip["status"] == "rendered", clip
        assert clip["media_url"] and clip["srt_url"] and clip["thumbnail_url"]
        assert len(clip["copy_variants"]) == 2
        for variant in clip["copy_variants"]:
            assert variant["caption"]
            assert len(variant["hooks"]) == 3
            assert "revolutionary" not in variant["caption"].lower()
        render_info = probe_media(Path(resolve_inside_data(clip["render_path"])))
        video = next(stream for stream in render_info["streams"] if stream["codec_type"] == "video")
        assert (video["width"], video["height"]) == (1080, 1920)

    summary = client.get(f"/api/projects/{project['id']}/summary")
    assert summary.status_code == 200, summary.text
    summary_body = summary.json()
    assert summary_body["tldr"]
    assert len(summary_body["bullets"]) >= 5
    assert summary_body["chapters"]
    assert len(summary_body["quotes"]) >= 3

    insights = client.get(f"/api/projects/{project['id']}/insights")
    assert insights.status_code == 200, insights.text
    report = insights.json()["report"]
    assert report["metrics"]["wpm"] > 0
    assert len(report["clips"]) == len(project_data["clips"])
    assert report["methodology"]

    transcript = client.get(f"/api/projects/{project['id']}/transcript")
    assert transcript.status_code == 200
    assert transcript.json()["segments_json"]
    assert transcript.json()["provider"] == "text"

    usage = client.get("/api/usage")
    assert usage.status_code == 200
    assert usage.json()["calls"] > 0
    assert usage.json()["total_cost_usd"] == 0.0

    events = client.get(f"/api/jobs/{job['id']}/events")
    assert events.status_code == 200
    assert "job_complete" in events.text

    export = client.get(f"/api/projects/{project['id']}/export")
    assert export.status_code == 200, export.text
    with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
        names = archive.namelist()
        assert "summary.md" in names
        assert "copy.csv" in names
        assert "insights.json" in names
        assert any(name.startswith("clips/") for name in names)
        assert any(name.startswith("captions/") for name in names)

    first_clip = project_data["clips"][0]
    banned_edit = client.patch(
        f"/api/clips/{first_clip['id']}",
        json={
            "variants": [
                {
                    "platform": "instagram",
                    "caption": "This revolutionary system changes everything.",
                    "hooks": [],
                    "hashtags": ["#Test"],
                    "cta": "Try it",
                }
            ]
        },
    )
    assert banned_edit.status_code == 422
    assert "revolutionary" in banned_edit.json()["detail"].lower()

    regenerated = client.post(
        f"/api/clips/{first_clip['id']}/regenerate",
        json={"kind": "copy", "platform": "x", "feedback": "Make it sharper"},
    )
    assert regenerated.status_code == 200, regenerated.text
    assert any(variant["platform"] == "x" for variant in regenerated.json()["copy_variants"])

    deleted = client.delete(f"/api/projects/{project['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_demo_project_and_sanitized_system_info(client):
    system = client.get("/api/system")
    assert system.status_code == 200
    body = system.json()
    assert body["provider"] == "openai_compatible"
    assert body["asr_provider"] == "whisper"
    assert body["provider_base_url"] == "http://testserver/v1"
    assert "api_key" not in {key.lower() for key in body}
    assert "model_api_key" not in body

    demo = client.post("/api/demo-project", json={})
    assert demo.status_code == 201, demo.text
    project = demo.json()
    assert project["assets"]
    asset = project["assets"][0]
    assert asset["kind"] == "video"
    assert asset["original_filename"] == "demo-short.mp4"
    assert asset["media_url"]
    assert asset["duration_s"] > 60

    cleaned = client.delete(f"/api/projects/{project['id']}")
    assert cleaned.status_code == 200
