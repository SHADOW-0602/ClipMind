from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import brand, clips, demo, export, insights, jobs, media, projects, uploads
from .config import get_settings
from .db import init_db
from .pipeline.orchestrator import job_service
from .providers import close_provider, get_provider
from .utils.media import require_ffmpeg

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_dirs()
    init_db()
    try:
        require_ffmpeg()
        logger.info("FFmpeg is available")
    except Exception as exc:  # noqa: BLE001
        logger.warning("FFmpeg check failed: %s", exc)
    try:
        get_provider()
    except Exception as exc:  # noqa: BLE001 - fail fast on a missing/invalid provider key
        logger.error("Provider configuration is invalid: %s", exc)
        raise
    await job_service.start()
    logger.info(
        "ClipMind ready — provider=%s model=%s asr=%s",
        settings.provider,
        settings.active_model,
        settings.effective_asr_provider,
    )
    try:
        yield
    finally:
        await job_service.stop()
        await close_provider()
        logger.info("ClipMind stopped")


app = FastAPI(
    title="ClipMind API",
    description=(
        "Multimodal content intelligence: long-form media to captioned vertical clips, "
        "platform copy, summaries, and engagement insights."
    ),
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

_rate_windows: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    if request.method in {"POST", "PATCH", "DELETE"}:
        client = request.client.host if request.client else "anonymous"
        now = time.monotonic()
        window = _rate_windows[client]
        while window and now - window[0] > 60:
            window.popleft()
        limit = settings.rate_limit_per_minute
        if len(window) >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit reached ({limit} writes/min). Try again shortly."},
                headers={"Retry-After": "30"},
            )
        window.append(now)
        if len(_rate_windows) > 5000:
            _rate_windows.clear()
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


app.include_router(projects.router)
app.include_router(demo.router)
app.include_router(uploads.router)
app.include_router(jobs.router)
app.include_router(jobs.project_router)
app.include_router(brand.router)
app.include_router(clips.router)
app.include_router(insights.router)
app.include_router(export.router)
app.include_router(media.router)


@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "provider": settings.provider,
        "model": settings.active_model,
        "asr_provider": settings.effective_asr_provider,
        "asr_model": settings.active_asr_model,
        "max_budget_usd": settings.max_budget_usd,
    }


@app.get("/api/system", tags=["system"])
def system_info() -> dict:
    """Sanitized runtime configuration for the settings screen. Never returns secrets."""
    return {
        "version": settings.app_version,
        "environment": settings.environment,
        "provider": settings.provider,
        "provider_base_url": settings.provider_base_url,
        "model": settings.active_model,
        "asr_provider": settings.effective_asr_provider,
        "asr_model": settings.active_asr_model,
        "force_whisper": settings.force_whisper,
        "max_budget_usd": settings.max_budget_usd,
        "hackathon_credits_usd": settings.hackathon_credits_usd,
        "input_price_per_m": settings.active_input_price_per_m,
        "cached_input_price_per_m": settings.active_cached_input_price_per_m,
        "output_price_per_m": settings.active_output_price_per_m,
        "asr_usd_per_hour": settings.active_asr_usd_per_hour,
        "max_upload_mb": settings.max_upload_mb,
        "max_duration_s": settings.max_duration_s,
        "min_clip_s": settings.min_clip_s,
        "max_clip_s": settings.max_clip_s,
        "job_concurrency": settings.job_concurrency,
        "auto_resume_jobs": settings.auto_resume_jobs,
        "public_api_url": settings.public_api_url,
        "data_dir": str(settings.data_dir),
        "cors_origins": settings.cors_origins,
    }


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"name": "ClipMind API", "docs": "/docs", "health": "/health"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
