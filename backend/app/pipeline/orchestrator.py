from __future__ import annotations

import asyncio
import copy
import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from ..config import get_settings
from ..db import get_engine
from ..models import BrandProfile, Clip, Job, MediaAsset, Project, Transcript
from ..services.costs import BudgetExceeded, current_job_id
from .generate_copy import generate_copy_for_clips
from .ingest import find_project_asset, ingest_asset
from .insights import generate_insights
from .render import render_project_clips
from .select_clips import select_clips
from .summarize import summarize_project
from .transcribe import transcribe_asset
from .understand import understand_asset

logger = logging.getLogger(__name__)

STAGES: list[dict[str, Any]] = [
    {"name": "ingest", "label": "Ingest & normalize", "weight": 8},
    {"name": "transcribe", "label": "Transcribe", "weight": 18},
    {"name": "understand", "label": "Understand story", "weight": 16},
    {"name": "select", "label": "Select clips", "weight": 16},
    {"name": "copy", "label": "Write copy & summary", "weight": 16},
    {"name": "render", "label": "Render vertical clips", "weight": 22},
    {"name": "insights", "label": "Build insights", "weight": 4},
]


def initial_stages() -> list[dict[str, Any]]:
    return [
        {
            "name": stage["name"],
            "label": stage["label"],
            "status": "pending",
            "progress": 0,
            "message": "",
        }
        for stage in STAGES
    ]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def append_job_event(
    job: Job,
    event_type: str,
    stage: str,
    message: str,
    progress: float,
    *,
    event_id: int | None = None,
) -> dict[str, Any]:
    events = list(job.events_json or [])
    seq = event_id if event_id is not None else (events[-1]["seq"] + 1 if events else 1)
    event = {
        "seq": seq,
        "type": event_type,
        "stage": stage,
        "message": message,
        "progress": round(progress, 3),
        "ts": time.time(),
    }
    events.append(event)
    job.events_json = events[-250:]
    return event


class PipelineRunner:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.session = Session(get_engine())
        self.settings = get_settings()
        self.job: Job | None = None
        self.project: Project | None = None
        self.asset: MediaAsset | None = None
        self.transcript: Transcript | None = None
        self.clips: list[Clip] = []
        self.token = current_job_id.set(job_id)

    def close(self) -> None:
        current_job_id.reset(self.token)
        self.session.close()

    def _refresh(self) -> None:
        self.job = self.session.get(Job, self.job_id)
        if not self.job:
            raise RuntimeError("Job disappeared")
        self.session.refresh(self.job)

    def _update(
        self,
        *,
        stage: str,
        stage_progress: float,
        message: str = "",
        event_type: str = "progress",
        stage_status: str | None = None,
        overall: bool = True,
    ) -> None:
        self._refresh()
        job = self.job
        assert job is not None
        # Deep-copy before mutating nested stage dicts. A shallow copy shares
        # dicts with SQLAlchemy's committed JSON value, so the unit of work sees
        # no net change and silently skips the UPDATE for stages_json.
        stages = copy.deepcopy(job.stages_json or initial_stages())
        if not stages:
            stages = initial_stages()
        stage_index = next((index for index, item in enumerate(stages) if item["name"] == stage), 0)
        item = stages[stage_index]
        item["progress"] = round(max(0.0, min(1.0, stage_progress)), 3)
        item["message"] = message
        if stage_status:
            item["status"] = stage_status
        if overall:
            weighted_complete = 0.0
            for current in stages:
                weight = next(
                    (definition["weight"] for definition in STAGES if definition["name"] == current["name"]),
                    10,
                )
                if current["status"] == "complete":
                    weighted_complete += weight
                elif current["status"] == "running":
                    weighted_complete += weight * float(current.get("progress", 0))
                elif current["status"] == "failed":
                    weighted_complete += weight * float(current.get("progress", 0))
            progress = weighted_complete / sum(definition["weight"] for definition in STAGES)
            job.progress = round(max(0.0, min(100.0, progress)), 2)
        job.stage = stage
        job.stages_json = stages
        job.updated_at = datetime.now(UTC)
        # Allocate sequence deterministically from existing event list.
        existing = list(job.events_json or [])
        seq = existing[-1]["seq"] + 1 if existing else 1
        append_job_event(
            job,
            event_type,
            stage,
            message,
            job.progress,
            event_id=seq,
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        logger.info(
            "job=%s stage=%s progress=%.1f event=%s %s",
            self.job_id,
            stage,
            job.progress,
            event_type,
            message,
        )

    async def _stage_progress(self, stage: str, fraction: float, message: str) -> None:
        status = "running"
        self._update(
            stage=stage,
            stage_progress=fraction,
            message=message,
            event_type="progress",
            stage_status=status,
        )

    def _complete_stage(self, stage: str, message: str) -> None:
        self._update(
            stage=stage,
            stage_progress=1.0,
            message=message,
            event_type="stage_complete",
            stage_status="complete",
        )

    async def _run_stage(self, stage: str, label: str, operation) -> Any:
        assert self.job
        self._update(
            stage=stage,
            stage_progress=0.0,
            message=f"{label} started",
            event_type="stage_start",
            stage_status="running",
        )

        async def progress(fraction: float, message: str) -> None:
            await self._stage_progress(stage, fraction, message)

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                value = await operation(progress)
                self._complete_stage(stage, f"{label} complete")
                return value
            except BudgetExceeded:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.exception("Stage %s attempt %d failed", stage, attempt + 1)
                if attempt == 0:
                    self._update(
                        stage=stage,
                        stage_progress=max(0.05, self._stage_fraction(stage)),
                        message=f"{label} hiccup, retrying: {exc}",
                        event_type="stage_retry",
                    )
                    await asyncio.sleep(1)
        self._update(
            stage=stage,
            stage_progress=self._stage_fraction(stage),
            message=f"{label} failed: {last_error}",
            event_type="stage_failed",
            stage_status="failed",
        )
        raise RuntimeError(f"{label} failed: {last_error}") from last_error

    def _stage_fraction(self, stage: str) -> float:
        if not self.job:
            return 0.0
        item = next((item for item in self.job.stages_json or [] if item["name"] == stage), None)
        return float(item.get("progress", 0)) if item else 0.0

    async def run(self) -> None:
        assert self.job_id
        self._refresh()
        job = self.job
        assert job is not None
        if not job:
            return
        if job.status == "completed":
            return
        options = dict(job.options_json or {})
        job.status = "running"
        job.started_at = job.started_at or datetime.now(UTC)
        job.error = None
        self.session.add(job)
        self.session.commit()
        self.project = self.session.get(Project, job.project_id)
        if not self.project:
            self._fail("Project not found", "ingest")
            return
        self.project.status = "processing"
        self.project.error = None
        self.session.add(self.project)
        self.session.commit()

        checkpoint = dict(job.checkpoint_json or {})
        completed = set(checkpoint.get("completed_stages") or [])
        stages_json = copy.deepcopy(job.stages_json or initial_stages())
        for item in stages_json:
            if item["name"] in completed:
                item["status"] = "complete"
                item["progress"] = 1
        job.stages_json = stages_json
        self.session.add(job)
        self.session.commit()

        try:
            self.asset = self.session.get(MediaAsset, options.get("asset_id")) if options.get("asset_id") else find_project_asset(self.session, self.project.id)
            if not self.asset:
                raise RuntimeError("No media uploaded to this project")
            brand = (
                self.session.get(BrandProfile, options.get("brand_profile_id"))
                if options.get("brand_profile_id")
                else None
            )
            if self.project.brand_profile_id and brand is None:
                brand = self.session.get(BrandProfile, self.project.brand_profile_id)
            platforms = options.get("platforms") or ["instagram", "youtube", "tiktok", "linkedin", "x"]
            n_clips = int(options.get("n_clips") or 8)
            min_s = int(options.get("min_clip_s") or self.settings.min_clip_s)
            max_s = int(options.get("max_clip_s") or self.settings.max_clip_s)

            async def ingest_op(progress):
                await progress(0.2, "Probing media and checking limits")
                asset = await asyncio.to_thread(ingest_asset, self.session, self.asset.id, force=options.get("regenerate", False))
                await progress(1.0, "Media normalized and keyframes sampled")
                return asset

            if "ingest" not in completed:
                self.asset = await self._run_stage("ingest", "Ingest & normalize", ingest_op)
                self._mark_completed("ingest")
            else:
                self.asset = await asyncio.to_thread(
                    ingest_asset, self.session, self.asset.id, force=False
                )

            async def transcribe_op(progress):
                await progress(0.1, "Loading or generating word-level transcript")
                transcript = await transcribe_asset(
                    self.session, self.asset.id, force=options.get("regenerate", False) and "transcribe" not in completed
                )
                await progress(1.0, f"Transcript ready ({transcript.provider})")
                return transcript

            if "transcribe" not in completed:
                self.transcript = await self._run_stage("transcribe", "Transcribe", transcribe_op)
                self._mark_completed("transcribe")
            else:
                self.transcript = self.session.exec(
                    select(Transcript).where(Transcript.asset_id == self.asset.id)
                ).first()
                if not self.transcript:
                    self.transcript = await transcribe_asset(self.session, self.asset.id)

            if "understand" not in completed:
                await self._run_stage(
                    "understand",
                    "Understand story",
                    lambda progress: understand_asset(
                        self.session,
                        self.project.id,
                        self.asset.id,
                        self.transcript,
                        progress=progress,
                    ),
                )
                self._mark_completed("understand")

            async def select_op(progress):
                clips = await select_clips(
                    self.session,
                    self.project.id,
                    self.asset.id,
                    self.transcript,
                    n_clips=n_clips,
                    min_s=min_s,
                    max_s=max_s,
                    brand=brand,
                    progress=progress,
                    feedback=options.get("feedback", ""),
                )
                return clips

            if "select" not in completed:
                self.clips = await self._run_stage("select", "Select clips", select_op)
                self._mark_completed("select")
            else:
                self.clips = self.session.exec(
                    select(Clip).where(Clip.project_id == self.project.id)
                ).all()
                if not self.clips:
                    self.clips = await select_clips(
                        self.session,
                        self.project.id,
                        self.asset.id,
                        self.transcript,
                        n_clips=n_clips,
                        min_s=min_s,
                        max_s=max_s,
                        brand=brand,
                    )

            async def copy_op(progress):
                await progress(0.05, "Writing platform-native hooks and captions")
                await generate_copy_for_clips(
                    self.session,
                    self.project.id,
                    self.clips,
                    platforms,
                    brand,
                    progress=lambda fraction, message: progress(fraction * 0.72, message),
                )
                await progress(0.76, "Building summary and chapters")
                await summarize_project(
                    self.session,
                    self.project.id,
                    self.asset,
                    self.transcript,
                    progress=lambda fraction, message: progress(0.76 + fraction * 0.24, message),
                )
                return True

            if "copy" not in completed:
                await self._run_stage("copy", "Write copy & summary", copy_op)
                self._mark_completed("copy")

            async def render_op(progress):
                clips = await render_project_clips(
                    self.session,
                    self.project.id,
                    self.clips,
                    progress=progress,
                    force=bool(options.get("regenerate")),
                )
                return clips

            if "render" not in completed:
                rendered = await self._run_stage("render", "Render vertical clips", render_op)
                if rendered:
                    self.clips = rendered
                self._mark_completed("render")
            else:
                self.clips = self.session.exec(
                    select(Clip).where(Clip.project_id == self.project.id)
                ).all()

            async def insights_op(progress):
                report = await generate_insights(
                    self.session,
                    self.project.id,
                    self.asset,
                    self.transcript,
                    self.clips,
                    progress=progress,
                )
                return report

            if "insights" not in completed:
                await self._run_stage("insights", "Build insights", insights_op)
                self._mark_completed("insights")

            self._refresh()
            job = self.job
            assert job is not None
            job.status = "completed"
            job.stage = "completed"
            job.progress = 100.0
            job.completed_at = datetime.now(UTC)
            job.error = None
            stages = copy.deepcopy(job.stages_json or [])
            for item in stages:
                item["status"] = "complete"
                item["progress"] = 1
            job.stages_json = stages
            seq = (job.events_json[-1]["seq"] + 1) if job.events_json else 1
            append_job_event(job, "job_complete", "completed", "Your clip pack is ready", 100.0, event_id=seq)
            self.project = self.session.get(Project, job.project_id)
            if self.project:
                self.project.status = "completed"
                self.project.error = job.error
                self.session.add(self.project)
            self.session.add(job)
            self.session.commit()
            logger.info("Job %s completed", self.job_id)
        except BudgetExceeded as exc:
            self._fail(str(exc), self.job.stage if self.job else "budget")
            logger.error("Budget stop for job %s: %s", self.job_id, exc)
        except Exception as exc:  # noqa: BLE001
            self._fail(str(exc), self.job.stage if self.job else "unknown")
            logger.exception("Job %s failed", self.job_id)
        finally:
            self.close()

    def _mark_completed(self, stage: str) -> None:
        self._refresh()
        job = self.job
        assert job is not None
        checkpoint = dict(job.checkpoint_json or {})
        completed = set(checkpoint.get("completed_stages") or [])
        completed.add(stage)
        checkpoint["completed_stages"] = sorted(completed)
        job.checkpoint_json = checkpoint
        job.stages_json = job.stages_json or initial_stages()
        self.session.add(job)
        self.session.commit()

    def _fail(self, message: str, stage: str) -> None:
        try:
            self._refresh()
            job = self.job
            if not job:
                return
            job.status = "failed"
            job.error = message[:2000]
            job.stage = stage
            job.completed_at = datetime.now(UTC)
            stages = copy.deepcopy(job.stages_json or initial_stages())
            for item in stages:
                if item["name"] == stage:
                    item["status"] = "failed"
                    item["message"] = message[:500]
            job.stages_json = stages
            seq = (job.events_json[-1]["seq"] + 1) if job.events_json else 1
            append_job_event(job, "job_failed", stage, message[:500], job.progress, event_id=seq)
            project = self.session.get(Project, job.project_id)
            if project:
                project.status = "failed"
                project.error = message[:2000]
                self.session.add(project)
            self.session.add(job)
            self.session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Could not persist job failure")


class JobService:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] | None = None
        self.workers: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.queue = asyncio.Queue()
        settings = get_settings()
        for index in range(max(1, settings.job_concurrency)):
            self.workers.append(asyncio.create_task(self._worker(index), name=f"clipmind-worker-{index}"))
        if settings.auto_resume_jobs:
            await self.recover()

    async def stop(self) -> None:
        self._running = False
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers = []
        self.queue = None

    async def recover(self) -> None:
        with Session(get_engine()) as session:
            stale = session.exec(
                select(Job).where(Job.status.in_(["queued", "running", "retrying"]))
            ).all()
        for job in stale:
            with Session(get_engine()) as session:
                fresh = session.get(Job, job.id)
                if fresh:
                    fresh.status = "queued"
                    fresh.stage = fresh.checkpoint_json.get("last_stage", fresh.stage) if fresh.checkpoint_json else fresh.stage
                    self.session_reset_stage(fresh)
                    session.add(fresh)
                    session.commit()
            logger.info("Re-queued interrupted job %s", job.id)
            await self.enqueue(job.id)

    @staticmethod
    def session_reset_stage(job: Job) -> None:
        # A stage that was "running" at the crash is not in completed_stages, so
        # it naturally re-runs. Keep all stage cards but mark them pending.
        stages = copy.deepcopy(job.stages_json or [])
        for item in stages:
            if item.get("status") == "failed":
                item["status"] = "pending"
                item["message"] = "Retrying after restart"
                item["progress"] = 0
        job.stages_json = stages

    async def enqueue(self, job_id: str) -> None:
        if self.queue is None:
            raise RuntimeError("Job service is not running")
        await self.queue.put(job_id)

    async def _worker(self, index: int) -> None:
        assert self.queue is not None
        while True:
            job_id = await self.queue.get()
            try:
                await self.run_job(job_id)
            except Exception:  # noqa: BLE001
                logger.exception("Worker %s crashed on job %s", index, job_id)
            finally:
                self.queue.task_done()

    async def run_job(self, job_id: str) -> None:
        runner = PipelineRunner(job_id)
        await runner.run()


job_service = JobService()


async def run_job_once(job_id: str) -> None:
    runner = PipelineRunner(job_id)
    await runner.run()


def active_job_for_project(project_id: str) -> Job | None:
    with Session(get_engine()) as session:
        return session.exec(
            select(Job)
            .where(Job.project_id == project_id, Job.status.in_(["queued", "running", "retrying"]))
            .order_by(Job.created_at.desc())
        ).first()
