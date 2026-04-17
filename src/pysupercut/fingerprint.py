"""Audio and video fingerprinting."""

from __future__ import annotations

import asyncio
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import av
import imagehash
from PIL import Image

from pysupercut.probe import VideoFile


@dataclass(frozen=True)
class AudioFingerprint:
    file: Path
    duration: float          # seconds reported by fpcalc
    raw: bytes               # packed int32 array (chromaprint fingerprint)

    @property
    def ints(self) -> list[int]:
        count = len(self.raw) // 4
        return list(struct.unpack(f"{count}i", self.raw))


@dataclass(frozen=True)
class VideoFingerprint:
    file: Path
    frame_hashes: list[int]  # dhash values, one per sampled frame
    sample_fps: float        # frames-per-second at which frames were sampled


@dataclass(frozen=True)
class FileFingerprint:
    audio: AudioFingerprint | None
    video: VideoFingerprint


# ── Audio ─────────────────────────────────────────────────────────────────────

def _fingerprint_audio_sync(path: Path, fpcalc: str) -> AudioFingerprint:
    # fpcalc can't decode Opus (or many other codecs) directly.
    # Extract audio to a temp WAV via ffmpeg first, then fingerprint that.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-v", "quiet", "-y",
                "-i", str(path),
                "-vn",
                "-ar", "11025",     # chromaprint standard sample rate
                "-ac", "1",         # mono
                str(tmp_path),
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg audio extract failed for {path}:\n"
                f"{result.stderr.decode(errors='replace')}"
            )

        fpcalc_result = subprocess.run(
            [fpcalc, "-raw", "-length", "7200", str(tmp_path)],
            capture_output=True,
            text=True,
        )
        if fpcalc_result.returncode != 0:
            raise RuntimeError(
                f"fpcalc failed for {path}:\n{fpcalc_result.stderr}"
            )
    finally:
        tmp_path.unlink(missing_ok=True)

    # fpcalc -raw output: "DURATION=X.XX\nFINGERPRINT=1,2,3,...\n"
    kv: dict[str, str] = {}
    for line in fpcalc_result.stdout.strip().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            kv[k.strip()] = v.strip()

    if "DURATION" not in kv or "FINGERPRINT" not in kv:
        raise ValueError(
            f"fpcalc produced unexpected output for {path}: {fpcalc_result.stdout[:200]!r}"
        )

    duration = float(kv["DURATION"])
    ints = [int(x) for x in kv["FINGERPRINT"].split(",") if x.strip()]
    raw = struct.pack(f"{len(ints)}i", *ints)

    return AudioFingerprint(file=path, duration=duration, raw=raw)


async def _fingerprint_audio(path: Path, fpcalc: str) -> AudioFingerprint:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fingerprint_audio_sync, path, fpcalc)


# ── Video ─────────────────────────────────────────────────────────────────────

_SAMPLE_FPS = 1.0  # sample one frame per second for matching


def _fingerprint_video_sync(path: Path, sample_fps: float = _SAMPLE_FPS) -> VideoFingerprint:
    hashes: list[int] = []
    container = av.open(str(path))
    stream = container.streams.video[0]

    # Sample by wall-clock time, not by frame count.
    # skip_frame="NONREF" would only decode keyframes — AV1 keyframes are
    # sparse and positioned differently per file, producing misaligned hashes.
    interval = 1.0 / sample_fps
    next_sample = 0.0

    for frame in container.decode(video=0):
        frame_time = float(frame.pts * stream.time_base) if frame.pts is not None else 0.0
        if frame_time >= next_sample:
            img = frame.to_image().convert("L")
            h = imagehash.dhash(img, hash_size=8)
            hashes.append(int(str(h), 16))
            next_sample += interval

    container.close()
    return VideoFingerprint(file=path, frame_hashes=hashes, sample_fps=sample_fps)


async def _fingerprint_video(path: Path) -> VideoFingerprint:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fingerprint_video_sync, path)


# ── Combined ──────────────────────────────────────────────────────────────────

async def _fingerprint_file(vf: VideoFile, fpcalc: str) -> FileFingerprint:
    audio_task = (
        _fingerprint_audio(vf.path, fpcalc) if vf.has_audio else asyncio.sleep(0)
    )
    video_task = _fingerprint_video(vf.path)

    audio_result, video_result = await asyncio.gather(audio_task, video_task)

    return FileFingerprint(
        audio=audio_result if vf.has_audio else None,
        video=video_result,
    )


async def fingerprint_all(
    video_files: list[VideoFile], fpcalc: str
) -> list[FileFingerprint]:
    """Fingerprint all files concurrently, returning results in input order."""
    return list(
        await asyncio.gather(*(_fingerprint_file(vf, fpcalc) for vf in video_files))
    )


# ── Validation ────────────────────────────────────────────────────────────────

def validate_fingerprints(
    video_files: list[VideoFile], fingerprints: list[FileFingerprint]
) -> None:
    """Raise ValueError if any fingerprint is empty or mismatched."""
    if len(fingerprints) != len(video_files):
        raise ValueError(
            f"Fingerprint count mismatch: expected {len(video_files)}, "
            f"got {len(fingerprints)}"
        )
    for vf, fp in zip(video_files, fingerprints):
        if fp.video.frame_hashes == []:
            raise ValueError(f"{vf.path.name}: video fingerprint is empty")
        if vf.has_audio and fp.audio is None:
            raise ValueError(f"{vf.path.name}: audio stream present but fingerprint missing")
        if vf.has_audio and fp.audio is not None and fp.audio.raw == b"":
            raise ValueError(f"{vf.path.name}: audio fingerprint is empty")
