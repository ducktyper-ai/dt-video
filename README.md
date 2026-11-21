# dt-video

Transcript-first content engine for podcasts, talking-head videos, tutorials, and short-form social packages.

dt-video turns one recording into a reviewable set of platform-ready files. It does not upload or schedule posts.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- FFmpeg and ffprobe on `PATH`

```bash
uv sync --extra dev
make verify
```

## Workflow

```bash
dt-video project init --name studio --workspace workspace
dt-video ingest recording.mp4 --profile talking-head --workspace workspace
dt-video run EPISODE_ID --until analyze --workspace workspace
dt-video review list EPISODE_ID --workspace workspace
dt-video review approve EPISODE_ID MOMENT_ID --workspace workspace
dt-video compose EPISODE_ID --workspace workspace
dt-video package EPISODE_ID --workspace workspace
```

Profiles: `podcast`, `talking-head`, `tutorial`, `social`.

Every command accepts `--json` for agents.

## Output layout

```
workspace/episodes/<id>/
  source/                 immutable copy of the recording
  artifacts/ingest/       probe + QC
  artifacts/normalize/    loudnorm audio + mezzanine
  artifacts/transcript/   json, srt, vtt, markdown
  artifacts/analyze/      chapters + ranked moments
  artifacts/review/       approval manifest
  artifacts/compose/      approved clips + captions
  artifacts/packages/     per-platform handoff directories
```

Compose and package run only after at least one moment is approved.

## Providers

Default transcription is `fake` (deterministic, for tests and dry runs).

```bash
export DT_VIDEO_TRANSCRIPTION_PROVIDER=openai
export DT_VIDEO_OPENAI_API_KEY=...
```

Analysis defaults to a heuristic ranker that uses transcript windows, duration policy, scene cuts, and imported performance signals.

```bash
dt-video metrics import EPISODE_ID stats.csv --workspace workspace
```

CSV columns: `moment_id,platform,views,retention_3s,retention_30s,ctr,comments`.

## License

MIT

## Location vlog to YouTube

```bash
dt-video vlog osmo-day1.mp4 out/day1.mp4 \
  --broll-dir broll/ --music music/lofi.mp3 --cut 312:340
```

Cuts dead air and black frames, covers each jump cut with b-roll, ducks background music under speech,
applies a light colour/sharpen/fade polish, normalizes loudness to -14 LUFS and exports 1080p H.264.
The edit plan is written next to the output (`day1.plan.json`); use `--plan-only` to inspect it first.
