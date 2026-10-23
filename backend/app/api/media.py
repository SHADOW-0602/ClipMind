from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..services.storage import resolve_inside_data

router = APIRouter(prefix="/api/media", tags=["media"])

ALLOWED_SUFFIXES = {
    ".mp4", ".m4a", ".wav", ".mp3", ".aac", ".webm", ".mov",
    ".jpg", ".jpeg", ".png", ".webp", ".srt", ".vtt",
}
CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".aac": "audio/aac",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".srt": "text/plain; charset=utf-8",
    ".vtt": "text/vtt; charset=utf-8",
}


@router.get("/{stored_path:path}")
def serve_media(stored_path: str) -> FileResponse:
    try:
        path = resolve_inside_data(stored_path)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid media path") from exc
    if not path or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Media not found")
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=403, detail="File type is not served")
    # Prevent accidental directory traversal through URL normalization.
    if Path(stored_path).is_absolute():
        raise HTTPException(status_code=403, detail="Invalid media path")
    return FileResponse(
        path,
        media_type=CONTENT_TYPES.get(suffix, "application/octet-stream"),
        headers={
            "Cache-Control": "private, max-age=300",
            "Accept-Ranges": "bytes",
        },
        filename=None,
    )
