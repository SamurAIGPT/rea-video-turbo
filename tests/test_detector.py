"""Tests for video metadata probing and shot detection."""
import subprocess

import pytest

from rea_video_turbo.detector import detect_shots, probe_video


@pytest.fixture
def clip(tmp_path):
    path = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=d=2:s=320x568:r=24", str(path)],
        check=True,
    )
    return path


def test_probe_video(clip):
    meta = probe_video(clip)
    assert meta["width"] == 320
    assert meta["height"] == 568
    assert meta["fps"] == 24.0
    assert 1.5 < meta["duration"] < 2.5


def test_detect_shots_single_shot(clip, tmp_path):
    shots = detect_shots(clip, tmp_path / "out")
    assert len(shots) == 1
    assert shots[0]["index"] == 1
