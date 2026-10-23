from __future__ import annotations

import asyncio
import copy
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session, delete, select

from ..db import get_engine, get_session
from ..models import (
    AsrCall,
    BrandProfile,
    Clip,
    CopyVariant,
    InsightReport,
    Job,
    MediaAsset,
    ModelCall,
    Project,
    Summary,
    TopicSegment,
    Transcript,
)
from ..pipeline.orchestrator import active_job_for_project, initial_stages, job_service
from ..schemas import JobRead, ProcessRequest
from ..services.storage import delete_project_files
from .serializers import job_read

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
project_router = APIRouter(prefix="/api/projects", tags=["jobs"])


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, session: Session = Depends(get_session)) -> JobRead:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_read(job)


@router.get("/{job_id}/events")
async def job_events(
    job_id: str,
    request: Request,
    last_event_id: int = 0,
) -> StreamingResponse:
    header_id = request.headers.get("last-event-id")
    if header_id and not last_event_id:
        try:
            last_event_id = int(header_id)
        except ValueError:
            last_event_id = 0

    async def stream():
        cursor = last_event_id
        heartbeat_at = time.monotonic()
        deadline = time.monotonic() + 60 * 60
        while time.monotonic() < deadline:
            if await request.is_disconnected():
                return
            with Session(get_engine()) as session:
                job = session.get(Job, job_id)
                if not job:
                    payload = {"type": "error", "message": "Job not found"}
                    yield f"event: error\ndata: {json.dumps(payload)}\n\n"
                    return
                events = list(job.events_json or [])
                status = job.status
                error = job.error
                progress = job.progress
            sent = False
            for event in events:
                seq = int(event.get("seq", 0))
                if seq <= cursor:
                    continue
                cursor = seq
                sent = True
                yield (
                    f"id: {seq}\nevent: {event.get('type', 'update')}\n"
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                )
            if status in {"completed", "failed", "cancelled"}:
                final = {
                    "type": "stream_end",
                    "status": status,
                    "progress": progress,
                    "error": error,
                }
                yield f"event: stream_end\ndata: {json.dumps(final, ensure_ascii=False)}\n\n"
                return
            if not sent and time.monotonic() - heartbeat_at > 12:
                heartbeat_at = time.monotonic()
                yield f": heartbeat {int(time.time())}\n\n"
            await asyncio.sleep(0.65)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{job_id}/retry", response_model=JobRead)
async def retry_job(job_id: str, session: Session = Depends(get_session)) -> JobRead:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Job is already active")
    job.status = "queued"
    job.error = None
    job.progress = 0
    job.events_json = []
    stages = copy.deepcopy(job.stages_json or initial_stages())
    for item in stages:
        if item.get("status") != "complete":
            item["status"] = "pending"
            item["progress"] = 0
            item["message"] = "Queued for retry"
    job.stages_json = stages
    session.add(job)
    session.commit()
    await job_service.enqueue(job.id)
    session.refresh(job)
    return job_read(job)


@project_router.post("/{project_id}/process", response_model=JobRead)
async def start_process(
    project_id: str,
    payload: ProcessRequest,
    session: Session = Depends(get_session),
) -> JobRead:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    asset = session.exec(
        select(MediaAsset).where(MediaAsset.project_id == project_id).order_by(MediaAsset.created_at.desc())
    ).first()
    if not asset:
        raise HTTPException(status_code=400, detail="Upload a video, audio file, or text first")
    active = active_job_for_project(project_id)
    if active:
        raise HTTPException(
            status_code=409,
            detail=f"A job is already active for this project (job {active.id})",
        )
    if payload.brand_profile_id:
        brand = session.get(BrandProfile, payload.brand_profile_id)
        if not brand:
            raise HTTPException(status_code=400, detail="Brand profile not found")
        project.brand_profile_id = payload.brand_profile_id
    options = payload.model_dump()
    options["asset_id"] = asset.id
    job = Job(
        project_id=project_id,
        status="queued",
        stage="queued",
        progress=0,
        options_json=options,
        stages_json=initial_stages(),
        events_json=[
            {
                "seq": 1,
                "type": "queued",
                "stage": "queued",
                "message": "Queued for processing",
                "progress": 0,
                "ts": time.time(),
            }
        ],
    )
    project.status = "queued"
    project.error = None
    session.add(job)
    session.add(project)
    session.commit()
    session.refresh(job)
    try:
        await job_service.enqueue(job.id)
    except RuntimeError as exc:
        job.status = "failed"
        job.error = "Job service is not running"
        session.add(job)
        session.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return job_read(job)


@project_router.delete("/{project_id}")
def delete_project(project_id: str, session: Session = Depends(get_session)) -> dict:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    active = active_job_for_project(project_id)
    if active:
        raise HTTPException(status_code=409, detail="Wait for the active job before deleting this project")
    clips = session.exec(select(Clip).where(Clip.project_id == project_id)).all()
    for clip in clips:
        session.exec(delete(CopyVariant).where(CopyVariant.clip_id == clip.id))
    session.exec(delete(Clip).where(Clip.project_id == project_id))
    session.exec(delete(Summary).where(Summary.project_id == project_id))
    session.exec(delete(InsightReport).where(InsightReport.project_id == project_id))
    assets = session.exec(select(MediaAsset).where(MediaAsset.project_id == project_id)).all()
    for asset in assets:
        session.exec(delete(TopicSegment).where(TopicSegment.asset_id == asset.id))
        session.exec(delete(Transcript).where(Transcript.asset_id == asset.id))
    session.exec(delete(MediaAsset).where(MediaAsset.project_id == project_id))
    jobs = session.exec(select(Job).where(Job.project_id == project_id)).all()
    for job in jobs:
        session.exec(delete(ModelCall).where(ModelCall.job_id == job.id))
        session.exec(delete(AsrCall).where(AsrCall.job_id == job.id))
    session.exec(delete(Job).where(Job.project_id == project_id))
    session.delete(project)
    session.commit()
    delete_project_files(project_id)
    return {"deleted": True, "project_id": project_id}
