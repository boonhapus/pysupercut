"""Startup environment checks."""

from __future__ import annotations

import shutil
import subprocess
import sys


def require_fpcalc() -> str:
    """Return fpcalc path or exit with an actionable error."""
    path = shutil.which("fpcalc")
    if path is None:
        print(
            "error: fpcalc not found on PATH.\n"
            "Install chromaprint:\n"
            "  Windows : choco install chromaprint  OR  scoop install chromaprint\n"
            "  macOS   : brew install chromaprint\n"
            "  Linux   : apt install libchromaprint-tools",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        result = subprocess.run(
            [path, "-version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            print(f"error: fpcalc found at {path} but failed to run.", file=sys.stderr)
            sys.exit(1)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"error: fpcalc check failed: {exc}", file=sys.stderr)
        sys.exit(1)

    return path
