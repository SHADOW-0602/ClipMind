from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..config import get_settings
from ..db import get_session
from ..models import AsrCall, InsightReport, ModelCall, Project
from ..schemas import InsightRead, UsageRead
from ..services.costs import usage_totals

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/projects/{project_id}/insights", response_model=InsightRead)
def get_insights(project_id: str, session: Session = Depends(get_session)) -> InsightRead:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    report = session.exec(select(InsightReport).where(InsightReport.project_id == project_id)).first()
    if not report:
        raise HTTPException(status_code=404, detail="Insights are not ready yet")
    return InsightRead(report=report.report_json)


@router.get("/usage", response_model=UsageRead)
def get_usage() -> UsageRead:
    return UsageRead(**usage_totals())


@router.get("/usage/calls")
def get_usage_calls(limit: int = 50, session: Session = Depends(get_session)) -> list[dict]:
    limit = max(1, min(limit, 200))
    settings = get_settings()
    calls = session.exec(
        select(ModelCall).order_by(ModelCall.created_at.desc()).limit(limit)
    ).all()
    asr_calls = session.exec(
        select(AsrCall).order_by(AsrCall.created_at.desc()).limit(limit)
    ).all()
    rows = [
        {
            "id": call.id,
            "kind": "model",
            "job_id": call.job_id,
            "provider": call.provider,
            "model": call.model,
            "purpose": call.purpose,
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "cached_tokens": call.cached_tokens,
            "audio_seconds": 0.0,
            "cost_usd": call.cost_usd,
            "latency_ms": call.latency_ms,
            "cache_hit": call.cache_hit,
            "created_at": call.created_at.isoformat(),
        }
        for call in calls
    ]
    rows.extend(
        {
            "id": call.id,
            "kind": "asr",
            "job_id": call.job_id,
            "provider": (
                "meta"
                if call.model == settings.meta_asr_model
                else settings.provider
                if call.model == settings.llm_asr_model
                else "whisper"
            ),
            "model": call.model,
            "purpose": "transcribe",
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "audio_seconds": call.audio_seconds,
            "cost_usd": call.cost_usd,
            "latency_ms": call.latency_ms,
            "cache_hit": False,
            "created_at": call.created_at.isoformat(),
        }
        for call in asr_calls
    )
    rows.sort(key=lambda row: row["created_at"], reverse=True)
    return rows[:limit]
