from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import BrandProfile, Clip, MediaAsset, Project, Summary, Transcript
from ..schemas import (
    BrandProfileRead,
    ClipRead,
    ProjectCreate,
    ProjectListItem,
    ProjectRead,
    ProjectUpdate,
    SummaryRead,
    TranscriptRead,
)
from .serializers import clip_read, project_list_item, project_read

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, session: Session = Depends(get_session)) -> ProjectRead:
    if payload.brand_profile_id and not session.get(BrandProfile, payload.brand_profile_id):
        raise HTTPException(status_code=400, detail="Brand profile not found")
    project = Project(name=payload.name.strip(), brand_profile_id=payload.brand_profile_id)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project_read(session, project)


@router.get("", response_model=list[ProjectListItem])
def list_projects(session: Session = Depends(get_session)) -> list[ProjectListItem]:
    projects = session.exec(select(Project).order_by(Project.updated_at.desc())).all()
    return [project_list_item(session, project) for project in projects]


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, session: Session = Depends(get_session)) -> ProjectRead:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project_read(session, project)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str, payload: ProjectUpdate, session: Session = Depends(get_session)
) -> ProjectRead:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if "name" in payload.model_fields_set and payload.name:
        project.name = payload.name.strip()
    if "brand_profile_id" in payload.model_fields_set:
        if payload.brand_profile_id and not session.get(BrandProfile, payload.brand_profile_id):
            raise HTTPException(status_code=400, detail="Brand profile not found")
        project.brand_profile_id = payload.brand_profile_id
    project.updated_at = datetime.now(UTC)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project_read(session, project)


@router.get("/{project_id}/transcript", response_model=TranscriptRead)
def get_transcript(project_id: str, session: Session = Depends(get_session)) -> TranscriptRead:
    asset = session.exec(
        select(MediaAsset).where(MediaAsset.project_id == project_id).order_by(MediaAsset.created_at.desc())
    ).first()
    if not asset:
        raise HTTPException(status_code=404, detail="No media for this project")
    transcript = session.exec(select(Transcript).where(Transcript.asset_id == asset.id)).first()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript is not ready yet")
    return TranscriptRead(
        id=transcript.id,
        asset_id=transcript.asset_id,
        language=transcript.language,
        text=transcript.text,
        segments_json=transcript.segments_json,
        provider=transcript.provider,
    )


@router.get("/{project_id}/summary", response_model=SummaryRead)
def get_summary(project_id: str, session: Session = Depends(get_session)) -> SummaryRead:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    summary = session.exec(select(Summary).where(Summary.project_id == project_id)).first()
    if not summary:
        raise HTTPException(status_code=404, detail="Summary is not ready yet")
    return SummaryRead(
        tldr=summary.tldr,
        bullets=summary.bullets_json,
        chapters=summary.chapters_json,
        quotes=summary.quotes_json,
    )


@router.get("/{project_id}/clips", response_model=list[ClipRead])
def get_clips(project_id: str, session: Session = Depends(get_session)) -> list[ClipRead]:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    clips = session.exec(
        select(Clip).where(Clip.project_id == project_id).order_by(Clip.start)
    ).all()
    return [clip_read(session, clip) for clip in clips]


@router.get("/{project_id}/brand", response_model=BrandProfileRead | None)
def get_project_brand(project_id: str, session: Session = Depends(get_session)) -> BrandProfileRead | None:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.brand_profile_id:
        return None
    brand = session.get(BrandProfile, project.brand_profile_id)
    return BrandProfileRead.model_validate(brand) if brand else None
