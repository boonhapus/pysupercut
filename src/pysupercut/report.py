"""Dry-run report rendering."""

from __future__ import annotations

from pathlib import Path

from pysupercut.timeline import Timeline


def _fmt_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h:
        return f"{h}h {m:02d}m {s:04.1f}s"
    if m:
        return f"{m}m {s:04.1f}s"
    return f"{s:.1f}s"


def render_dry_run(
    timeline: Timeline,
    output: Path,
    total_input_duration: float,
) -> str:
    lines: list[str] = []
    lines.append("-- pysupercut dry-run ---------------------------------------------")

    if timeline.dropped_files:
        lines.append(f"\nDROPPED files ({len(timeline.dropped_files)}) - fully duplicated content:")
        for p in timeline.dropped_files:
            lines.append(f"  x  {p.name}")

    output_duration = sum(s.duration for s in timeline.segments)
    saved = total_input_duration - output_duration

    lines.append(f"\nSEGMENTS ({len(timeline.segments)}):")
    for i, seg in enumerate(timeline.segments, 1):
        trim_note = ""
        if seg.start > 0.01 or seg.end < seg.end + 0.01:
            trim_note = f"  [{_fmt_duration(seg.start)} to {_fmt_duration(seg.end)}]"
        else:
            trim_note = "  [full]"
        lines.append(f"  {i:3d}. {seg.file.name}{trim_note}  ({_fmt_duration(seg.duration)})")

    lines.append("")
    lines.append(f"Input  total : {_fmt_duration(total_input_duration)}")
    lines.append(f"Output total : {_fmt_duration(output_duration)}")
    lines.append(f"Saved        : {_fmt_duration(saved)}  ({100 * saved / total_input_duration:.1f}%)" if total_input_duration else "Saved        : 0s")
    lines.append(f"Output file  : {output}")
    lines.append("")
    lines.append("No files will be written. Remove --dry-run to execute.")
    lines.append("-------------------------------------------------------------------")

    return "\n".join(lines)
