---
name: dt-video
description: Run the dt-video creator flywheel from Cursor. Use when ingesting recordings, transcribing, ranking clips, reviewing moments, composing captions, or packaging platform-ready social/podcast/tutorial assets.
---

# dt-video

Drive the `dt-video` CLI. Do not reimplement FFmpeg, transcription, or packaging in ad-hoc scripts.

## Preconditions

1. `uv sync --extra dev` in the repo.
2. `ffmpeg` and `ffprobe` on PATH (`dt-video doctor --json`).
3. A workspace directory (`dt-video project init` or `--workspace`).

## Canonical loop

```bash
dt-video ingest SOURCE --profile PROFILE --workspace WS --json
dt-video run EPISODE_ID --until analyze --workspace WS --json
dt-video review list EPISODE_ID --workspace WS --json
# stop for human approval
dt-video review approve EPISODE_ID MOMENT_ID --workspace WS --json
dt-video compose EPISODE_ID --workspace WS --json
dt-video package EPISODE_ID --workspace WS --json
```

Profiles: `podcast`, `talking-head`, `tutorial`, `social`.

## Rules

- Prefer `--json` so results are machine-readable.
- Never compose or package until at least one moment is `approved`.
- Do not upload or publish. Packages are the handoff.
- Resume is hash-based; use `--force` only when asked.
- Inspect artifacts under `workspace/episodes/<id>/artifacts/` on failure.
- Default transcription provider is `fake`. Use `openai` only when an API key is configured.
- Do not commit `.env`, API keys, or generated media workspaces.
