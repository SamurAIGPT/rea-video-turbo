"""Offline tests for rea_video_turbo.audio using synthetic audio."""
import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from rea_video_turbo import audio

SR = 22050


def _write(path: Path, x: np.ndarray) -> Path:
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


def _click_track(bpm: float, seconds: float = 12.0) -> np.ndarray:
    x = np.zeros(int(SR * seconds), dtype=np.float32)
    step = 60.0 / bpm
    t = 0.5
    burst = np.random.default_rng(0).standard_normal(400).astype(np.float32) * np.hanning(400)
    while t < seconds - 0.1:
        i = int(t * SR)
        x[i:i + 400] += burst * 0.9
        t += step
    return x


@pytest.mark.parametrize("bpm", [100, 120, 140])
def test_estimate_bpm_click_track(tmp_path, bpm):
    wav = _write(tmp_path / "clicks.wav", _click_track(bpm))
    res = audio.estimate_bpm(wav)
    assert res["bpm"] is not None
    assert abs(res["bpm"] - bpm) <= 3
    assert res["confidence"] > 0.2


def test_estimate_bpm_silence(tmp_path):
    wav = _write(tmp_path / "s.wav", np.zeros(SR * 3, dtype=np.float32))
    assert audio.estimate_bpm(wav)["bpm"] is None


def test_detect_sfx_candidates_finds_hits_and_clips(tmp_path):
    x = np.zeros(SR * 6, dtype=np.float32)
    burst = np.random.default_rng(1).standard_normal(600).astype(np.float32) * np.hanning(600)
    times = [1.0, 2.5, 4.2]
    for t in times:
        i = int(t * SR)
        x[i:i + 600] += burst
    wav = _write(tmp_path / "hits.wav", x)
    hits = audio.detect_sfx_candidates(wav, out_dir=tmp_path)
    assert len(hits) == 3
    for h, t in zip(hits, times):
        assert abs(h["time"] - t) < 0.1
        assert Path(h["clip"]).exists()
    assert audio.detect_sfx_candidates(wav) [0]["clip"] is None


def test_classify_speech_vs_music_vs_silence(tmp_path):
    rng = np.random.default_rng(2)
    n = SR * 2
    t = np.arange(n) / SR
    # music-like: steady chord
    music = sum(np.sin(2 * np.pi * f * t) for f in (220, 277.2, 329.6, 440)) * 0.15
    # speech-like: noise/harmonics gated at ~4 Hz syllable rate with pauses
    carrier = np.sin(2 * np.pi * 140 * t) + 0.5 * np.sin(2 * np.pi * 700 * t) + 0.2 * rng.standard_normal(n)
    gate = (np.sin(2 * np.pi * 3.5 * t) > 0.2).astype(np.float32)
    gate = np.convolve(gate, np.ones(200) / 200, mode="same")
    speech = carrier * gate * 0.3
    silence = np.zeros(n)
    x = np.concatenate([music, speech, silence]).astype(np.float32)
    wav = _write(tmp_path / "mix.wav", x)
    segs = audio.classify_segments(wav)
    labels = [s["label"] for s in segs]
    assert labels == ["music", "speech", "silence"]


def test_analyze_audio_no_track(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg missing")
    vid = tmp_path / "silent.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1",
                    "-pix_fmt", "yuv420p", str(vid)], check=True)
    res = audio.analyze_audio(vid, tmp_path / "out")
    assert res["has_audio"] is False
    assert res["stems"]["status"] == "unavailable"
    json.dumps(res)


def test_analyze_audio_with_track_is_json_serializable(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg missing")
    wav = _write(tmp_path / "c.wav", _click_track(120, 8.0))
    vid = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=8",
                    "-i", str(wav), "-shortest", "-pix_fmt", "yuv420p", str(vid)], check=True)
    res = audio.analyze_audio(vid, tmp_path / "out")
    assert res["has_audio"] is True
    assert abs(res["bpm"] - 120) <= 3
    assert len(res["sfx"]) >= 8
    assert res["stems"]["status"] in {"unavailable", "ok", "failed"}
    json.dumps(res)
