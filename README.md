# pysupercut

Anime is structurally padded. Opening and ending sequences run every episode. Filler arcs stretch narratives across dozens of episodes that contribute nothing to the story. Recap segments rehash scenes viewers watched hours ago. The result is that a 26-episode series might contain 8 hours of runtime but only 5 hours of story.

`pysupercut` is a pre-processing engine for supercut creation. Given a set of video files in chronological order, it detects content that appears more than once across files, removes the duplicates, and stitches the unique content into a single continuous file.

The output is not a finished supercut. It is a clean, deduplicated foundation — the raw material a human editor would otherwise spend hours producing manually. The goal is to reduce the time between having the source files and having something worth editing.

---

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- `ffmpeg` and `ffprobe` on `$PATH`
- `fpcalc` (chromaprint) on `$PATH`

### Install system dependencies

**macOS**
```bash
brew install ffmpeg chromaprint
```

**Ubuntu/Debian**
```bash
sudo apt install ffmpeg libchromaprint-tools
```

**Windows**
- ffmpeg: https://ffmpeg.org/download.html
- fpcalc: https://acoustid.org/chromaprint

---

## Installation

```bash
git clone <repo>
cd pysupercut
uv sync
```

---

## Usage

### Basic
```bash
uv run pysupercut a.mp4 b.mp4 c.mp4 --output result.mp4
```

Files must be passed **in chronological order**. The tool trims duplicate content from the head of later files, keeping earlier files intact.

### Preview without processing
```bash
uv run pysupercut a.mp4 b.mp4 c.mp4 --dry-run
```

Prints the full deduplication plan — segments, dropped files, expected output duration — without invoking ffmpeg. Use this to audit every decision before committing.

### Tune sensitivity
```bash
uv run pysupercut *.mp4 \
  --min-overlap 10 \
  --phash-threshold 8 \
  --audio-threshold 0.90 \
  --fps 2.0 \
  --output result.mp4
```

---

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output` | `output.mp4` | Output file path |
| `--min-overlap` | `5.0` | Minimum overlap duration in seconds to consider a duplicate |
| `--phash-threshold` | `10` | Max hamming distance (0–64) between frame hashes to count as a match. Lower = stricter. |
| `--audio-threshold` | `0.85` | Min audio fingerprint similarity score (0–1) to count as a match. Higher = stricter. |
| `--fps` | `1.0` | Frame sample rate for video hashing. Higher = more accurate, slower. |
| `--dry-run` | `False` | Print plan and exit. No files written. |

---

## How it works

Overlap detection uses both audio fingerprinting (chromaprint) and video perceptual hashing (dhash) — both signals must agree before a segment is considered a duplicate. This makes it slower but significantly more accurate than single-signal approaches.

1. **Probe** — each file is inspected with `ffprobe` to extract duration, codec, and stream info.
2. **Fingerprint** — audio is fingerprinted with `fpcalc` (chromaprint); video frames are hashed with dhash at the configured sample rate. Both run concurrently.
3. **Match** — every pair of files is compared. An overlap is only confirmed when both audio and video signals agree on the same time range.
4. **Timeline** — overlapping ranges are resolved against the known file order. Files whose content is entirely contained within another are dropped. The head of later files is trimmed.
5. **Stitch** — trimmed segments are re-encoded frame-accurately, then all segments are concatenated into the output via the ffmpeg concat demuxer.

Cut points are frame-accurate but re-encoded (libx264/aac). The rest of the content is stream-copied with no quality loss.

---

## Limitations

- All input files must share the same video codec (e.g. all H.264). Mixed codecs will produce an error.
- Files must be passed in chronological order — the tool does not infer order from content.
- Both audio and video streams are required for full-confidence matching. Files without audio fall back to video-only matching with a capped confidence score.

---

## Dev environment

```bash
# Install deps including dev extras
uv sync --all-extras

# Run tests
uv run pytest

# Run the CLI from source
uv run pysupercut --help
```

Logs go to stderr. Use `--dry-run` liberally when developing — it exercises the full pipeline up to ffmpeg.
