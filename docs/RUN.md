# Running dt-video from a release

dt-video is a **command-line tool, not a server.** It has no listener, no port and no health URL. Read from `pyproject.toml`, `Makefile` and `src/dt_video/cli.py`; not yet run on ENG-UK (UNVERIFIED until the first deployment).

## Runtime
Python >= 3.12, `uv`, and `ffmpeg` + `ffprobe` on PATH. From the extracted release archive (never from a checkout):

```
uv sync --no-dev          # installs dt-video and its dependencies from uv.lock
uv run dt-video doctor    # preflight: reports ffmpeg/ffprobe paths and providers, exit 0 when usable
```

## Start command
There is no daemon. Commands run on demand, for example:

```
uv run dt-video vlog INPUT.mp4 OUT.mp4 --broll-dir broll/ --music music.mp3
uv run dt-video project init / ingest / transcribe / analyze / compose / package   # see --help
```

A launchd job is not applicable. Use the release only as an installed tool for the operator or other seats.

## Configuration (environment, names only)
| Variable | Meaning |
|---|---|
| `DT_VIDEO_OPENAI_API_KEY` | key for the optional OpenAI transcription provider; supply at run time from OpenPassword, never store in the repo |
| `DT_VIDEO_TRANSCRIPTION_PROVIDER` | transcription provider; default `fake` (offline, no key) |

## Port and health
None (no listener, no launchd job). Smoke command, instead of a health URL:

```
uv run dt-video doctor
```

Expected: exit 0.

## Data directory
The workspace: `./workspace` relative to the working directory by default (`dt-video doctor` prints the resolved path; `--workspace` overrides on pipeline commands). It holds episodes, transcripts and rendered output. Run from a stable absolute directory outside the extracted release so upgrades keep the data.
