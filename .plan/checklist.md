# pysupercut — build checklist

MVP phases marked **[MVP]**. Complete these first before polish.

---

## Phase 0 — Scaffold [MVP]
- [ ] [S-01] uv init + add all deps
- [ ] [S-02] fpcalc startup check
- [ ] [S-03] Stub CLI with cyclopts

## Phase 1 — Probe [MVP]
- [ ] [P-01] ffprobe files async → VideoFile
- [ ] [P-02] Validate same codec across all files

## Phase 2 — Fingerprint [MVP]
- [ ] [F-01] Audio fingerprinting via fpcalc
- [ ] [F-02] Video frame hashing via dhash
- [ ] [F-03] Run fingerprinting concurrently per file
- [ ] [F-04] Validate fingerprint output completeness

## Phase 3 — Match [MVP]
- [ ] [M-01] Audio XOR sliding window
- [ ] [M-02] Video hamming sliding window
- [ ] [M-03] Combine audio + video ranges → OverlapMatch
- [ ] [M-04] Run all N×(N-1)/2 pairs

## Phase 4 — Timeline [MVP]
- [ ] [T-01] Containment check → DROPPED files
- [ ] [T-02] Keep-range computation → trim B's start
- [ ] [T-03] Double-sided trim (B overlaps both A and C)
- [ ] [T-04] Emit ordered Segment list
- [ ] [T-05] Verify segment duration invariant

## Phase 5 — Dry Run [MVP]
- [ ] [D-01] --dry-run output: segments, dropped files, expected duration

## Phase 6 — Stitch [MVP]
- [ ] [ST-01] Re-encode trimmed segments to temp files
- [ ] [ST-02] Build concat demuxer list
- [ ] [ST-03] Final ffmpeg concat → output file
- [ ] [ST-04] Verify output duration

## Phase 7 — Polish
- [ ] [PO-01] structlog throughout all phases
- [ ] [PO-02] Progress reporting per phase
- [ ] [PO-03] Handle files with no audio stream
- [ ] [PO-04] Handle complex interleave edge case
- [ ] [PO-05] README + install instructions
