"""Top-level pipeline orchestration."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from pysupercut.check import require_fpcalc
from pysupercut.fingerprint import fingerprint_all, validate_fingerprints
from pysupercut.match import match_all_pairs
from pysupercut.probe import VideoFile, probe_all, validate_codecs
from pysupercut.report import render_dry_run
from pysupercut.timeline import build_timeline, verify_duration_invariant

log = structlog.get_logger()


def run(files: list[Path], *, output: Path, dry_run: bool) -> None:
    """Execute the full pysupercut pipeline."""
    asyncio.run(_run_async(files, output=output, dry_run=dry_run))


async def _run_async(files: list[Path], *, output: Path, dry_run: bool) -> None:
    fpcalc = require_fpcalc()

    log.info("probe.start", file_count=len(files))
    video_files: list[VideoFile] = await probe_all(files)
    validate_codecs(video_files)
    log.info("probe.done", files=[vf.path.name for vf in video_files])

    log.info("fingerprint.start")
    fingerprints = await fingerprint_all(video_files, fpcalc)
    validate_fingerprints(video_files, fingerprints)
    log.info("fingerprint.done")

    log.info("match.start", pairs=len(files) * (len(files) - 1) // 2)
    matches = match_all_pairs(files, fingerprints)
    log.info("match.done", overlaps_found=len(matches))

    log.info("timeline.start")
    timeline = build_timeline(video_files, matches)
    verify_duration_invariant(video_files, timeline, matches)
    log.info(
        "timeline.done",
        segments=len(timeline.segments),
        dropped=len(timeline.dropped_files),
    )

    total_input = sum(vf.duration for vf in video_files)

    if dry_run:
        print(render_dry_run(timeline, output, total_input))
        return

    from pysupercut import stitch
    stitch.run(timeline, output=output)
