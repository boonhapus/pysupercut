"""Timeline construction: convert OverlapMatches into an ordered Segment list."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from pysupercut.match import OverlapMatch, TimeRange
from pysupercut.probe import VideoFile


class SegmentStatus(Enum):
    KEEP = auto()
    DROPPED = auto()


@dataclass
class Segment:
    """A contiguous slice of a source file to include in the output."""

    file: Path
    start: float  # seconds into the source file
    end: float  # seconds into the source file (exclusive)
    status: SegmentStatus = SegmentStatus.KEEP

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Timeline:
    segments: list[Segment]
    dropped_files: list[Path]


# ── Containment check ─────────────────────────────────────────────────────────


def _is_contained(
    inner: VideoFile, outer: VideoFile, matches: list[OverlapMatch]
) -> bool:
    """True if inner is entirely duplicated within outer based on match ranges."""
    for m in matches:
        files = {m.file_a, m.file_b}
        if inner.path not in files or outer.path not in files:
            continue

        # Get the range attributed to inner
        inner_range = m.range_in_a if m.file_a == inner.path else m.range_in_b

        # inner is contained if the matched range covers ≥ 95% of its duration
        coverage = inner_range.duration / inner.duration
        if coverage >= 0.95:
            return True

    return False


def _find_dropped(
    video_files: list[VideoFile], matches: list[OverlapMatch]
) -> set[Path]:
    """Identify files whose entire content is a duplicate of another file."""
    dropped: set[Path] = set()
    for i, fi in enumerate(video_files):
        for j, fj in enumerate(video_files):
            if i == j:
                continue
            if fj.path in dropped:
                continue
            if _is_contained(fi, fj, matches):
                dropped.add(fi.path)
                break
    return dropped


# ── Keep-range computation ────────────────────────────────────────────────────


def _keep_range_for_file(
    vf: VideoFile,
    matches: list[OverlapMatch],
    ordered_files: list[Path],
    dropped: set[Path],
) -> tuple[float, float]:
    """
    Return (start_trim, end_trim) for vf.

    Rule: if file B overlaps with the END of file A (its predecessor), trim B's
    start by the overlap length. If B also overlaps with the START of file C
    (its successor), trim B's end.
    """
    my_idx = ordered_files.index(vf.path)
    start_trim = 0.0
    end_trim = vf.duration

    print(f"[DEBUG] _keep_range_for_file: {vf.path.name}, duration={vf.duration:.1f}s")

    for m in matches:
        files = {m.file_a, m.file_b}
        if vf.path not in files:
            continue

        other = m.file_b if m.file_a == vf.path else m.file_a
        if other in dropped:
            continue

        other_idx = ordered_files.index(other)
        my_range = m.range_in_a if m.file_a == vf.path else m.range_in_b
        other_range = m.range_in_b if m.file_a == vf.path else m.range_in_a

        print(
            f"[DEBUG]   match with {other.name}: my_range={my_range.start:.1f}-{my_range.end:.1f}, other_range={other_range.start:.1f}-{other_range.end:.1f}"
        )

if other_idx < my_idx:
            # Predecessor: other file appears BEFORE me
            # Check if the match is at the START of my file (recap situation)
            # If my_range.start is near 0, the match is at my start = duplicate intro
            if my_range.start < 60.0:
                # Match at my start = I'm the successor with duplicate intro
                # Keep from where my unique content starts (after the dup)
                candidate = my_range.end
                print(f"[DEBUG]     predecessor: dup at MY start, trim MY start to {candidate:.1f}")
                if candidate > start_trim:
                    start_trim = candidate
            else:
                # Match elsewhere - this is NOT a duplicate intro to trim
                print(f"[DEBUG]     predecessor: dup NOT at MY start, no trim")

        if other_idx > my_idx:
            # Successor: other file appears AFTER me
            # Check if the match is at the END of my file (preview situation)
            # If my_range.end is near my duration, the match is at my end = duplicate preview
            if my_range.end > vf.duration - 60.0:
                # Match at my end = I'm the predecessor with duplicate preview
                # Keep up to where my unique content ends (before the dup)
                candidate = my_range.start
                print(f"[DEBUG]     successor: dup at MY end, trim MY end to {candidate:.1f}")
                if candidate < end_trim:
                    end_trim = candidate
            else:
                # Match elsewhere - this is NOT a duplicate preview to trim
                print(f"[DEBUG]     successor: dup NOT at MY end, no trim")

    print(f"[DEBUG]   result: start_trim={start_trim:.1f}, end_trim={end_trim:.1f}")
    return start_trim, end_trim


# ── Build timeline ────────────────────────────────────────────────────────────


def build_timeline(
    video_files: list[VideoFile],
    matches: list[OverlapMatch],
) -> Timeline:
    """
    Convert VideoFile list + OverlapMatches into a Timeline.

    Files are assumed to be in chronological order (same order as video_files).
    """
    ordered_paths = [vf.path for vf in video_files]
    dropped = _find_dropped(video_files, matches)

    print(
        f"[DEBUG] build_timeline: {len(video_files)} files, {len(matches)} matches, dropped={dropped}"
    )
    for i, m in enumerate(matches):
        print(
            f"[DEBUG]   match {i}: {m.file_a.name} [{m.range_in_a.start:.1f}-{m.range_in_a.end:.1f}] <-> {m.file_b.name} [{m.range_in_b.start:.1f}-{m.range_in_b.end:.1f}]"
        )

    segments: list[Segment] = []

    for vf in video_files:
        if vf.path in dropped:
            segments.append(
                Segment(
                    file=vf.path,
                    start=0.0,
                    end=vf.duration,
                    status=SegmentStatus.DROPPED,
                )
            )
            continue

        start, end = _keep_range_for_file(vf, matches, ordered_paths, dropped)

        # Clamp to valid range
        start = max(0.0, start)
        end = min(vf.duration, end)

        if end <= start:
            # Conservative: if trimming produces zero/negative duration, keep full file
            start, end = 0.0, vf.duration

        segments.append(Segment(file=vf.path, start=start, end=end))

    return Timeline(
        segments=[s for s in segments if s.status == SegmentStatus.KEEP],
        dropped_files=sorted(dropped),
    )


# ── Duration invariant ────────────────────────────────────────────────────────


def verify_duration_invariant(
    video_files: list[VideoFile],
    timeline: Timeline,
    matches: list[OverlapMatch],
) -> None:
    """
    Raise ValueError if the output duration is implausibly long or short.

    Output must be:
    - ≤ sum of all input durations
    - ≥ longest single input file (we can't produce less than one episode's worth)
    """
    total_input = sum(vf.duration for vf in video_files)
    output_duration = sum(s.duration for s in timeline.segments)
    longest = max((vf.duration for vf in video_files), default=0.0)

    if output_duration > total_input + 1.0:  # 1 s tolerance for float rounding
        raise ValueError(
            f"Duration invariant violated: output ({output_duration:.1f}s) > "
            f"total input ({total_input:.1f}s)"
        )

    if output_duration < longest - 1.0:
        raise ValueError(
            f"Duration invariant violated: output ({output_duration:.1f}s) < "
            f"longest input file ({longest:.1f}s). "
            f"Something was over-trimmed."
        )
