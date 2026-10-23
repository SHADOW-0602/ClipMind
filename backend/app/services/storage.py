from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..config import get_settings

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(filename: str, fallback: str = "upload") -> str:
    name = Path(filename or fallback).name
    name = SAFE_NAME.sub("-", name).strip(".-")
    return name[:140] or fallback


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def project_dir(kind: str, project_id: str) -> Path:
    allowed = {"uploads", "processed", "renders"}
    if kind not in allowed:
        raise ValueError(f"Unknown storage bucket: {kind}")
    path = get_settings().data_dir / kind / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def relative_path(path: Path) -> str:
    settings = get_settings()
    try:
        return path.resolve().relative_to(settings.data_dir.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def resolve_path(stored: str | None) -> Path | None:
    if not stored:
        return None
    path = Path(stored)
    if not path.is_absolute():
        path = get_settings().data_dir / path
    return path.resolve()


def resolve_inside_data(stored: str | None) -> Path | None:
    path = resolve_path(stored)
    if path is None:
        return None
    data_dir = get_settings().data_dir.resolve()
    try:
        path.relative_to(data_dir)
    except ValueError as exc:
        raise ValueError("Invalid media path") from exc
    return path


def public_media_url(relative: str | None, route: str = "/media") -> str | None:
    if not relative:
        return None
    return f"{get_settings().public_api_url.rstrip('/')}{route}/{relative.lstrip('/')}"


def delete_project_files(project_id: str) -> None:
    settings = get_settings()
    for root in (settings.uploads_dir, settings.processed_dir, settings.renders_dir):
        target = (root / project_id).resolve()
        if root.resolve() in target.parents and target.exists():
            import shutil

            shutil.rmtree(target, ignore_errors=True)
