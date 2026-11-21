"""Location-vlog edit: cut dead air, cover jump cuts with b-roll, add ducked music, polish, export for YouTube.

The edit is a small plan (what to cut, where b-roll goes) rendered with one ffmpeg filter graph.
Planning is pure Python so it can be tested without ffmpeg.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from dt_video.media.engine import FFmpegEngine
from dt_video.media.ops import detect_black, detect_silence

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".webm"}
MIN_KEEP_SEC = 0.3


class BrollPlacement(BaseModel):
    """Overlay a clip on the output timeline. Narration keeps playing underneath."""

    path: Path
    at: float = Field(ge=0, description="Start on the OUTPUT timeline, seconds.")
    duration: float = Field(gt=0)
    source_start: float = Field(default=0.0, ge=0)


class VlogOptions(BaseModel):
    min_silence_sec: float = Field(default=1.0, gt=0, description="Silences at least this long are cut.")
    pad_sec: float = Field(default=0.25, ge=0, description="Breathing room kept on each side of a cut.")
    cut_black: bool = True
    manual_cuts: list[tuple[float, float]] = Field(default_factory=list)
    broll_dir: Path | None = None
    broll_sec: float = Field(default=2.5, gt=0)
    music: Path | None = None
    music_volume: float = Field(default=0.18, ge=0, le=2)
    duck_music: bool = True
    polish: bool = True
    width: int = 1920
    height: int = 1080
    fps: int = 30
    loudness_lufs: float = -14.0


class VlogPlan(BaseModel):
    source: Path
    source_duration: float
    cuts: list[tuple[float, float]]
    keeps: list[tuple[float, float]]
    output_duration: float
    broll: list[BrollPlacement]
    options: VlogOptions


# ---------------------------------------------------------------- planning


def merge_ranges(ranges: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    clamped = sorted((max(0.0, s), min(duration, e)) for s, e in ranges if e > s)
    merged: list[tuple[float, float]] = []
    for start, end in clamped:
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def keep_ranges(duration: float, cuts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Complement of the cuts, dropping slivers shorter than MIN_KEEP_SEC."""
    keeps: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in merge_ranges(cuts, duration):
        if start > cursor:
            keeps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        keeps.append((cursor, duration))
    return [(s, e) for s, e in keeps if e - s >= MIN_KEEP_SEC]


def pad_cuts(cuts: list[tuple[float, float]], pad: float) -> list[tuple[float, float]]:
    """Shrink each cut by pad on both sides so speech is not clipped."""
    return [(s + pad, e - pad) for s, e in cuts if (e - s) > 2 * pad]


def join_points(keeps: list[tuple[float, float]]) -> list[float]:
    """Output-timeline times where two kept segments meet (the jump cuts)."""
    points: list[float] = []
    elapsed = 0.0
    for start, end in keeps[:-1]:
        elapsed += end - start
        points.append(elapsed)
    return points


def list_broll(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS and not p.name.startswith("."))


def place_broll(
    clips: list[tuple[Path, float]],
    points: list[float],
    output_duration: float,
    length: float,
) -> list[BrollPlacement]:
    """Centre a b-roll clip on each jump cut, cycling through the clips, never overlapping."""
    placements: list[BrollPlacement] = []
    if not clips:
        return placements
    last_end = 0.0
    for index, point in enumerate(points):
        path, clip_duration = clips[index % len(clips)]
        dur = min(length, clip_duration)
        if dur < 0.5:
            continue
        at = max(last_end, point - dur / 2)
        dur = min(dur, output_duration - at)
        if dur < 0.5:
            continue
        placements.append(BrollPlacement(path=path, at=round(at, 3), duration=round(dur, 3)))
        last_end = at + dur
    return placements


def plan_vlog(engine: FFmpegEngine, source: Path, options: VlogOptions) -> VlogPlan:
    probe = engine.probe(source)
    duration = probe.duration
    auto: list[tuple[float, float]] = [
        (s, e) for s, e in detect_silence(engine, source) if e - s >= options.min_silence_sec
    ]
    auto = pad_cuts(auto, options.pad_sec)
    if options.cut_black:
        auto += detect_black(engine, source)
    cuts = merge_ranges(auto + list(options.manual_cuts), duration)
    keeps = keep_ranges(duration, cuts)
    out_duration = sum(e - s for s, e in keeps)
    broll: list[BrollPlacement] = []
    if options.broll_dir is not None:
        clips = [(p, engine.probe(p).duration) for p in list_broll(options.broll_dir)]
        broll = place_broll(clips, join_points(keeps), out_duration, options.broll_sec)
    return VlogPlan(
        source=source,
        source_duration=duration,
        cuts=cuts,
        keeps=keeps,
        output_duration=out_duration,
        broll=broll,
        options=options,
    )


# ---------------------------------------------------------------- rendering


def build_filtergraph(plan: VlogPlan, *, has_audio: bool) -> tuple[str, list[str], str, str]:
    """Return (filter_complex, extra input args, video label, audio label).

    Input 0 is the source. When the source has no audio, a silent lavfi input is input 1 instead.
    """
    o = plan.options
    parts: list[str] = []
    inputs: list[str] = []
    next_input = 1
    audio_src = "0:a"
    if not has_audio:
        inputs += ["-f", "lavfi", "-t", f"{plan.source_duration:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        audio_src = f"{next_input}:a"
        next_input += 1

    n = len(plan.keeps)
    for i, (s, e) in enumerate(plan.keeps):
        parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[{audio_src}]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]")
    streams = "".join(f"[v{i}][a{i}]" for i in range(n))
    parts.append(f"{streams}concat=n={n}:v=1:a=1[vc][ac]")

    fit = (
        f"scale={o.width}:{o.height}:force_original_aspect_ratio=decrease,"
        f"pad={o.width}:{o.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={o.fps}"
    )
    chain = fit
    if o.polish:
        total = plan.output_duration
        fade_out = max(0.0, total - 0.6)
        chain += (
            f",eq=contrast=1.06:saturation=1.15,unsharp=5:5:0.4,fade=t=in:st=0:d=0.4,fade=t=out:st={fade_out:.3f}:d=0.6"
        )
    parts.append(f"[vc]{chain}[vbase]")

    current = "vbase"
    for k, b in enumerate(plan.broll):
        parts_input = next_input
        inputs += ["-i", str(b.path)]
        next_input += 1
        parts.append(
            f"[{parts_input}:v]trim=start={b.source_start:.3f}:duration={b.duration:.3f},"
            f"setpts=PTS-STARTPTS+{b.at:.3f}/TB,scale={o.width}:{o.height}:force_original_aspect_ratio=increase,"
            f"crop={o.width}:{o.height},setsar=1,fps={o.fps},format=yuv420p[b{k}]"
        )
        parts.append(
            f"[{current}][b{k}]overlay=enable='between(t,{b.at:.3f},{b.at + b.duration:.3f})':eof_action=pass[o{k}]"
        )
        current = f"o{k}"

    audio_label = "ac"
    if o.music is not None:
        music_input = next_input
        inputs += ["-stream_loop", "-1", "-i", str(o.music)]
        next_input += 1
        parts.append(
            f"[{music_input}:a]atrim=duration={plan.output_duration:.3f},asetpts=PTS-STARTPTS,"
            f"aresample=48000,volume={o.music_volume}[mus]"
        )
        if o.duck_music:
            parts.append("[ac]asplit[ac1][ac2]")
            parts.append("[mus][ac1]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
            parts.append("[ac2][duck]amix=inputs=2:duration=first:dropout_transition=0[mix]")
        else:
            parts.append("[ac][mus]amix=inputs=2:duration=first:dropout_transition=0[mix]")
        audio_label = "mix"
    parts.append(f"[{audio_label}]loudnorm=I={o.loudness_lufs}:TP=-1.5:LRA=11,aresample=48000[aout]")
    return ";".join(parts), inputs, current, "aout"


def render_vlog(engine: FFmpegEngine, plan: VlogPlan, dest: Path) -> Path:
    if not plan.keeps:
        raise ValueError("nothing left after cuts")
    probe = engine.probe(plan.source)
    has_audio = any(s.codec_type == "audio" for s in probe.streams)
    graph, extra, vlabel, alabel = build_filtergraph(plan, has_audio=has_audio)
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-i",
        str(plan.source),
        *extra,
        "-filter_complex",
        graph,
        "-map",
        f"[{vlabel}]",
        "-map",
        f"[{alabel}]",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    result = engine.run(args, timeout=max(engine.timeout_sec, plan.source_duration * 6))
    engine.ensure_ok(result, "vlog render")
    return dest


def write_plan(plan: VlogPlan, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(plan.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return dest
