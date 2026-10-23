"""Generate the offline demo media and word-level transcript manifest.

The generated files are committed so the demo works without network, a model
key, or a text-to-speech engine. Re-run this only when you want to rebuild the
sample set:

    python scripts/generate_samples.py --force

Windows uses the built-in System.Speech voices through scripts/tts_sapi.ps1.
On macOS/Linux, install `espeak-ng` or supply your own audio; the checked-in
samples are enough for normal development and evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "backend" / "samples"
TTS_SCRIPT = ROOT / "scripts" / "tts_sapi.ps1"

LONG_TITLE = "The Creator Operating System"
LONG_LABEL = "LONG-FORM DEMO  /  6 MINUTES"
LONG_SCRIPT = """
Most creators do not have a content problem. They have a system problem. You already have more ideas than you can use, more recordings than you can edit, and more drafts than you can publish. The bottleneck is not inspiration. The bottleneck is the distance between something you know and something the internet can actually watch. Over the next few minutes, I want to show you the operating system I use to close that gap. It has three layers: capture, distill, and distribute. Get those layers working together, and posting stops feeling like a fresh act of willpower every single day.
Let us start with capture. Most people capture randomly. They record when they feel inspired, which means they record less often than they think. A better rule is to create one source of truth every week. For me, that is a single long conversation or a single long recording. I do not try to make ten posts while I am recording. I try to make one hour of honest thinking. That hour can contain a story, a disagreement, a framework, and a confession. Those are the raw materials. The goal of capture is not polish. The goal is volume of thought in one place.
Here is the part that took me years to learn. The best clip is not the best sentence. It is the moment a belief changes. A useful clip starts with tension, then earns a small shift. Maybe the shift is from working harder to working on the right constraint. Maybe it is from chasing views to measuring saves. If a moment does not contain a before and an after, it is probably context, not content. Context is important inside the episode. It is expensive inside the clip. The clip has to be able to stand on its own without a runway.
So when you distill, ask three questions. First, what is the claim? Second, what is the concrete example or number? Third, what is the sentence someone would repeat at dinner? If you cannot answer all three, keep looking. And please stop starting clips with the words, so, basically, or the thing is. Those words are warm-up laps. The audience did not come to watch you warm up. Start on the idea. You can always add the context in the caption, in the on-screen text, or in the next sentence.
Now let us talk about distribution. Cross-posting the same caption to five platforms is not distribution. It is copy-paste with extra steps. Each platform has a different reason to exist. On LinkedIn, people want a professional argument they can share with their team. On TikTok, they want a fast, human demonstration. On YouTube Shorts, they want a complete little lesson. On Instagram, they want a saveable aesthetic. On X, they want a sharp claim that invites a reply. The clip can stay the same. The framing should not.
Hooks are where most good clips die. A hook is not a summary. A hook is a promise with a little bit of danger in it. Compare, here is my three step content strategy, with, your content is not failing because of reach. It is failing because the first two seconds are a warm-up. The second version names a fear, implies a cause, and makes you want the answer. You do not need clickbait. You need specificity. The more precisely you describe the problem, the less you have to exaggerate the solution.
Measurement is the next layer. Views are a lagging indicator and a terrible daily boss. If you check views every ten minutes, you will optimize for the wrong thing. Track leading indicators instead. Did people stay past the first three seconds? Did they save the clip? Did they send it to someone? Did they ask a question that proves they understood the argument? Those signals tell you whether the idea landed. Then change one variable at a time. Change the hook, not the hook and the edit and the platform and the posting time. Otherwise you learn nothing and call it bad luck.
Let me give you a simple weekly cadence. On Monday, capture one long conversation. On Tuesday, read the transcript and highlight the five moments where the energy changes. On Wednesday, cut those moments into drafts. Do not perfect them. On Thursday, write platform-specific hooks and captions. On Friday, publish three of them and look at the leading indicators. Then take the weekend off. The point is not to become a content machine. The point is to build a loop that runs whether you feel inspired or not.
Three mistakes show up again and again. The first is over-editing. New creators add zooms, sound effects, captions, memes, and a second background track because they are afraid the idea is not enough. Usually the idea is enough. The second mistake is refusing to repeat yourself. You will say the same belief fifty times in fifty different ways. That is not repetition. That is positioning. The third mistake is copying a format without copying the reason it works. The reason is not the font. The reason is the tension, the specificity, and the payoff.
Here is the reframe I want you to keep. You are not behind. You are disorganized. The creators you admire are not producing more ideas than you. They have a shorter path from idea to published asset. That path is a system, and systems can be built. Start with one source of truth. Pick one weekly recording slot. Choose one metric that actually reflects whether the idea landed. Then let the clips compound. You do not need a bigger audience before you build the habit. You need the habit before the audience has a reason to stay.
If you take one thing from this, take the three layer loop: capture, distill, distribute. Capture one honest conversation. Distill the moment where a belief changes. Distribute it with a promise that matches the platform. Do that for four weeks and you will have something more valuable than a viral hit. You will have a repeatable way to think in public. And that is the real creator operating system.
"""

SHORT_TITLE = "Your Best Content Is Already Recorded"
SHORT_LABEL = "SHORT-FORM DEMO  /  80 SECONDS"
SHORT_SCRIPT = """
Your best content is probably sitting in a folder right now. You recorded it, you meant to edit it, and then life happened. Here is the fix. Stop trying to publish everything. Instead, find the one moment where your thinking changes. That moment is the clip. Start on the idea, not on the setup. Give the audience a reason to stay in the first two seconds. Then make the ending earn the beginning. One more thing. Do not write the same caption for every platform. The clip stays. The promise changes. Do this once a week for a month and you will stop asking whether you have anything to say. You will start asking which idea deserves the next slot. That is a much better question.
Here is the simplest workflow I know. Record one long conversation. Pull the transcript. Highlight five moments where the energy shifts. Cut the two strongest. Write three hooks for each. Publish one, save the rest. The goal is not a perfect batch. The goal is a loop you can repeat next week. That is how a library starts. One honest source, a few sharp moments, and a promise that respects the platform. You do not need more motivation. You need a smaller gap between recording and publishing.
"""


def log(message: str) -> None:
    print(message, flush=True)


def run(args: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-3000:]
        raise RuntimeError(f"Command failed ({args[0]}): {detail}")


def duration_of(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr}")
    return float(result.stdout.strip() or 0)


def sentences_from(script: str) -> list[str]:
    text = re.sub(r"\s+", " ", script).strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def synthesize(sentences: list[str], work: Path) -> list[Path]:
    if not TTS_SCRIPT.exists():
        raise RuntimeError(f"Missing TTS helper: {TTS_SCRIPT}")
    payload = work / "sentences.json"
    payload.write_text(json.dumps(sentences, ensure_ascii=False), encoding="utf-8")
    voice_dir = work / "sentences"
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        raise RuntimeError(
            "Windows PowerShell with System.Speech is required to rebuild the sample audio. "
            "The checked-in sample media already works without it."
        )
    log(f"Synthesizing {len(sentences)} sentences with System.Speech...")
    run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(TTS_SCRIPT),
            "-JsonFile",
            str(payload),
            "-OutputDir",
            str(voice_dir),
        ]
    )
    wavs = sorted(voice_dir.glob("sentence-*.wav"))
    if len(wavs) != len(sentences):
        raise RuntimeError(f"Expected {len(sentences)} sentence WAVs, found {len(wavs)}")
    return wavs


def concat_audio(wavs: list[Path], output: Path, work: Path) -> float:
    list_file = work / "concat.txt"
    lines = ["ffconcat version 1.0"]
    for wav in wavs:
        safe = wav.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{safe}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-ac",
            "1",
            "-ar",
            "24000",
            "-c:a",
            "pcm_s16le",
            str(output),
        ]
    )
    return duration_of(output)


def build_transcript(sentences: list[str], wavs: list[Path]) -> dict:
    cursor = 0.0
    segments: list[dict] = []
    for sentence, wav in zip(sentences, wavs, strict=True):
        duration = max(0.4, duration_of(wav))
        words = sentence.split()
        # SAPI leaves a small tail of silence around each utterance. Keep a
        # narrow inner span so word timings land on speech rather than air.
        speech_start = cursor + min(0.08, duration * 0.04)
        speech_end = cursor + max(speech_start - cursor + 0.2, duration - min(0.16, duration * 0.06))
        weights = [max(2, len(word.strip(".,!?;:"))) for word in words]
        total_weight = max(1, sum(weights))
        span = max(0.2, speech_end - speech_start)
        word_rows = []
        word_cursor = speech_start
        for word, weight in zip(words, weights, strict=True):
            word_end = word_cursor + span * weight / total_weight
            word_rows.append(
                {
                    "start": round(word_cursor, 3),
                    "end": round(word_end, 3),
                    "word": word,
                }
            )
            word_cursor = word_end
        if word_rows:
            word_rows[-1]["end"] = round(speech_end, 3)
        segments.append(
            {
                "start": round(cursor, 3),
                "end": round(cursor + duration, 3),
                "text": sentence,
                "speaker": "A",
                "words": word_rows,
            }
        )
        cursor += duration
    return {
        "language": "en",
        "text": " ".join(sentences),
        "segments": segments,
        "provider": "sample-ground-truth",
        "duration_s": round(cursor, 3),
    }


def font_option() -> str:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    ]
    for path in candidates:
        if path.exists():
            escaped = path.as_posix().replace(":", "\\:").replace("'", "\\'")
            return f"fontfile='{escaped}'"
    return ""


def make_video(
    audio: Path,
    output: Path,
    *,
    title: str,
    label: str,
    subtitle: str,
    crf: int = 29,
) -> None:
    duration = duration_of(audio)
    font = font_option()
    font_prefix = f"{font}:" if font else ""
    safe_title = title.replace(":", " -").replace("'", "").replace(",", " ")
    filter_complex = (
        "[0:v]"
        "drawbox=x=0:y=0:w=iw:h=ih:color=0x0B0E14:t=fill,"
        "drawbox=x=0:y=0:w=iw:h=360:color=0x111A2A@0.55:t=fill,"
        "drawbox=x=0:y=0:w=iw:h=6:color=0xD7FF63@0.95:t=fill,"
        "drawbox=x=80:y=636:w=1120:h=2:color=0xFFFFFF@0.10:t=fill,"
        f"drawtext={font_prefix}text='CLIPMIND  /  DEMO SOURCE':x=80:y=66:fontsize=22:"
        "fontcolor=0xD7FF63,"
        f"drawtext={font_prefix}text='{label}':x=80:y=112:fontsize=18:fontcolor=0x93A1B5,"
        f"drawtext={font_prefix}text='{safe_title}':x=80:y=210:fontsize=56:fontcolor=0xFFFFFF,"
        f"drawtext={font_prefix}text='{subtitle}':"
        "x=80:y=300:fontsize=24:fontcolor=0xAEB9C9,"
        "drawbox=x=80:y=600:w=1120:h=3:color=0xD7FF63@0.55:t=fill"
        "[bg];"
        "[1:a]showwaves=s=1120x120:mode=cline:colors=0xD7FF63:rate=30,"
        "format=yuva420p,colorchannelmixer=aa=0.82[wave];"
        "[bg][wave]overlay=80:438:shortest=1[v]"
    )
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0B0E14:s=1280x720:r=30:d={duration:.3f}",
            "-i",
            str(audio),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-t",
            f"{duration:.3f}",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_sample(
    *,
    script: str,
    slug: str,
    title: str,
    label: str,
    manifest: dict,
    force: bool,
    audio_only: bool = False,
    write_transcript: bool = False,
) -> None:
    video_path = SAMPLES / f"{slug}.mp4"
    audio_path = SAMPLES / f"{slug}.m4a" if audio_only else None
    if video_path.exists() and not force and audio_path is None:
        transcript = manifest.get(sha256(video_path))
        if transcript:
            log(f"Skipping {video_path.name} (already generated)")
            return
    with tempfile.TemporaryDirectory(prefix="clipmind-samples-") as temp:
        work = Path(temp)
        sentences = sentences_from(script)
        wavs = synthesize(sentences, work)
        full_audio = work / "voice.wav"
        total = concat_audio(wavs, full_audio, work)
        log(f"{slug}: {len(sentences)} sentences, {total / 60:.1f} minutes of audio")
        transcript = build_transcript(sentences, wavs)
        if write_transcript:
            (SAMPLES / "demo-transcript.txt").write_text(
                "\n\n".join(sentences) + "\n", encoding="utf-8"
            )
        make_video(
            full_audio,
            video_path,
            title=title,
            label=label,
            subtitle=(
                "A grounded long-form source for the ClipMind pipeline"
                if write_transcript
                else "A short source for fast iteration and evaluation"
            ),
        )
        manifest[sha256(video_path)] = transcript
        log(f"Built {video_path.name} ({video_path.stat().st_size / 1_000_000:.1f} MB)")
        if audio_only:
            assert audio_path is not None
            run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(full_audio),
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    str(audio_path),
                ]
            )
            manifest[sha256(audio_path)] = transcript
            log(f"Built {audio_path.name} ({audio_path.stat().st_size / 1_000_000:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Rebuild files even if they exist")
    args = parser.parse_args()
    SAMPLES.mkdir(parents=True, exist_ok=True)
    manifest_path = SAMPLES / "transcripts.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest = {key: value for key, value in manifest.items() if isinstance(value, dict)}

    build_sample(
        script=LONG_SCRIPT,
        slug="demo-long",
        title=LONG_TITLE,
        label=LONG_LABEL,
        manifest=manifest,
        force=args.force,
        write_transcript=True,
    )
    build_sample(
        script=SHORT_SCRIPT,
        slug="demo-short",
        title=SHORT_TITLE,
        label=SHORT_LABEL,
        manifest=manifest,
        force=args.force,
        audio_only=True,
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    log(f"Wrote {manifest_path} with {len(manifest)} media fingerprints")
    for path in sorted(SAMPLES.glob("demo-*")):
        if path.suffix in {".mp4", ".m4a"}:
            log(f"  {path.name:<20} {path.stat().st_size / 1_000_000:>6.1f} MB  {sha256(path)[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
