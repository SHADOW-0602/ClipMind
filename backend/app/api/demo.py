from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..models import BrandProfile, Project
from ..pipeline.ingest import register_asset
from ..schemas import ProjectRead
from ..services.storage import project_dir
from .serializers import project_read

router = APIRouter(prefix="/api", tags=["demo"])

# Locally this is <repo>/backend; in the container it is /app. Both hold samples/.
BACKEND_DIR = Path(__file__).resolve().parents[2]
DEMO_NAME = "The Creator Operating System"


class DemoProjectRequest(BaseModel):
    brand_profile_id: str | None = None


@router.post("/demo-project", response_model=ProjectRead, status_code=201)
def create_demo_project(
    payload: DemoProjectRequest | None = None,
    session: Session = Depends(get_session),
) -> ProjectRead:
    """Create a project from the bundled, transcript-grounded demo recording.

    The short sample has a known transcript manifest, so the demo can show real
    word-level captions without spending ASR time on the sample audio.
    """
    sample = BACKEND_DIR / "samples" / "demo-short.mp4"
    if not sample.exists():
        raise HTTPException(
            status_code=404,
            detail="Demo media is not generated. Run python scripts/generate_samples.py.",
        )
    brand_id = payload.brand_profile_id if payload else None
    if brand_id and not session.get(BrandProfile, brand_id):
        raise HTTPException(status_code=400, detail="Brand profile not found")

    stamp = datetime.now(UTC).strftime("%b %d, %H:%M")
    project = Project(name=f"{DEMO_NAME} · {stamp}", brand_profile_id=brand_id, status="draft")
    session.add(project)
    session.commit()
    session.refresh(project)

    destination = project_dir("uploads", project.id) / "demo-short.mp4"
    shutil.copy2(sample, destination)
    register_asset(
        session,
        project_id=project.id,
        path=destination,
        original_filename="demo-short.mp4",
        kind_hint="video",
    )
    project = session.get(Project, project.id)
    assert project is not None
    return project_read(session, project)
