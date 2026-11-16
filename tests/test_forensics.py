"""Offline tests for forensics, using synthetic ffmpeg-generated clips."""
import subprocess
from pathlib import Path

import pytest

from rea_video_turbo.forensics import (
    frame_cadence, probe_forensics, sensor_noise, summarize_breakdown,
)


def _ff(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    plain = d / "plain.mp4"
    _ff(["-f", "lavfi", "-i", "testsrc2=size=160x120:rate=24:duration=3", "-pix_fmt", "yuv420p", str(plain)])
    tagged = d / "tagged.mp4"
    _ff(["-f", "lavfi", "-i", "testsrc2=size=160x120:rate=24:duration=2", "-pix_fmt", "yuv420p",
         "-movflags", "use_metadata_tags", "-metadata", "com.apple.quicktime.make=Apple", "-metadata", "com.apple.quicktime.model=iPhone 15",
         "-metadata", "AIGC=true", "-metadata", "software=CapCut 9.0", "-metadata", "creation_time=2026-01-02T03:04:05Z",
         str(tagged)])
    padded = d / "padded.mp4"  # 24fps content in a 30fps container
    _ff(["-f", "lavfi", "-i", "testsrc2=size=160x120:rate=24:duration=3", "-vf", "fps=30", "-pix_fmt", "yuv420p", str(padded)])
    noisy = d / "noisy.mp4"
    _ff(["-f", "lavfi", "-i", "color=gray:size=160x120:rate=24:duration=2", "-vf", "noise=alls=25:allf=t",
         "-c:v", "libx264", "-crf", "5", "-pix_fmt", "yuv420p", str(noisy)])
    clean = d / "clean.mp4"
    _ff(["-f", "lavfi", "-i", "color=gray:size=160x120:rate=24:duration=2", "-c:v", "libx264", "-crf", "5",
         "-pix_fmt", "yuv420p", str(clean)])
    return dict(plain=plain, tagged=tagged, padded=padded, noisy=noisy, clean=clean)


def test_probe_forensics_tags(clips):
    r = probe_forensics(clips["tagged"])
    assert r["device"].get("com.apple.quicktime.make") == "Apple"
    assert any("aigc" in k for k in r["aigc_tags"])
    assert r["editor"] == "CapCut"
    assert r["creation_time"].startswith("2026-01-02")
    assert r["c2pa"] is False
    assert r["clues"]


def test_probe_forensics_plain_is_ffmpeg(clips):
    r = probe_forensics(clips["plain"])
    assert r["device"] == {} and r["aigc_tags"] == {}
    assert r["editor"] and "FFmpeg" in r["editor"]


def test_probe_missing_file():
    with pytest.raises(FileNotFoundError):
        probe_forensics("/nonexistent/x.mp4")


def test_cadence_detects_duplicates(clips):
    native = frame_cadence(clips["plain"])
    padded = frame_cadence(clips["padded"])
    assert native["duplicate_ratio"] < 0.05
    assert 0.1 < padded["duplicate_ratio"] < 0.3
    assert 22 <= padded["effective_fps"] <= 26
    assert "duplicate-frame" in padded["note"]


def test_sensor_noise_ordering(clips):
    n = sensor_noise(clips["noisy"])
    c = sensor_noise(clips["clean"])
    assert n["noise_sigma"] > c["noise_sigma"]
    assert c["level"] == "none"
    assert n["level"] != "none"


def test_summarize_breakdown_flags_low_conf():
    b = {
        "source": {"filename": "a.mp4", "width": 480, "height": 854, "fps": 24.0, "duration": 10.0},
        "summary": {"vlm_model": "heuristic"},
        "shots": [
            {"index": 1, "start": 0, "end": 6, "duration": 6, "vlm": {"label": "live_action", "confidence": 0.95}},
            {"index": 2, "start": 6, "end": 10, "duration": 4, "vlm": {"label": "ai_video", "confidence": 0.5}},
        ],
        "forensics": {"clues": ["Editor/encoder signature: CapCut"]},
    }
    s = summarize_breakdown(b)
    assert "live_action 60%" in s and "ai_video 40%" in s
    assert "#2" in s and "Needs review (1" in s
    assert "CapCut" in s
    assert "Needs review: none" in summarize_breakdown({"shots": []})
