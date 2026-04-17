"""ffprobe-based video file probing."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VideoFile:
    path: Path
    duration: float          # seconds
    video_codec: str
    width: int
    height: int
    frame_rate: float        # fps
    has_audio: bool
    audio_codec: str | None


async def _probe_one(path: Path) -> VideoFile:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed for {path}:\n{stderr.decode(errors='replace')}"
        )

    data = json.loads(stdout)
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video is None:
        raise ValueError(f"{path}: no video stream found")

    duration = float(fmt.get("duration") or video.get("duration", 0))

    # frame rate: "num/den" string
    raw_fr = video.get("r_frame_rate", "0/1")
    num, _, den = raw_fr.partition("/")
    frame_rate = float(num) / float(den) if float(den) else 0.0

    return VideoFile(
        path=path,
        duration=duration,
        video_codec=video.get("codec_name", "unknown"),
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        frame_rate=frame_rate,
        has_audio=audio is not None,
        audio_codec=audio.get("codec_name") if audio else None,
    )


async def probe_all(files: list[Path]) -> list[VideoFile]:
    """Probe all files concurrently, returning VideoFile list in input order."""
    return list(await asyncio.gather(*(_probe_one(f) for f in files)))


def validate_codecs(video_files: list[VideoFile]) -> None:
    """Raise ValueError if files don't share the same video codec."""
    codecs = {vf.video_codec for vf in video_files}
    if len(codecs) > 1:
        detail = ", ".join(
            f"{vf.path.name}={vf.video_codec}" for vf in video_files
        )
        raise ValueError(
            f"Files have mixed video codecs ({', '.join(codecs)}). "
            f"Re-encode to a common codec first.\nDetail: {detail}"
        )
