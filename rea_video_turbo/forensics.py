"""Cheap, offline forensic evidence: container metadata, frame cadence, sensor noise, summaries."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np

LOW_CONFIDENCE = 0.7

_DEVICE_KEYS = (
    "com.apple.quicktime.make", "com.apple.quicktime.model", "make", "model",
    "com.android.manufacturer", "com.android.model", "com.apple.quicktime.software",
)
_AIGC_PATTERN = re.compile(r"aigc|ai[-_ ]?generated|generated[-_ ]?by[-_ ]?ai|synthetic|contentproducer|producerid", re.I)
_C2PA_MARKERS = (b"c2pa", b"jumb", b"cai_", b"contentcredentials")
_EDITORS = {
    "capcut": "CapCut", "jianying": "Jianying", "premiere": "Adobe Premiere", "final cut": "Final Cut Pro",
    "davinci": "DaVinci Resolve", "resolve": "DaVinci Resolve", "vegas": "Vegas", "imovie": "iMovie",
    "kdenlive": "Kdenlive", "remotion": "Remotion", "lavf": "FFmpeg (Lavf)", "lavc": "FFmpeg (libavcodec)",
    "handbrake": "HandBrake", "after effects": "After Effects", "kinemaster": "KineMaster",
}


def _ffprobe(path: Path) -> dict[str, Any]:
    cmd = ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(res.stdout or "{}")


def _collect_tags(info: dict[str, Any]) -> dict[str, str]:
    tags: dict[str, str] = {}
    for src in [info.get("format", {})] + list(info.get("streams", [])):
        for k, v in (src.get("tags") or {}).items():
            tags.setdefault(str(k).lower(), str(v))
    return tags


def probe_forensics(video_path: str | Path) -> dict[str, Any]:
    """Return metadata clues about how a video was made.

    Keys: device, aigc_tags, c2pa, editor, encoder, creation_time, tags, clues (human-readable list).
    """
    p = Path(video_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Video file not found: {p}")
    info = _ffprobe(p)
    tags = _collect_tags(info)

    device = {k: tags[k] for k in _DEVICE_KEYS if k in tags}
    aigc = {k: v for k, v in tags.items() if _AIGC_PATTERN.search(k) or _AIGC_PATTERN.search(v)}

    # C2PA / JUMBF: scan head and tail of file for manifest markers.
    c2pa = False
    try:
        size = p.stat().st_size
        with open(p, "rb") as f:
            blob = f.read(2_000_000)
            if size > 2_000_000:
                f.seek(max(0, size - 2_000_000))
                blob += f.read(2_000_000)
        low = blob.lower()
        c2pa = any(m in low for m in _C2PA_MARKERS) and (b"c2pa" in low or b"contentcredentials" in low)
    except OSError:
        pass

    encoder_raw = tags.get("encoder") or tags.get("software") or tags.get("com.apple.quicktime.software") or ""
    for s in info.get("streams", []):
        enc = (s.get("tags") or {}).get("encoder")
        if enc and not encoder_raw:
            encoder_raw = str(enc)
    handler = " ".join((s.get("tags") or {}).get("handler_name", "") for s in info.get("streams", []))
    hay = f"{encoder_raw} {handler} {tags.get('comment', '')} {tags.get('title', '')}".lower()
    alltags = " ".join(tags.values()).lower()
    generic = ("lavf", "lavc")
    editor = next((n for k, n in _EDITORS.items() if k not in generic and (k in hay or k in alltags)), None)
    if editor is None:
        editor = next((n for k, n in _EDITORS.items() if k in generic and k in hay), None)

    out = {
        "device": device,
        "aigc_tags": aigc,
        "c2pa": c2pa,
        "editor": editor,
        "encoder": encoder_raw or None,
        "creation_time": tags.get("creation_time"),
        "tags": tags,
    }
    clues: list[str] = []
    if device:
        clues.append("Capture-device tags present (" + ", ".join(f"{k}={v}" for k, v in device.items()) + ") -> likely camera/phone origin")
    if aigc:
        clues.append("AIGC label tags present: " + ", ".join(aigc))
    if c2pa:
        clues.append("C2PA/Content Credentials manifest markers found")
    if editor:
        clues.append(f"Editor/encoder signature: {editor}")
    out["clues"] = clues
    return out


def _read_gray_frames(video_path: str | Path, start: float, end: float, max_frames: int) -> tuple[list[np.ndarray], float]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(round(start * fps))))
    last = int(round(end * fps))
    frames: list[np.ndarray] = []
    idx = int(round(start * fps))
    while idx < last and len(frames) < max_frames:
        ok, fr = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY))
        idx += 1
    cap.release()
    return frames, fps


def frame_cadence(video_path: str | Path, start: float = 0.0, end: float | None = None,
                  max_frames: int = 240) -> dict[str, Any]:
    """Detect duplicate-frame patterns (e.g. 24fps source padded into a 30fps container).

    Returns container_fps, duplicate_ratio, effective_fps, and a note.
    """
    if end is None:
        cap = cv2.VideoCapture(str(video_path))
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        f = cap.get(cv2.CAP_PROP_FPS) or 24.0
        cap.release()
        end = n / f
    frames, fps = _read_gray_frames(video_path, start, end, max_frames)
    if len(frames) < 3:
        return {"container_fps": round(fps, 3), "duplicate_ratio": 0.0, "effective_fps": round(fps, 3), "note": "too few frames"}
    diffs = np.array([float(np.mean(cv2.absdiff(frames[i], frames[i + 1]))) for i in range(len(frames) - 1)])
    # a "duplicate" transition is far below the median motion level
    thr = max(0.35, float(np.median(diffs)) * 0.1)
    dup = diffs < thr
    # Static content gives all-duplicate; require motion elsewhere to call it cadence.
    ratio = float(dup.mean())
    if ratio > 0.9:
        return {"container_fps": round(fps, 3), "duplicate_ratio": round(ratio, 3), "effective_fps": round(fps, 3), "note": "static content, cadence inconclusive"}
    effective = fps * (1.0 - ratio)
    note = "native cadence"
    if ratio > 0.1:
        note = f"duplicate-frame pattern: ~{effective:.1f}fps source inside {fps:g}fps container"
    return {"container_fps": round(fps, 3), "duplicate_ratio": round(ratio, 3), "effective_fps": round(effective, 3), "note": note}


def sensor_noise(video_path: str | Path, start: float = 0.0, end: float | None = None,
                 max_frames: int = 12) -> dict[str, Any]:
    """Estimate fine-grain noise (std of the high-pass residual in flat regions) and temporal noise independence.

    Real sensors give noise that is non-zero and uncorrelated between frames; clean synthetic/AI video is low-noise or smooth.
    """
    if end is None:
        cap = cv2.VideoCapture(str(video_path))
        end = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 24.0)
        cap.release()
    frames, _ = _read_gray_frames(video_path, start, end, max_frames)
    if not frames:
        return {"noise_sigma": 0.0, "temporal_sigma": 0.0, "level": "unknown"}
    sigmas = []
    for fr in frames:
        f = fr.astype(np.float32)
        resid = f - cv2.GaussianBlur(f, (0, 0), 1.5)
        gx = cv2.Sobel(f, cv2.CV_32F, 1, 0)
        gy = cv2.Sobel(f, cv2.CV_32F, 0, 1)
        grad = np.hypot(gx, gy)
        flat = grad < np.percentile(grad, 40)
        vals = resid[flat]
        # robust sigma via MAD
        sigmas.append(1.4826 * float(np.median(np.abs(vals - np.median(vals)))) if vals.size else 0.0)
    spatial = float(np.mean(sigmas))
    temporal = 0.0
    if len(frames) >= 2:
        d = [float(np.std(frames[i + 1].astype(np.float32) - frames[i].astype(np.float32))) for i in range(len(frames) - 1)]
        temporal = float(np.mean(d))
    level = "none" if spatial < 0.4 else "low" if spatial < 1.2 else "sensor-like"
    return {"noise_sigma": round(spatial, 3), "temporal_sigma": round(temporal, 3), "level": level}


def shot_evidence(video_path: str | Path, shot: dict[str, Any]) -> dict[str, Any]:
    """Cadence + noise evidence for one shot dict (needs `start`/`end`)."""
    s, e = float(shot.get("start", 0.0)), float(shot.get("end", 0.0)) or None
    return {"cadence": frame_cadence(video_path, s, e), "noise": sensor_noise(video_path, s, e)}


def summarize_breakdown(breakdown: dict[str, Any], low_confidence: float = LOW_CONFIDENCE) -> str:
    """Compact text conclusion for a breakdown dict; flags low-confidence shots."""
    src = breakdown.get("source", {}) or {}
    shots = breakdown.get("shots", []) or []
    summ = breakdown.get("summary", {}) or {}
    total_dur = sum(float(s.get("duration", 0) or 0) for s in shots) or 1e-9

    by_label: dict[str, float] = {}
    flagged: list[str] = []
    for sh in shots:
        v = sh.get("vlm") or {}
        lbl = v.get("label") or sh.get("label") or "unknown"
        by_label[lbl] = by_label.get(lbl, 0.0) + float(sh.get("duration", 0) or 0)
        conf = v.get("confidence")
        if conf is not None and float(conf) < low_confidence:
            flagged.append(f"#{sh.get('index', '?')} {float(sh.get('start', 0)):.1f}-{float(sh.get('end', 0)):.1f}s "
                           f"{lbl} (conf {float(conf):.2f})")

    mix = ", ".join(f"{k} {100 * d / total_dur:.0f}%" for k, d in sorted(by_label.items(), key=lambda kv: -kv[1]))
    lines = [
        f"Source: {src.get('filename', '?')} | {src.get('width', '?')}x{src.get('height', '?')} | "
        f"{src.get('fps', '?')}fps | {src.get('duration', '?')}s",
        f"Conclusion: {mix or 'no shots'} across {len(shots)} shot(s)",
        f"Analyzer: {summ.get('vlm_model', 'unknown')}",
    ]
    forensic = breakdown.get("forensics") or {}
    for c in forensic.get("clues", []):
        lines.append(f"Metadata: {c}")
    if flagged:
        lines.append(f"Needs review ({len(flagged)} low-confidence shot(s), conf < {low_confidence}):")
        lines += [f"  - {f}" for f in flagged]
    else:
        lines.append("Needs review: none")
    return "\n".join(lines)
