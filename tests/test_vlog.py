from pathlib import Path

import pytest

from dt_video.media.engine import FFmpegEngine
from dt_video.media.ops import generate_synthetic_audio, generate_synthetic_video
from dt_video.vlog import (
    VlogOptions,
    join_points,
    keep_ranges,
    merge_ranges,
    pad_cuts,
    place_broll,
    plan_vlog,
    render_vlog,
)


def test_merge_and_keep_ranges() -> None:
    assert merge_ranges([(5, 6), (1, 2), (1.5, 3)], 10) == [(1, 3), (5, 6)]
    assert keep_ranges(10, [(1, 3), (5, 6)]) == [(0, 1), (3, 5), (6, 10)]
    assert keep_ranges(10, [(0, 10)]) == []
    assert keep_ranges(10, [(0.1, 9.9)]) == []


def test_pad_cuts_drops_short() -> None:
    assert pad_cuts([(1.0, 3.0), (5.0, 5.4)], 0.25) == [(1.25, 2.75)]


def test_join_points_and_broll_placement() -> None:
    keeps = [(0, 4), (6, 10), (12, 20)]
    assert join_points(keeps) == [4, 8]
    clips = [(Path("a.mp4"), 5.0)]
    placed = place_broll(clips, [4, 8], 16, 2.5)
    assert [(p.at, p.duration) for p in placed] == [(2.75, 2.5), (6.75, 2.5)]
    assert place_broll([], [4], 16, 2.5) == []
    # never overlaps the previous overlay
    tight = place_broll(clips, [4, 5], 16, 2.5)
    assert tight[1].at >= tight[0].at + tight[0].duration


@pytest.mark.requires_ffmpeg
def test_vlog_end_to_end(tmp_path: Path) -> None:
    engine = FFmpegEngine()
    if not engine.available():
        pytest.skip("ffmpeg missing")
    src = generate_synthetic_video(engine, tmp_path / "src.mp4", duration=6.0)
    broll_dir = tmp_path / "broll"
    generate_synthetic_video(engine, broll_dir / "b1.mp4", duration=3.0, with_audio=False)
    music = generate_synthetic_audio(engine, tmp_path / "music.wav", duration=2.0, frequency=220)
    options = VlogOptions(manual_cuts=[(2.0, 3.5)], broll_dir=broll_dir, music=music, width=640, height=360, fps=15)
    plan = plan_vlog(engine, src, options)
    assert plan.keeps == [(0.0, 2.0), (3.5, 6.0)]
    assert len(plan.broll) == 1
    out = render_vlog(engine, plan, tmp_path / "out" / "vlog.mp4")
    probe = engine.probe(out)
    assert abs(probe.duration - 4.5) < 0.6
    assert any(s.codec_type == "audio" for s in probe.streams)
    video = next(s for s in probe.streams if s.codec_type == "video")
    assert (video.width, video.height) == (640, 360)
