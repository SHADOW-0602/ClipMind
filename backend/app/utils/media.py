from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MediaError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise MediaError(
            "FFmpeg/ffprobe not found on PATH. Install FFmpeg and restart ClipMind. "
            "See README.md for platform instructions."
        )


def run_ffmpeg(args: list[str], *, cwd: Path | None = None, timeout: int = 600) -> None:
    require_ffmpeg()
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    logger.debug("ffmpeg command: %s", " ".join(command))
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-3000:]
        raise MediaError(f"FFmpeg failed: {detail or 'unknown error'}")


def probe_media(path: Path) -> dict[str, Any]:
    require_ffmpeg()
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        shell=False,
    )
    if proc.returncode != 0:
        raise MediaError(f"ffprobe failed: {(proc.stderr or '').strip()[-1000:]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError("ffprobe returned invalid JSON") from exc


def media_metadata(path: Path) -> dict[str, float | int]:
    data = probe_media(path)
    streams = data.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    duration = float(data.get("format", {}).get("duration") or 0)
    if duration <= 0 and video:
        duration = float(video.get("duration") or 0)
    fps = 0.0
    if video and video.get("avg_frame_rate"):
        numerator, _, denominator = str(video["avg_frame_rate"]).partition("/")
        try:
            fps = float(numerator) / max(1.0, float(denominator or 1))
        except (ValueError, ZeroDivisionError):
            fps = 0.0
    return {
        "duration_s": round(duration, 3),
        "width": int(video.get("width") or 0) if video else 0,
        "height": int(video.get("height") or 0) if video else 0,
        "fps": round(fps, 3),
        "has_video": bool(video),
        "has_audio": bool(audio),
    }


def normalize_video(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            "scale='min(1920,iw)':-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(destination),
        ],
        timeout=1800,
    )


def normalize_audio(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i",
            str(source),
            "-vn",
            "-ac",
            "2",
            "-ar",
            "44100",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(destination),
        ],
        timeout=900,
    )


def extract_audio(source: Path, destination: Path, *, sample_rate: int = 16000) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        timeout=1800,
    )


def extract_keyframes(source: Path, output_dir: Path, duration: float, *, max_frames: int = 8) -> list[dict]:
    """Sample up to max_frames scene-ish frames, capped at one per 10 seconds.

    The plan allows PySceneDetect as an optional enhancement. A regular sample is
    deterministic, fast, and keeps visual tokens/costs low. See DECISIONS.md.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    if duration <= 0:
        return []
    count = max(1, min(max_frames, int(duration // 10) or 1))
    interval = max(10.0, duration / count)
    frames: list[dict] = []
    for index in range(count):
        timestamp = min(max(0.0, index * interval + interval / 2), max(0.0, duration - 0.2))
        target = output_dir / f"frame-{index:02d}.jpg"
        try:
            run_ffmpeg(
                [
                    "-ss",
                    f"{timestamp:.3f}",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale='min(768,iw)':-2",
                    "-q:v",
                    "4",
                    str(target),
                ],
                timeout=120,
            )
            if target.exists() and target.stat().st_size > 0:
                frames.append({"timestamp": round(timestamp, 3), "path": target.name})
        except MediaError as exc:
            logger.warning("Skipping keyframe at %.1fs: %s", timestamp, exc)
    return frames


def create_placeholder_video(destination: Path, duration: float, title: str = "ClipMind") -> None:
    """Build a branded visual bed for text/audio-only projects."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    safe_title = title.replace(":", " -").replace("'", "")[:80]
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x101218:s=1080x1920:d={max(1.0, duration):.3f}:r=30",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=stereo:sample_rate=44100:d={max(1.0, duration):.3f}",
            "-shortest",
            "-vf",
            (
                "drawbox=x=78:y=1700:w=924:h=5:color=0xd7ff63@0.9:t=fill,"
                "drawtext=text='CLIPMIND':x=80:y=150:fontsize=40:fontcolor=0xd7ff63,"
                f"drawtext=text='{safe_title}':x=80:y=230:fontsize=66:fontcolor=white:"
                "line_spacing=14,"
                "drawtext=text='TEXT EDITION':x=80:y=1760:fontsize=28:fontcolor=white@0.65"
            ),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            str(destination),
        ],
        timeout=900,
    )
