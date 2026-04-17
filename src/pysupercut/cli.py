"""pysupercut CLI."""

from __future__ import annotations

import sys
from pathlib import Path

import cyclopts

from pysupercut.check import require_fpcalc

app = cyclopts.App(
    name="pysupercut",
    help="Deduplicate and stitch episode files into a clean continuous file.",
)


@app.default
def main(
    *files: Path,
    output: Path = Path("supercut.mkv"),
    dry_run: bool = False,
) -> None:
    """
    Process FILES in chronological order, removing duplicate content and stitching
    the unique segments into OUTPUT.

    Parameters
    ----------
    files
        Episode files in chronological order.
    output
        Destination file for the stitched result.
    dry_run
        Print the plan (segments, dropped files, expected duration) without
        writing anything.
    """
    if not files:
        print("error: at least one input file is required.", file=sys.stderr)
        sys.exit(1)

    missing = [f for f in files if not f.exists()]
    if missing:
        joined = ", ".join(str(f) for f in missing)
        print(f"error: files not found: {joined}", file=sys.stderr)
        sys.exit(1)

    fpcalc = require_fpcalc()  # noqa: F841 — checked here, passed to pipeline later

    from pysupercut import pipeline

    try:
        pipeline.run(list(files), output=output, dry_run=dry_run)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
