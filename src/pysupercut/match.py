"""Overlap detection between file pairs via audio XOR and video hamming windows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pysupercut.fingerprint import AudioFingerprint, FileFingerprint, VideoFingerprint

# ── Thresholds ────────────────────────────────────────────────────────────────

# Fraction of XOR bits that must be zero for an audio window to be a match.
# chromaprint fingerprints: >= 0.65 bits matching is considered a duplicate.
_AUDIO_MATCH_THRESHOLD = 0.35   # max fraction of differing bits

# Average hamming distance per hash pair for video window to be a match.
# dhash 64-bit: <= 10 bits differing ~= visually identical.
_VIDEO_MATCH_THRESHOLD = 10.0   # max mean hamming distance

# Minimum overlap duration in seconds to be considered a real duplicate.
_MIN_OVERLAP_SECONDS = 10.0

# Audio temporal consistency: audio and video match positions must agree within N seconds.
_AV_AGREEMENT_TOLERANCE = 10.0


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TimeRange:
    """A half-open time interval [start, end) in seconds."""
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    def overlaps(self, other: "TimeRange") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class OverlapMatch:
    """A confirmed duplicate segment between two files."""
    file_a: Path
    file_b: Path
    range_in_a: TimeRange   # where the duplicate content sits in file A
    range_in_b: TimeRange   # where the duplicate content sits in file B


# ── Helpers ───────────────────────────────────────────────────────────────────

def _popcount(x: int) -> int:
    """Count set bits in a 32-bit integer."""
    x = x & 0xFFFF_FFFF
    x -= (x >> 1) & 0x5555_5555
    x = (x & 0x3333_3333) + ((x >> 2) & 0x3333_3333)
    x = (x + (x >> 4)) & 0x0F0F_0F0F
    return ((x * 0x0101_0101) & 0xFFFF_FFFF) >> 24


def _hamming32(a: int, b: int) -> int:
    return _popcount(a ^ b)


def _greedy_nonoverlapping(
    candidates: list[tuple[float, int, int, int]],  # (score, a_start, b_start, length)
) -> list[tuple[float, int, int, int]]:
    """
    Greedy non-overlapping selection.

    Sort candidates by score (ascending = better), then greedily pick each
    match that does not overlap any already-selected match in A or B.
    """
    selected: list[tuple[float, int, int, int]] = []
    used_a: list[tuple[int, int]] = []  # (start, end) index ranges in A
    used_b: list[tuple[int, int]] = []  # (start, end) index ranges in B

    for score, a_start, b_start, length in sorted(candidates, key=lambda c: c[0]):
        a_end = a_start + length
        b_end = b_start + length

        # Check no overlap with any already-selected range in A or B
        overlap_a = any(a_start < ea and sa < a_end for sa, ea in used_a)
        overlap_b = any(b_start < eb and sb < b_end for sb, eb in used_b)

        if not overlap_a and not overlap_b:
            selected.append((score, a_start, b_start, length))
            used_a.append((a_start, a_end))
            used_b.append((b_start, b_end))

    return selected


# ── Audio matching ────────────────────────────────────────────────────────────

def _audio_window_matches(
    fa: AudioFingerprint,
    fb: AudioFingerprint,
    window_sec: float = 30.0,
    step_sec: float = 2.0,
) -> list[tuple[TimeRange, TimeRange]]:
    """
    Sliding window XOR scan. Returns ALL non-overlapping matching (A_range, B_range)
    pairs above threshold, ordered by match quality.

    Each chromaprint int represents ~0.1241 seconds of audio.
    """
    INTS_PER_SEC = 8.06
    a_ints = fa.ints
    b_ints = fb.ints
    win = max(1, round(window_sec * INTS_PER_SEC))
    step = max(1, round(step_sec * INTS_PER_SEC))
    min_len = max(1, round(_MIN_OVERLAP_SECONDS * INTS_PER_SEC))

    candidates: list[tuple[float, int, int, int]] = []

    for a_start in range(0, max(1, len(a_ints) - win + 1), step):
        a_chunk = a_ints[a_start : a_start + win]
        actual_len = len(a_chunk)
        if actual_len < min_len:
            break

        for b_start in range(0, max(1, len(b_ints) - actual_len + 1), step):
            b_chunk = b_ints[b_start : b_start + actual_len]
            if len(b_chunk) < actual_len:
                break

            diff_bits = sum(_hamming32(x, y) for x, y in zip(a_chunk, b_chunk))
            score = diff_bits / (actual_len * 32)

            if score <= _AUDIO_MATCH_THRESHOLD:
                candidates.append((score, a_start, b_start, actual_len))

    selected = _greedy_nonoverlapping(candidates)

    results: list[tuple[TimeRange, TimeRange]] = []
    for _score, a_start, b_start, length in selected:
        a_start_sec = a_start / INTS_PER_SEC
        b_start_sec = b_start / INTS_PER_SEC
        dur = length / INTS_PER_SEC
        if dur >= _MIN_OVERLAP_SECONDS:
            results.append((
                TimeRange(a_start_sec, a_start_sec + dur),
                TimeRange(b_start_sec, b_start_sec + dur),
            ))

    return results


# ── Video matching ────────────────────────────────────────────────────────────

def _video_window_matches(
    va: VideoFingerprint,
    vb: VideoFingerprint,
    window_sec: float = 30.0,
    step_sec: float = 2.0,
) -> list[tuple[TimeRange, TimeRange]]:
    """
    Sliding window hamming scan. Returns ALL non-overlapping matching (A_range, B_range)
    pairs above threshold.
    """
    fps = va.sample_fps
    win = max(1, round(window_sec * fps))
    step = max(1, round(step_sec * fps))
    min_frames = max(1, round(_MIN_OVERLAP_SECONDS * fps))

    a_hashes = va.frame_hashes
    b_hashes = vb.frame_hashes

    candidates: list[tuple[float, int, int, int]] = []

    for a_start in range(0, max(1, len(a_hashes) - win + 1), step):
        a_chunk = a_hashes[a_start : a_start + win]
        actual_len = len(a_chunk)
        if actual_len < min_frames:
            break

        for b_start in range(0, max(1, len(b_hashes) - actual_len + 1), step):
            b_chunk = b_hashes[b_start : b_start + actual_len]
            if len(b_chunk) < actual_len:
                break

            mean_dist = (
                sum(bin(x ^ y).count("1") for x, y in zip(a_chunk, b_chunk))
                / actual_len
            )

            if mean_dist <= _VIDEO_MATCH_THRESHOLD:
                candidates.append((mean_dist, a_start, b_start, actual_len))

    selected = _greedy_nonoverlapping(candidates)

    results: list[tuple[TimeRange, TimeRange]] = []
    for _score, a_start, b_start, length in selected:
        a_start_sec = a_start / fps
        b_start_sec = b_start / fps
        dur = length / fps
        if dur >= _MIN_OVERLAP_SECONDS:
            results.append((
                TimeRange(a_start_sec, a_start_sec + dur),
                TimeRange(b_start_sec, b_start_sec + dur),
            ))

    return results


# ── Combined pair matching ────────────────────────────────────────────────────

def _match_pair(
    fps_a: FileFingerprint,
    fps_b: FileFingerprint,
    file_a: Path,
    file_b: Path,
) -> list[OverlapMatch]:
    """
    Match one (A, B) pair. Returns ALL confirmed non-overlapping OverlapMatches.

    Both audio and video must agree on each match (conservative policy).
    Audio match position must be within _AV_AGREEMENT_TOLERANCE of video match.
    """
    video_matches = _video_window_matches(fps_a.video, fps_b.video)
    if not video_matches:
        return []

    # No audio available on either file — accept video-only matches.
    if fps_a.audio is None or fps_b.audio is None:
        return [
            OverlapMatch(file_a=file_a, file_b=file_b, range_in_a=va, range_in_b=vb)
            for va, vb in video_matches
        ]

    audio_matches = _audio_window_matches(fps_a.audio, fps_b.audio)
    if not audio_matches:
        return []

    # Pair each video match with a confirming audio match (within tolerance).
    confirmed: list[OverlapMatch] = []
    for v_range_a, v_range_b in video_matches:
        for a_range_a, a_range_b in audio_matches:
            if (
                abs(a_range_a.start - v_range_a.start) <= _AV_AGREEMENT_TOLERANCE
                and abs(a_range_b.start - v_range_b.start) <= _AV_AGREEMENT_TOLERANCE
            ):
                confirmed.append(OverlapMatch(
                    file_a=file_a,
                    file_b=file_b,
                    range_in_a=v_range_a,
                    range_in_b=v_range_b,
                ))
                break  # one audio confirmation per video match is enough

    return confirmed


def match_all_pairs(
    files: list[Path],
    fingerprints: list[FileFingerprint],
) -> list[OverlapMatch]:
    """Run all N*(N-1)/2 file pairs and return all confirmed overlap matches."""
    matches: list[OverlapMatch] = []
    n = len(files)
    for i in range(n):
        for j in range(i + 1, n):
            results = _match_pair(
                fingerprints[i], fingerprints[j], files[i], files[j]
            )
            matches.extend(results)
    return matches
