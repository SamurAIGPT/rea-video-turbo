"""Tests for video metadata probing and detector."""
from pathlib import Path
from muapi_video_reverse.detector import probe_video, detect_shots


def test_probe_sample_video():
    sample = Path("rea-video/docs/cases/videos/dual_role.mp4")
    if not sample.is_file():
        return
    meta = probe_video(sample)
    assert meta["width"] == 480
    assert meta["height"] == 854
    assert meta["fps"] == 24.0
    assert meta["aspect_ratio"] == "9:16"
    assert meta["duration"] > 18.0
