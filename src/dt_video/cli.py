"""Typer CLI with human and JSON output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from dt_video.__version__ import __version__
from dt_video.capabilities.pipeline import (
    MetricsImportRequest,
    MetricsImportTool,
    ReviewActionRequest,
)
from dt_video.capabilities.support import ToolRunner
from dt_video.domain.enums import ContentProfile, PipelineStage
from dt_video.domain.models import ProjectConfig, ReviewManifest
from dt_video.media.engine import FFmpegEngine
from dt_video.media.ops import (
    extract_audio,
    generate_synthetic_audio,
    generate_synthetic_video,
    slice_media,
)
from dt_video.settings import load_project_config
from dt_video.store import ArtifactStore
from dt_video.vlog import VlogOptions, plan_vlog, render_vlog, write_plan
from dt_video.workflows.runner import WorkflowRunner

app = typer.Typer(no_args_is_help=True, help="dt-video creator flywheel")
project_app = typer.Typer(no_args_is_help=True)
review_app = typer.Typer(no_args_is_help=True)
media_app = typer.Typer(no_args_is_help=True)
metrics_app = typer.Typer(no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(review_app, name="review")
app.add_typer(media_app, name="media")
app.add_typer(metrics_app, name="metrics")

console = Console()
err_console = Console(stderr=True)


def _emit(as_json: bool, payload: Any, message: str) -> None:
    if as_json:
        if hasattr(payload, "model_dump"):
            data = payload.model_dump(mode="json")
        else:
            data = payload
        console.print_json(json.dumps({"ok": True, "message": message, "data": data}, default=str))
    else:
        console.print(message)
        if payload is not None and not isinstance(payload, str):
            console.print(payload)


def _workspace(explicit: Path | None) -> Path:
    if explicit:
        return explicit.resolve()
    return load_project_config().workspace.resolve()


@app.callback()
def root(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON"),
) -> None:
    ctx.obj = {"json": json_output}


@app.command()
def version() -> None:
    """Print version."""
    console.print(__version__)


@app.command()
def doctor(
    ctx: typer.Context,
    workspace: Path | None = typer.Option(None, "--workspace"),
) -> None:
    """Check ffmpeg, workspace, and config."""
    engine = FFmpegEngine()
    cfg = load_project_config()
    payload = {
        "version": __version__,
        "ffmpeg": engine.ffmpeg_bin,
        "ffprobe": engine.ffprobe_bin,
        "available": engine.available(),
        "workspace": str(_workspace(workspace)),
        "transcription_provider": cfg.transcription_provider,
        "analysis_provider": cfg.analysis_provider,
    }
    _emit(ctx.obj["json"], payload, "doctor")
    raise typer.Exit(0 if engine.available() else 2)


@project_app.command("init")
def project_init(
    ctx: typer.Context,
    name: str = typer.Option("studio", "--name"),
    workspace: Path = typer.Option(Path("workspace"), "--workspace"),
) -> None:
    """Write dt_video.toml and create the workspace."""
    workspace.mkdir(parents=True, exist_ok=True)
    toml_path = Path("dt_video.toml")
    toml_path.write_text(
        f'[project]\nname = "{name}"\nworkspace = "{workspace}"\n'
        'default_profile = "talking-head"\ntranscription_provider = "fake"\n',
        encoding="utf-8",
    )
    ArtifactStore(load_project_config(toml_path))
    _emit(ctx.obj["json"], {"config": str(toml_path), "workspace": str(workspace)}, "Initialized project")


@app.command()
def ingest(
    ctx: typer.Context,
    source: Path = typer.Argument(..., exists=True, readable=True),
    profile: ContentProfile = typer.Option(ContentProfile.TALKING_HEAD, "--profile"),
    title: str | None = typer.Option(None, "--title"),
    workspace: Path | None = typer.Option(None, "--workspace"),
) -> None:
    """Ingest a recording into an episode workspace."""
    runner = WorkflowRunner(_workspace(workspace))
    result = runner.ingest(source, profile, title)
    if result.status != "success":
        err_console.print(result.human_message)
        raise typer.Exit(1)
    _emit(ctx.obj["json"], result.data, result.human_message)


@app.command()
def run(
    ctx: typer.Context,
    episode_id: str,
    until: PipelineStage = typer.Option(PipelineStage.ANALYZE, "--until"),
    workspace: Path | None = typer.Option(None, "--workspace"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Run the pipeline up to a stage. Stops at review until moments are approved."""
    runner = WorkflowRunner(_workspace(workspace))
    results = runner.run_until(episode_id, until, force=force)
    payload = [{"status": r.status, "message": r.human_message} for r in results]
    failed = any(r.status == "error" for r in results)
    _emit(ctx.obj["json"], payload, "pipeline")
    raise typer.Exit(1 if failed else 0)


@app.command()
def transcribe(
    ctx: typer.Context,
    episode_id: str,
    workspace: Path | None = typer.Option(None, "--workspace"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    runner = WorkflowRunner(_workspace(workspace))
    result = runner.run_stage(episode_id, PipelineStage.TRANSCRIBE, force=force)
    _emit(ctx.obj["json"], result.data, result.human_message)
    raise typer.Exit(0 if result.status != "error" else 1)


@app.command()
def analyze(
    ctx: typer.Context,
    episode_id: str,
    workspace: Path | None = typer.Option(None, "--workspace"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    runner = WorkflowRunner(_workspace(workspace))
    result = runner.run_stage(episode_id, PipelineStage.ANALYZE, force=force)
    _emit(ctx.obj["json"], result.data, result.human_message)
    raise typer.Exit(0 if result.status != "error" else 1)


@review_app.command("list")
def review_list(
    ctx: typer.Context,
    episode_id: str,
    workspace: Path | None = typer.Option(None, "--workspace"),
) -> None:
    store = ArtifactStore(ProjectConfig(workspace=_workspace(workspace)))
    review = ReviewManifest.model_validate(store.read_json(episode_id, PipelineStage.REVIEW, "review.json"))
    if ctx.obj["json"]:
        _emit(True, review, "review")
        return
    table = Table(title=f"Moments for {episode_id}")
    table.add_column("id")
    table.add_column("status")
    table.add_column("start")
    table.add_column("end")
    table.add_column("score")
    table.add_column("hook")
    for moment in review.moments:
        table.add_row(
            moment.moment_id,
            moment.status.value,
            f"{moment.start:.1f}",
            f"{moment.end:.1f}",
            f"{moment.scores.total:.2f}",
            moment.hook[:60],
        )
    console.print(table)


@review_app.command("approve")
def review_approve(
    ctx: typer.Context,
    episode_id: str,
    moment_id: str,
    workspace: Path | None = typer.Option(None, "--workspace"),
    notes: str = typer.Option("", "--notes"),
    start: float | None = typer.Option(None, "--start"),
    end: float | None = typer.Option(None, "--end"),
) -> None:
    from dt_video.capabilities.pipeline import ReviewApproveTool

    result = ToolRunner().run(
        ReviewApproveTool(),
        ReviewActionRequest(
            episode_id=episode_id,
            workspace=_workspace(workspace),
            moment_id=moment_id,
            notes=notes,
            start=start,
            end=end,
        ),
        _workspace(workspace),
    )
    _emit(ctx.obj["json"], result.data, result.human_message)
    raise typer.Exit(0 if result.status != "error" else 1)


@review_app.command("reject")
def review_reject(
    ctx: typer.Context,
    episode_id: str,
    moment_id: str,
    workspace: Path | None = typer.Option(None, "--workspace"),
    notes: str = typer.Option("", "--notes"),
) -> None:
    from dt_video.capabilities.pipeline import ReviewRejectTool

    result = ToolRunner().run(
        ReviewRejectTool(),
        ReviewActionRequest(
            episode_id=episode_id,
            workspace=_workspace(workspace),
            moment_id=moment_id,
            notes=notes,
        ),
        _workspace(workspace),
    )
    _emit(ctx.obj["json"], result.data, result.human_message)
    raise typer.Exit(0 if result.status != "error" else 1)


@app.command()
def compose(
    ctx: typer.Context,
    episode_id: str,
    workspace: Path | None = typer.Option(None, "--workspace"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    runner = WorkflowRunner(_workspace(workspace))
    result = runner.run_stage(episode_id, PipelineStage.COMPOSE, force=force)
    _emit(ctx.obj["json"], result.data, result.human_message)
    raise typer.Exit(0 if result.status != "error" else 1)


@app.command()
def package(
    ctx: typer.Context,
    episode_id: str,
    workspace: Path | None = typer.Option(None, "--workspace"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    runner = WorkflowRunner(_workspace(workspace))
    result = runner.run_stage(episode_id, PipelineStage.PACKAGE, force=force)
    _emit(ctx.obj["json"], result.data, result.human_message)
    raise typer.Exit(0 if result.status != "error" else 1)


@media_app.command("probe")
def media_probe(
    ctx: typer.Context,
    source: Path = typer.Argument(..., exists=True),
) -> None:
    engine = FFmpegEngine()
    result = engine.probe(source)
    _emit(ctx.obj["json"], result, f"{source} duration={result.duration:.2f}s")


@media_app.command("extract-audio")
def media_extract_audio(
    ctx: typer.Context,
    source: Path,
    dest: Path,
) -> None:
    path = extract_audio(FFmpegEngine(), source, dest)
    _emit(ctx.obj["json"], {"output": str(path)}, str(path))


@media_app.command("slice")
def media_slice(
    ctx: typer.Context,
    source: Path,
    dest: Path,
    start: float = typer.Option(..., "--start"),
    end: float = typer.Option(..., "--end"),
) -> None:
    path = slice_media(FFmpegEngine(), source, dest, start, end, reencode=True)
    _emit(ctx.obj["json"], {"output": str(path)}, str(path))


@media_app.command("synth")
def media_synth(
    ctx: typer.Context,
    dest: Path,
    kind: str = typer.Option("video", "--kind"),
    duration: float = typer.Option(4.0, "--duration"),
) -> None:
    engine = FFmpegEngine()
    if kind == "audio":
        path = generate_synthetic_audio(engine, dest, duration=duration)
    else:
        path = generate_synthetic_video(engine, dest, duration=duration)
    _emit(ctx.obj["json"], {"output": str(path)}, str(path))


def _parse_cut(value: str) -> tuple[float, float]:
    try:
        start, end = value.split(":", 1)
        return float(start), float(end)
    except ValueError as exc:
        raise typer.BadParameter(f"expected START:END in seconds, got {value!r}") from exc


@app.command("vlog")
def vlog(
    ctx: typer.Context,
    source: Path = typer.Argument(..., exists=True, dir_okay=False, help="Location recording (e.g. Osmo Pocket 3)."),
    dest: Path = typer.Argument(..., help="YouTube-ready .mp4 to write."),
    broll_dir: Path | None = typer.Option(None, "--broll-dir", help="Folder of b-roll clips to cover jump cuts."),
    music: Path | None = typer.Option(None, "--music", exists=True, dir_okay=False, help="Background music file."),
    music_volume: float = typer.Option(0.18, "--music-volume"),
    min_silence: float = typer.Option(1.0, "--min-silence", help="Cut silences at least this many seconds."),
    cut: list[str] = typer.Option([], "--cut", help="Extra range to remove, START:END seconds. Repeatable."),
    polish: bool = typer.Option(True, "--polish/--no-polish", help="Colour lift, sharpen, fades."),
    width: int = typer.Option(1920, "--width"),
    height: int = typer.Option(1080, "--height"),
    fps: int = typer.Option(30, "--fps"),
    plan_only: bool = typer.Option(False, "--plan-only", help="Write the edit plan JSON and stop."),
) -> None:
    """Turn a location recording into a YouTube-ready video: cut, b-roll, music, polish."""
    engine = FFmpegEngine()
    options = VlogOptions(
        min_silence_sec=min_silence,
        manual_cuts=[_parse_cut(c) for c in cut],
        broll_dir=broll_dir,
        music=music,
        music_volume=music_volume,
        polish=polish,
        width=width,
        height=height,
        fps=fps,
    )
    plan = plan_vlog(engine, source, options)
    plan_path = write_plan(plan, dest.with_suffix(".plan.json"))
    summary = {
        "plan": str(plan_path),
        "source_seconds": round(plan.source_duration, 2),
        "output_seconds": round(plan.output_duration, 2),
        "cuts": len(plan.cuts),
        "broll": len(plan.broll),
    }
    if plan_only:
        _emit(ctx.obj["json"], summary, f"plan written: {plan_path}")
        return
    path = render_vlog(engine, plan, dest)
    _emit(ctx.obj["json"], {**summary, "output": str(path)}, str(path))


@metrics_app.command("import")
def metrics_import(
    ctx: typer.Context,
    episode_id: str,
    path: Path,
    workspace: Path | None = typer.Option(None, "--workspace"),
) -> None:
    result = ToolRunner().run(
        MetricsImportTool(),
        MetricsImportRequest(episode_id=episode_id, workspace=_workspace(workspace), path=path),
        _workspace(workspace),
    )
    _emit(ctx.obj["json"], result.data, result.human_message)
    raise typer.Exit(0 if result.status != "error" else 1)


def main() -> None:
    app()
