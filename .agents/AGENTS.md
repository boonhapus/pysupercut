# AGENTS.md

Guidance for coding agents working on this codebase. For project overview, CLI usage, options, and dev setup see `README.md`.

---

## Architecture

The pipeline runs in 5 sequential phases. Each phase has a single responsibility and defined input/output contract. Do not merge phases or add cross-phase logic.

```
probe → fingerprint → match → timeline → stitch
```

Tickets in `tickets/` map 1:1 to implementation tasks. Each ticket defines the done-when criteria — use these as your success condition before marking a task complete.

---

## Tech stack

- **uv** — package manager and task runner. Never use `pip` directly.
- **attrs / cattrs** — all data structures. No plain dicts or dataclasses for domain objects.
- **structlog** — all logging. No `print()` except the `--dry-run` report and final summary.
- **asyncio** — all I/O concurrency. Use `asyncio.create_subprocess_exec` for ffmpeg/fpcalc. Use `asyncio.to_thread` for CPU-bound work (frame hashing).
- **cyclopts** — CLI only. No argparse or click.
- **niquests** — if HTTP is ever needed. No requests or httpx.

---

## Code rules

**Karpathy guidelines apply.** Source: `tickets/` files reference these. In brief:
- No speculative abstractions. Build what the ticket says, nothing more.
- Every changed line must trace to a ticket.
- Surface assumptions explicitly — don't silently pick an interpretation.
- Define a verifiable done-when before writing code, not after.

**Data structures:**
- All domain objects use `@define` (attrs). Validate with cattrs converters at I/O boundaries (ffprobe output, fpcalc output).
- Never pass raw dicts between phases. Convert at the boundary, use typed objects everywhere else.

**Error handling:**
- Hard errors (`sys.exit(1)`) for: missing `fpcalc` binary, codec mismatch, file not found, ffmpeg non-zero exit, empty segment list after timeline resolution.
- Warnings (structlog `log.warning`) for: no audio stream, signal disagreement on overlap, duration drift on output.
- No catch-all `except Exception` blocks. Catch specific exceptions.

**Async:**
- All subprocess calls via `asyncio.create_subprocess_exec` — never `subprocess.run` in async context.
- CPU-bound loops (frame hashing) via `asyncio.to_thread`.
- Concurrent fan-out via `asyncio.gather`.

**ffmpeg / ffprobe:**
- Always pass `-v quiet` to ffprobe to suppress noise.
- Always stream ffmpeg stderr to structlog at DEBUG — never suppress it silently.
- Always use absolute paths (`.resolve()`) in concat demuxer lists.
- Never use `-ss` before `-i` for trimming — always after, for frame accuracy.

---

## Key invariants

These must hold after their respective phases. Treat violations as hard errors unless noted.

| Invariant | Phase | Severity |
|-----------|-------|----------|
| All files share same codec | Probe | Hard error |
| Every file has ≥1 audio chunk (if `has_audio`) and ≥1 frame hash | Fingerprint | Hard error |
| Every `OverlapMatch` has `confidence ∈ [0, 1]` | Match | Hard error |
| Every `Segment` has `start < end` | Timeline | Hard error |
| `sum(segment durations) ≤ sum(input durations) + 0.5` | Timeline | Hard error |
| Output duration within ±0.5s of expected | Stitch | Warning only |
| Temp directory cleaned up | Stitch | Hard error if cleanup fails |

---

## What not to touch

- Do not add re-ordering logic — file order is caller-supplied and trusted.
- Do not add scene detection, quality scoring, or format conversion — out of scope.
- Do not add a database, cache layer, or persistent state — pipeline is stateless by design.
- Do not change the CLI surface without a corresponding ticket.

---

## Testing approach

Use `--dry-run` to verify phases 1–4 without running ffmpeg. Use `ffprobe` to verify stitch output duration. Construct minimal test fixtures (short overlapping clips) rather than mocking ffmpeg — real subprocess behaviour is part of what needs to work.
