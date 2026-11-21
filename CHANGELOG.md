# Changelog

All notable changes to dt-video are documented here. Format: Keep a Changelog; versions: SemVer.

## [0.3.0] - 2026-11-21

### Added

- `dt-video vlog SOURCE OUT`: turn a location recording (for example a DJI Osmo Pocket 3 vlog)
  into a YouTube-ready 1080p video. Cuts silences and black frames (plus any `--cut START:END`),
  covers each jump cut with b-roll from `--broll-dir`, adds `--music` ducked under speech,
  applies a colour/sharpen/fade polish, normalizes loudness to -14 LUFS and writes an edit plan
  JSON beside the output. `--plan-only` writes the plan without rendering.
- `make hooks` installs a pre-push hook that runs `make verify`.

### Changed

- **Renamed from QuackVideo to dt-video.** Distribution `dt-video`, import `dt_video`, CLI `dt-video`,
  environment variables `DT_VIDEO_*` (were `QUACKVIDEO_*`), repository `ducktyper-ai/dt-video`.
  Not previously published to PyPI.

## [0.2.0]

- Rebuilt as a transcript-first creator flywheel (ingest, transcribe, analyze, review, compose, package).
