# PLAN.md — Project Lighthouse

## The problem

Anime is structurally padded. Opening and ending sequences run every episode. Filler arcs stretch narratives across dozens of episodes that contribute nothing to the story. Recap segments rehash scenes viewers watched hours ago. The result is that a 26-episode series might contain 8 hours of runtime but only 5 hours of story.

This padding is accepted as a medium convention, but it is not inevitable. In 2021, Demon Slayer: Mugen Train took the Mugen Train arc — previously spread across television episodes with all the attendant repetition — and released it as a theatrical film. It became the highest-grossing anime film of all time. The format resonated because it respected the viewer's time and let the story breathe without interruption.

That format — the **supercut** — is the north star for this project.

---

## What this project is

`pysupercut` is a pre-processing engine for supercut creation. Given a set of video files in chronological order, it:

1. Detects content that appears more than once across files (overlapping segments, repeated cold opens, recap sequences)
2. Removes the duplicates
3. Stitches the unique content into a single continuous file

The output is not a finished supercut. It is a clean, deduplicated foundation — the raw material a human editor would otherwise spend hours producing manually, scrubbing through episodes frame by frame to find where one ends and another begins, running ad-hoc ffmpeg commands to cut and join.

The goal is to **reduce the time between having the source files and having something worth editing**. Not to eliminate the editor.

---

## What this project is not

- **Not a general video editor.** There is no timeline UI, no effects, no colour grading, no titles. Those belong in a dedicated editing tool downstream.
- **Not a transcription or subtitle tool.** Audio is used for fingerprinting only — to detect duplicate content, not to process speech.
- **Not a cloud service or web application.** This is a local CLI tool, intentionally. Source files are large, private, and should not leave the user's machine.
- **Not a replacement for editorial judgment.** The tool cannot know which scenes are emotionally resonant, which transitions feel right, or what pacing serves the story. That is the human's job. This tool handles the mechanical labour before that work begins.

---

## Design philosophy

**Conservative over aggressive.** When in doubt about whether two segments are duplicates, the tool does nothing. A false positive (removing content that wasn't actually a duplicate) is far more damaging than a false negative (leaving a segment in that could have been removed). Both audio and video signals must agree before any content is removed.

**Transparent before irreversible.** `--dry-run` is a first-class feature, not an afterthought. Every decision the tool makes — what it detected, what it dropped, what it kept — should be visible and reviewable before ffmpeg writes a single byte. The editor should be able to audit the plan and trust it before committing.

**Composable, not monolithic.** The tool does one thing: dedup and stitch. It takes files, produces a file. It is designed to be one step in a pipeline, not the whole pipeline. Other tools handle ingestion, format conversion, subtitle extraction, and final editing. This tool hands off cleanly to all of them.

**Quality of cut over speed of cut.** Trimmed segments are re-encoded frame-accurately rather than snapped to keyframe boundaries. A supercut is watched, not just processed. Visible artefacts at cut points are unacceptable.

---

## The workflow this enables

```
Source episodes (raw files)
        ↓
  [ pysupercut ]        ← this project
        ↓
Deduplicated continuous file
        ↓
  [ human editor ]      ← DaVinci, Premiere, etc.
        ↓
Finished supercut
```

The tool shortens the gap between the first and third row. Everything below the line remains human work — and should stay that way.

---

## Success criteria

The tool is successful when an editor working on a 12-episode anime arc can:

1. Pass the episode files to `pysupercut` in order
2. Review the `--dry-run` output and trust it
3. Run the stitch and receive a clean file with no duplicate content and no visible cut artefacts
4. Open that file in their editor and begin creative work immediately — without first spending hours on mechanical cleanup

That outcome — hours saved, creative work unblocked — is what this project is for.
