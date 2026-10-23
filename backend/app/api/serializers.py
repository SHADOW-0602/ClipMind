from __future__ import annotations

from sqlmodel import Session, select

from ..models import BrandProfile, Clip, CopyVariant, Job, MediaAsset, Project
from ..schemas import (
    BrandProfileRead,
    ClipRead,
    CopyVariantRead,
    JobRead,
    MediaAssetRead,
    ProjectListItem,
    ProjectRead,
)
from ..services.storage import public_media_url


def copy_variant_read(variant: CopyVariant) -> CopyVariantRead:
    return CopyVariantRead.model_validate(variant)


def clip_read(session: Session, clip: Clip) -> ClipRead:
    variants = session.exec(
        select(CopyVariant).where(CopyVariant.clip_id == clip.id).order_by(CopyVariant.created_at)
    ).all()
    data = ClipRead.model_validate(clip, from_attributes=True)
    data.copy_variants = [copy_variant_read(variant) for variant in variants]
    data.media_url = public_media_url(clip.render_path, "/api/media")
    data.thumbnail_url = public_media_url(clip.thumbnail_path, "/api/media")
    data.srt_url = public_media_url(clip.srt_path, "/api/media")
    return data


def asset_read(asset: MediaAsset) -> MediaAssetRead:
    data = MediaAssetRead.model_validate(asset, from_attributes=True)
    data.media_url = public_media_url(asset.normalized_path or asset.path, "/api/media")
    data.audio_url = public_media_url(asset.audio_path, "/api/media")
    raw_frames = asset.frames_json or []
    data.frames = [
        {
            **frame,
            "url": public_media_url(frame.get("path"), "/api/media"),
        }
        for frame in raw_frames
    ]
    return data


def job_read(job: Job) -> JobRead:
    return JobRead.model_validate(job, from_attributes=True)


def project_read(session: Session, project: Project) -> ProjectRead:
    assets = session.exec(
        select(MediaAsset).where(MediaAsset.project_id == project.id).order_by(MediaAsset.created_at.desc())
    ).all()
    clips = session.exec(
        select(Clip).where(Clip.project_id == project.id).order_by(Clip.start)
    ).all()
    latest_job = session.exec(
        select(Job).where(Job.project_id == project.id).order_by(Job.created_at.desc())
    ).first()
    brand = session.get(BrandProfile, project.brand_profile_id) if project.brand_profile_id else None
    data = ProjectRead.model_validate(project, from_attributes=True)
    data.assets = [asset_read(asset) for asset in assets]
    data.clips = [clip_read(session, clip) for clip in clips]
    data.latest_job = job_read(latest_job) if latest_job else None
    data.brand_profile = BrandProfileRead.model_validate(brand) if brand else None
    return data


def project_list_item(session: Session, project: Project) -> ProjectListItem:
    assets = session.exec(select(MediaAsset).where(MediaAsset.project_id == project.id)).all()
    clips = session.exec(select(Clip).where(Clip.project_id == project.id)).all()
    thumb = next((clip.thumbnail_path for clip in clips if clip.thumbnail_path), None)
    return ProjectListItem(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        updated_at=project.updated_at,
        status=project.status,
        brand_profile_id=project.brand_profile_id,
        duration_s=max((asset.duration_s for asset in assets), default=0.0),
        clip_count=len(clips),
        thumbnail_url=public_media_url(thumb, "/api/media"),
    )
