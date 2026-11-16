"""Lightweight, offline audio analysis: extraction, tempo, sound-effect hits, speech/music.

Everything here uses ffmpeg + numpy only. Stem separation is optional and only runs
when ``demucs`` is installed; otherwise it is reported as unavailable.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any

import numpy as np

SAMPLE_RATE = 22050
N_FFT = 1024
HOP = 512


# --------------------------------------------------------------------------- IO

def has_audio_stream(video_path: str | Path) -> bool:
    """True if the file contains at least one audio stream."""
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=index", "-of", "json", str(video_path)],
            capture_output=True, text=True, check=True,
        )
        return bool(json.loads(res.stdout or "{}").get("streams"))
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return False


def extract_audio(video_path: str | Path, out_dir: str | Path, sr: int = SAMPLE_RATE) -> Path | None:
    """Extract mono 16-bit PCM wav to ``out_dir/original.wav``. Returns None if no audio track."""
    if not has_audio_stream(video_path):
        return None
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    wav_path = out / "original.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(video_path), "-vn", "-ac", "1",
             "-ar", str(sr), "-c:a", "pcm_s16le", str(wav_path)],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return wav_path if wav_path.exists() and wav_path.stat().st_size > 44 else None


def load_wav(wav_path: str | Path) -> tuple[np.ndarray, int]:
    """Load a PCM wav as float32 mono in [-1, 1]."""
    with wave.open(str(wav_path), "rb") as w:
        sr, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {width}")
    if ch > 1:
        x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    return x, sr


def _write_wav(path: Path, x: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# --------------------------------------------------------------------- features

def _stft_mag(x: np.ndarray) -> np.ndarray:
    """Magnitude spectrogram, shape (frames, bins)."""
    if len(x) < N_FFT:
        x = np.pad(x, (0, N_FFT - len(x)))
    n_frames = 1 + (len(x) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    frames = x[idx] * np.hanning(N_FFT)[None, :]
    return np.abs(np.fft.rfft(frames, axis=1))


def onset_envelope(x: np.ndarray) -> np.ndarray:
    """Positive spectral flux on log-compressed magnitudes."""
    mag = np.log1p(10.0 * _stft_mag(x))
    flux = np.maximum(mag[1:] - mag[:-1], 0).sum(axis=1)
    return np.concatenate([[0.0], flux]).astype(np.float64)


def estimate_bpm(wav_path: str | Path, min_bpm: float = 60.0, max_bpm: float = 200.0) -> dict[str, Any]:
    """Tempo by autocorrelation of the onset envelope.

    Returns ``{"bpm": float | None, "confidence": float}``; confidence is the normalized
    autocorrelation peak (0..1). Weakly biased towards ~120 BPM to pick between octaves.
    """
    x, sr = load_wav(wav_path)
    env = onset_envelope(x)
    if len(env) < 8 or env.std() < 1e-9:
        return {"bpm": None, "confidence": 0.0}
    env = env - env.mean()
    ac = np.correlate(env, env, mode="full")[len(env) - 1:]
    if ac[0] <= 0:
        return {"bpm": None, "confidence": 0.0}
    ac = ac / ac[0]
    fps = sr / HOP
    lags = np.arange(len(ac))
    bpms = 60.0 * fps / np.maximum(lags, 1)
    mask = (bpms >= min_bpm) & (bpms <= max_bpm) & (lags > 0)
    if not mask.any():
        return {"bpm": None, "confidence": 0.0}
    prior = np.exp(-0.5 * (np.log2(bpms[mask] / 120.0) / 0.9) ** 2)
    scores = ac[mask] * prior
    best = int(np.argmax(scores))
    lag = lags[mask][best]
    # parabolic refinement of the lag
    if 1 <= lag < len(ac) - 1:
        a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
        denom = a - 2 * b + c
        if abs(denom) > 1e-12:
            lag = lag + 0.5 * (a - c) / denom
    bpm = 60.0 * fps / float(lag)
    conf = float(np.clip(ac[lags[mask][best]], 0.0, 1.0))
    return {"bpm": round(float(bpm), 1), "confidence": round(conf, 3)}


def detect_sfx_candidates(
    wav_path: str | Path,
    out_dir: str | Path | None = None,
    max_hits: int = 40,
    min_gap_sec: float = 0.15,
    clip_sec: float = 1.0,
    sensitivity: float = 6.0,
) -> list[dict[str, Any]]:
    """Find sharp transients (hits, impacts, clicks) from the onset envelope.

    If ``out_dir`` is given, a short clip per hit is written to ``out_dir/sfx/sfx_NN.wav``.
    Returns ``[{"time": sec, "strength": float, "clip": path | None}]`` sorted by time.
    """
    x, sr = load_wav(wav_path)
    env = onset_envelope(x)
    if len(env) < 4:
        return []
    med = float(np.median(env))
    mad = float(np.median(np.abs(env - med))) + 1e-9
    thresh = med + sensitivity * 1.4826 * mad
    floor = 0.05 * float(env.max())
    thresh = max(thresh, floor)
    fps = sr / HOP
    min_gap = max(1, int(min_gap_sec * fps))
    peaks: list[int] = []
    for i in range(1, len(env) - 1):
        if env[i] >= thresh and env[i] >= env[i - 1] and env[i] > env[i + 1]:
            if peaks and i - peaks[-1] < min_gap:
                if env[i] > env[peaks[-1]]:
                    peaks[-1] = i
                continue
            peaks.append(i)
    if len(peaks) > max_hits:
        keep = sorted(sorted(peaks, key=lambda p: env[p], reverse=True)[:max_hits])
        peaks = keep
    hits: list[dict[str, Any]] = []
    sfx_dir = Path(out_dir) / "sfx" if out_dir is not None else None
    for n, p in enumerate(peaks, 1):
        t = p * HOP / sr
        clip = None
        if sfx_dir is not None:
            s0 = max(0, int((t - 0.05) * sr))
            s1 = min(len(x), s0 + int(clip_sec * sr))
            clip_path = sfx_dir / f"sfx_{n:02d}.wav"
            _write_wav(clip_path, x[s0:s1], sr)
            clip = str(clip_path)
        hits.append({"time": round(float(t), 3), "strength": round(float(env[p]), 3), "clip": clip})
    return hits


def classify_segments(wav_path: str | Path, seg_sec: float = 2.0) -> list[dict[str, Any]]:
    """Coarse per-segment label: ``silence`` | ``speech`` | ``music``.

    Heuristic: speech has strong syllabic (2-8 Hz) amplitude modulation and many
    low-energy gaps; music is steadier and more tonal. It is a rough guide, not a model.
    """
    x, sr = load_wav(wav_path)
    seg_len = int(seg_sec * sr)
    out: list[dict[str, Any]] = []
    if len(x) == 0:
        return out
    for start in range(0, len(x), seg_len):
        seg = x[start:start + seg_len]
        if len(seg) < sr // 4:
            break
        t0, t1 = start / sr, (start + len(seg)) / sr
        rms = float(np.sqrt(np.mean(seg ** 2)))
        if rms < 0.003:
            out.append({"start": round(t0, 2), "end": round(t1, 2), "label": "silence", "confidence": 1.0})
            continue
        mag = _stft_mag(seg)
        frame_rms = np.sqrt((mag ** 2).mean(axis=1)) + 1e-9
        fps = sr / HOP
        # syllabic modulation: share of envelope variance in 2-8 Hz
        e = frame_rms / frame_rms.mean()
        e = e - e.mean()
        spec = np.abs(np.fft.rfft(e * np.hanning(len(e)))) ** 2
        freqs = np.fft.rfftfreq(len(e), 1.0 / fps)
        total = spec[1:].sum() + 1e-12
        syl = float(spec[(freqs >= 2.0) & (freqs <= 8.0)].sum() / total)
        mod_depth = float(np.std(frame_rms) / np.mean(frame_rms))
        gap_frac = float(np.mean(frame_rms < 0.3 * np.mean(frame_rms)))
        # tonality: spectral flatness (low = tonal)
        avg = mag.mean(axis=0) + 1e-9
        flatness = float(np.exp(np.mean(np.log(avg))) / np.mean(avg))
        score = 0.0
        score += 1.0 if syl > 0.35 else 0.0
        score += 1.0 if mod_depth > 0.5 else 0.0
        score += 1.0 if gap_frac > 0.1 else 0.0
        score -= 0.5 if flatness < 0.05 else 0.0
        label = "speech" if score >= 2.0 else "music"
        conf = float(np.clip(abs(score - 1.5) / 1.5, 0.0, 1.0))
        out.append({"start": round(t0, 2), "end": round(t1, 2), "label": label, "confidence": round(conf, 2)})
    return out


# ------------------------------------------------------------------------ stems

def separate_stems(wav_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    """Optional vocals/accompaniment split. Only runs when ``demucs`` is installed."""
    if importlib.util.find_spec("demucs") is None:
        return {"status": "unavailable", "reason": "demucs not installed"}
    out = Path(out_dir) / "stems"
    try:
        subprocess.run(
            [sys.executable, "-m", "demucs", "--two-stems=vocals", "-o", str(out), str(wav_path)],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return {"status": "failed", "reason": str(e)[:200]}
    found = sorted(str(p) for p in out.rglob("*.wav"))
    return {"status": "ok", "files": found}


# ---------------------------------------------------------------------- summary

def analyze_audio(video_path: str | Path, out_dir: str | Path, with_stems: bool = False) -> dict[str, Any]:
    """Full audio pass. Always returns a JSON-serializable dict.

    Keys: has_audio, duration, sample_rate, bpm, bpm_confidence, sfx, segments,
    speech_ratio, music_ratio, silence_ratio, stems, wav.
    """
    out = Path(out_dir) / "audio"
    wav = extract_audio(video_path, out)
    if wav is None:
        return {"has_audio": False, "duration": 0.0, "sample_rate": None, "bpm": None,
                "bpm_confidence": 0.0, "sfx": [], "segments": [], "speech_ratio": 0.0,
                "music_ratio": 0.0, "silence_ratio": 0.0,
                "stems": {"status": "unavailable", "reason": "no audio track"}, "wav": None}
    x, sr = load_wav(wav)
    tempo = estimate_bpm(wav)
    segs = classify_segments(wav)
    total = sum(s["end"] - s["start"] for s in segs) or 1.0

    def ratio(label: str) -> float:
        return round(sum(s["end"] - s["start"] for s in segs if s["label"] == label) / total, 3)

    stems = separate_stems(wav, out) if with_stems else {"status": "unavailable", "reason": "not requested"}
    return {
        "has_audio": True,
        "duration": round(len(x) / sr, 3),
        "sample_rate": int(sr),
        "bpm": tempo["bpm"],
        "bpm_confidence": tempo["confidence"],
        "sfx": detect_sfx_candidates(wav, out_dir=out),
        "segments": segs,
        "speech_ratio": ratio("speech"),
        "music_ratio": ratio("music"),
        "silence_ratio": ratio("silence"),
        "stems": stems,
        "wav": str(wav),
    }
