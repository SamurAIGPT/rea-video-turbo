"""Video metadata probing and scene/shot boundary detection using PySceneDetect and OpenCV."""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def probe_video(video_path: str | Path) -> dict[str, Any]:
    """Inspects video file metadata using ffprobe and cv2."""
    p = Path(video_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Video file not found: {p}")

    cap = cv2.VideoCapture(str(p))
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {p}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    duration = total_frames / fps if fps > 0 else 0.0

    # Determine aspect ratio
    aspect_ratio = "16:9"
    if width > 0 and height > 0:
        ratio = width / height
        if 0.5 <= ratio <= 0.65:
            aspect_ratio = "9:16"
        elif 0.9 <= ratio <= 1.1:
            aspect_ratio = "1:1"
        elif 1.6 <= ratio <= 1.9:
            aspect_ratio = "16:9"
        else:
            aspect_ratio = f"{width}:{height}"

    meta = {
        "path": str(p),
        "filename": p.name,
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "total_frames": total_frames,
        "duration": round(duration, 3),
        "aspect_ratio": aspect_ratio,
    }

    # Attempt ffprobe container details if available
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name", "-of", "json", str(p)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(res.stdout)
        streams = info.get("streams", [])
        if streams:
            meta["vcodec"] = streams[0].get("codec_name", "unknown")
    except Exception:
        meta["vcodec"] = "h264"

    return meta


def detect_shots(video_path: str | Path, out_dir: str | Path, min_scene_len_sec: float = 0.5) -> list[dict[str, Any]]:
    """Detects cuts and shots using PySceneDetect (with OpenCV fallback).
    Saves keyframes (first, middle, last) and outputs shot list."""
    p = Path(video_path).resolve()
    out = Path(out_dir).resolve()
    shots_dir = out / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    meta = probe_video(p)
    fps = meta["fps"]
    duration = meta["duration"]

    scenes = []

    # Try PySceneDetect ContentDetector
    try:
        from scenedetect import open_video, SceneManager, ContentDetector
        video = open_video(str(p))
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=27.0, min_scene_len=int(min_scene_len_sec * fps)))
        scene_manager.detect_scenes(video)
        scene_list = scene_manager.get_scene_list()
        for s in scene_list:
            scenes.append((s[0].get_seconds(), s[1].get_seconds()))
    except Exception:
        # Fallback to single shot or naive cuts
        scenes = []

    if not scenes:
        scenes = [(0.0, duration)]

    shots = []
    cap = cv2.VideoCapture(str(p))

    for idx, (start_sec, end_sec) in enumerate(scenes, 1):
        shot_dur = max(0.1, end_sec - start_sec)
        mid_sec = start_sec + (shot_dur / 2.0)

        # Extract frames
        first_frame = _get_frame_at_sec(cap, start_sec, fps)
        mid_frame = _get_frame_at_sec(cap, mid_sec, fps)
        last_frame = _get_frame_at_sec(cap, max(start_sec, end_sec - 0.05), fps)

        # Save first frame (crucial for I2V reference)
        first_path = shots_dir / f"shot_{idx:03d}_first.jpg"
        if first_frame is not None:
            cv2.imwrite(str(first_path), first_frame)

        last_path = shots_dir / f"shot_{idx:03d}_last.jpg"
        if last_frame is not None:
            cv2.imwrite(str(last_path), last_frame)

        # Contact sheet (first | mid | last)
        tiled_path = shots_dir / f"shot_{idx:03d}.jpg"
        if first_frame is not None and mid_frame is not None and last_frame is not None:
            h, w = first_frame.shape[:2]
            target_w = 320
            target_h = int(h * (target_w / w))
            f1 = cv2.resize(first_frame, (target_w, target_h))
            f2 = cv2.resize(mid_frame, (target_w, target_h))
            f3 = cv2.resize(last_frame, (target_w, target_h))
            tiled = np.hstack([f1, f2, f3])
            cv2.imwrite(str(tiled_path), tiled)

        # Estimate camera motion
        motion = _estimate_camera_motion(first_frame, last_frame)

        shots.append({
            "index": idx,
            "id": f"shot_{idx:03d}",
            "start": round(start_sec, 3),
            "end": round(end_sec, 3),
            "duration": round(shot_dur, 3),
            "camera_motion": motion,
            "first_frame": str(first_path),
            "last_frame": str(last_path),
            "contact_sheet": str(tiled_path),
        })

    cap.release()

    # Generate full storyboard grid
    _create_storyboard(shots, out / "storyboard.jpg")

    return shots


def _get_frame_at_sec(cap: cv2.VideoCapture, sec: float, fps: float) -> np.ndarray | None:
    frame_idx = int(round(sec * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    return frame if ret else None


def _estimate_camera_motion(f1: np.ndarray | None, f2: np.ndarray | None) -> str:
    """Estimates basic camera motion between first and last frame."""
    if f1 is None or f2 is None:
        return "static"

    gray1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)

    # Phase correlation for translation
    shift, _ = cv2.phaseCorrelate(np.float32(gray1), np.float32(gray2))
    dx, dy = shift
    dist = math.hypot(dx, dy)

    if dist < 2.0:
        return "static"
    elif dist > 15.0:
        return "dynamic_cut_or_pan"
    return "smooth_pan_or_drift"


def _create_storyboard(shots: list[dict], out_path: Path, cols: int = 4) -> None:
    """Assembles a single overview contact sheet of all shots."""
    frames = []
    for s in shots:
        p = Path(s.get("first_frame", ""))
        if p.is_file():
            img = cv2.imread(str(p))
            if img is not None:
                img = cv2.resize(img, (240, 135))
                # Add label overlay
                cv2.putText(img, f"#{s['index']} {s['duration']}s", (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                frames.append(img)

    if not frames:
        return

    rows = math.ceil(len(frames) / cols)
    blank = np.zeros_like(frames[0])
    while len(frames) < rows * cols:
        frames.append(blank)

    grid_rows = [np.hstack(frames[r * cols:(r + 1) * cols]) for r in range(rows)]
    grid = np.vstack(grid_rows)
    cv2.imwrite(str(out_path), grid)
