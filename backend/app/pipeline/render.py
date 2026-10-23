from __future__ import annotations

import logging
from pathlib import Path

from sqlmodel import Session, select

from ..models import Clip, MediaAsset, Project, Transcript
from ..services.storage import project_dir, relative_path, resolve_path
from ..services.transcripts import build_ass, build_srt
from ..utils.media import MediaError, probe_media, run_ffmpeg

logger = logging.getLogger(__name__)


def _caption_segments(transcript: Transcript, start: float, end: float) -> list[dict]:
    segments: list[dict] = []
    for segment in transcript.segments_json or []:
        words = [
            {
                "start": float(word.get("start", 0)),
                "end": float(word.get("end", 0)),
                "word": str(word.get("word", "")),
            }
            for word in segment.get("words") or []
            if float(word.get("end", 0)) > start and float(word.get("start", 0)) < end
        ]
        if words:
            segments.append(
                {
                    "start": words[0]["start"],
                    "end": words[-1]["end"],
                    "text": " ".join(word["word"] for word in words),
                    "words": words,
                }
            )
    return segments


def build_clip_srt(transcript: Transcript, start: float, end: float) -> str:
    segments = _caption_segments(transcript, start, end)
    return build_srt(segments, clip_start=start, clip_end=end)


def _render_dir(project_id: str) -> Path:
    return project_dir("renders", project_id)


def render_clip(
    session: Session,
    clip: Clip,
    *,
    force: bool = False,
) -> Clip:
    project = session.get(Project, clip.project_id)
    asset = session.get(MediaAsset, clip.asset_id)
    if not project or not asset:
        raise MediaError("Project or media asset not found for render")
    transcript = session.exec(
        select(Transcript).where(Transcript.asset_id == asset.id)
    ).first()
    if not transcript:
        raise MediaError("Transcript missing for captions")
    duration = max(1.0, clip.end - clip.start)
    render_dir = _render_dir(clip.project_id)
    stem = f"clip-{clip.id[:10]}"
    output = render_dir / f"{stem}.mp4"
    srt_path = render_dir / f"{stem}.srt"
    ass_path = render_dir / f"{stem}.ass"
    thumb_path = render_dir / f"{stem}.jpg"
    if output.exists() and srt_path.exists() and ass_path.exists() and clip.render_path and not force:
        return clip

    segments = transcript.segments_json or []
    srt = build_clip_srt(transcript, clip.start, clip.end)
    if not srt.strip():
        srt = "1\n00:00:00,000 --> 00:00:02,000\n[Captions unavailable]\n"
    srt_path.write_text(srt, encoding="utf-8")
    ass = build_ass(segments, clip_start=clip.start, clip_end=clip.end)
    if "Dialogue:" not in ass:
        ass += "Dialogue: 0,0:00:00.00,0:00:02.00,ClipMind,,0,0,0,,[Captions unavailable]\n"
    ass_path.write_text(ass, encoding="utf-8")
    subtitle_filter = f"ass={ass_path.name}"

    source = resolve_path(asset.normalized_path or asset.path)
    if not source or not source.exists():
        raise MediaError("Normalized media is missing")

    if asset.kind == "audio":
        # Audiogram: branded canvas + real waveform + burned-in captions.
        filter_complex = (
            "[1:v]drawbox=x=0:y=0:w=iw:h=ih:color=0x0D0F14:t=fill,"
            "drawbox=x=74:y=1780:w=932:h=4:color=0xD7FF63@0.9:t=fill,"
            f"{subtitle_filter}[bg];"
            "[0:a]showwaves=s=940x250:mode=cline:colors=0xD7FF63:rate=30,"
            "format=yuva420p,colorchannelmixer=aa=0.9[wave];"
            "[bg][wave]overlay=70:1290:shortest=1[v]"
        )
        args = [
            "-ss",
            f"{clip.start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source),
            "-f",
            "lavfi",
            "-i",
            "color=c=0x0D0F14:s=1080x1920:r=30",
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            "-movflags",
            "+faststart",
            output.name,
        ]
    else:
        # Landscape sources get a blurred vertical canvas with the full frame
        # centered, instead of a center crop that slices titles and faces.
        if asset.width > asset.height > 0:
            video_filter = (
                "[0:v]split=2[bg][fg];"
                "[bg]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
                "crop=1080:1920,boxblur=60:3,eq=brightness=-0.24:saturation=0.55,"
                "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.35:t=fill[bg2];"
                "[fg]scale=1080:-2:flags=lanczos[fg2];"
                "[bg2][fg2]overlay=(W-w)/2:(H-h)/2,setsar=1,"
                "drawbox=x=0:y=1540:w=iw:h=380:color=black@0.12:t=fill,"
                f"{subtitle_filter}[v]"
            )
            args = [
                "-ss",
                f"{clip.start:.3f}",
                "-t",
                f"{duration:.3f}",
                "-i",
                str(source),
                "-filter_complex",
                video_filter,
                "-map",
                "[v]",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
            ]
        else:
            video_filter = (
                "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
                "crop=1080:1920,setsar=1,"
                "drawbox=x=0:y=1540:w=iw:h=380:color=black@0.12:t=fill,"
                f"{subtitle_filter}"
            )
            args = [
                "-ss",
                f"{clip.start:.3f}",
                "-t",
                f"{duration:.3f}",
                "-i",
                str(source),
                "-vf",
                video_filter,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
            ]
            args.extend(["-map", "0:v:0", "-map", "0:a:0?"])
        args.extend(
            [
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                output.name,
            ]
        )

    # Run inside the render dir so libass can resolve the relative SRT path on
    # every OS (colon-heavy Windows paths break the subtitles filter otherwise).
    run_ffmpeg(args, cwd=render_dir, timeout=1800)
    if not output.exists() or output.stat().st_size < 1000:
        raise MediaError("Render produced no playable video")

    run_ffmpeg(
        [
            "-ss",
            f"{min(duration * 0.35, duration - 0.2):.3f}",
            "-i",
            output.name,
            "-frames:v",
            "1",
            "-vf",
            "scale=540:960",
            "-q:v",
            "3",
            thumb_path.name,
        ],
        cwd=render_dir,
        timeout=180,
    )
    try:
        info = probe_media(output)
        video = next(stream for stream in info["streams"] if stream.get("codec_type") == "video")
        if int(video.get("width", 0)) != 1080 or int(video.get("height", 0)) != 1920:
            raise MediaError("Rendered clip is not 1080×1920")
    except (StopIteration, MediaError):
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not verify rendered dimensions: %s", exc)

    clip.render_path = relative_path(output)
    clip.srt_path = relative_path(srt_path)
    clip.thumbnail_path = relative_path(thumb_path)
    clip.status = "rendered"
    session.add(clip)
    session.commit()
    session.refresh(clip)
    logger.info("Rendered clip %s -> %s", clip.id, clip.render_path)
    return clip


async def render_project_clips(
    session: Session,
    project_id: str,
    clips: list[Clip],
    *,
    progress=None,
    force: bool = False,
) -> list[Clip]:
    import asyncio

    rendered: list[Clip] = []
    for index, clip in enumerate(clips):
        if progress:
            await progress(index / max(1, len(clips)), f"Rendering clip {index + 1} of {len(clips)}")
        try:
            result = await asyncio.to_thread(render_clip, session, clip, force=force)
            rendered.append(result)
        except Exception as exc:  # noqa: BLE001 - one bad clip must not kill the batch
            logger.exception("Render failed for clip %s: %s", clip.id, exc)
            clip.status = "failed"
            session.add(clip)
            session.commit()
            if progress:
                await progress(
                    (index + 1) / max(1, len(clips)),
                    f"Clip {index + 1} failed; continuing",
                )
    if progress:
        await progress(1.0, f"Rendered {len(rendered)} of {len(clips)} clips")
    if clips and not rendered:
        raise MediaError("Every clip render failed; see server logs for FFmpeg details")
    return rendered
