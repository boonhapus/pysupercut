"""ffmpeg-based stitching: re-encode trimmed segments then concat."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import structlog

from pysupercut.timeline import Segment, Timeline

log = structlog.get_logger()

_DURATION_TOLERANCE = 2.0  # seconds — acceptable output vs expected delta


def _ffmpeg(*args: str | Path) -> subprocess.CompletedProcess[str]:
    cmd = ["ffmpeg", "-y", *[str(a) for a in args]]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed:\nCMD: {' '.join(cmd)}\nSTDERR:\n{result.stderr[-2000:]}"
        )
    return result


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr}")
    import json
    data = json.loads(result.stdout)
    return float(data["format"].get("duration", 0))


def _re_encode_segment(seg: Segment, dest: Path) -> None:
    """Re-encode a trimmed segment to dest with frame-accurate cut points."""
    duration = seg.end - seg.start
    _ffmpeg(
        "-ss", str(seg.start),
        "-i", seg.file,
        "-t", str(duration),
        # Re-encode for frame accuracy — copy would snap to keyframe boundaries.
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-avoid_negative_ts", "make_zero",
        dest,
    )
    log.debug("stitch.segment_encoded", file=seg.file.name, start=seg.start, end=seg.end, dest=dest.name)


def _build_concat_list(temp_files: list[Path], list_path: Path) -> None:
    """Write an ffmpeg concat demuxer input file."""
    lines = []
    for p in temp_files:
        escaped = str(p).replace("'", r"\'")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _concat(list_path: Path, output: Path) -> None:
    _ffmpeg(
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        output,
    )
    log.info("stitch.concat_done", output=str(output))


def _verify_duration(output: Path, expected: float) -> None:
    actual = _probe_duration(output)
    delta = abs(actual - expected)
    if delta > _DURATION_TOLERANCE:
        raise RuntimeError(
            f"Output duration mismatch: expected {expected:.1f}s, "
            f"got {actual:.1f}s (delta {delta:.1f}s > tolerance {_DURATION_TOLERANCE}s)"
        )
    log.info("stitch.duration_verified", expected=expected, actual=actual, delta=delta)


def run(timeline: Timeline, *, output: Path) -> None:
    """Execute the full stitch pipeline: re-encode → concat → verify."""
    expected_duration = sum(s.duration for s in timeline.segments)
    log.info("stitch.start", segments=len(timeline.segments), expected_duration=expected_duration)

    with tempfile.TemporaryDirectory(prefix="pysupercut_") as tmp:
        tmp_dir = Path(tmp)
        temp_files: list[Path] = []

        for i, seg in enumerate(timeline.segments):
            dest = tmp_dir / f"seg_{i:04d}.mkv"
            log.info("stitch.encoding", index=i + 1, total=len(timeline.segments), file=seg.file.name)
            _re_encode_segment(seg, dest)
            temp_files.append(dest)

        list_path = tmp_dir / "concat.txt"
        _build_concat_list(temp_files, list_path)

        output.parent.mkdir(parents=True, exist_ok=True)
        _concat(list_path, output)

    _verify_duration(output, expected_duration)
    log.info("stitch.complete", output=str(output))
    print(f"Done. Output: {output}  ({expected_duration:.0f}s)")
