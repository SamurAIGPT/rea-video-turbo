"""Execution and assembly of remake videos using Muapi generations and local FFmpeg."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .client import MuapiClient, MuapiClientError


def execute_remake(jobs_file: str | Path, dry_run: bool = False,
                   client: MuapiClient | None = None) -> dict[str, Any]:
    """Runs generation jobs against Muapi and renders still motion shots locally."""
    j_path = Path(jobs_file).resolve()
    if not j_path.is_file():
        raise FileNotFoundError(f"Jobs file not found: {j_path}")

    jobs_data = json.loads(j_path.read_text(encoding="utf-8"))
    jobs = jobs_data.get("jobs", [])
    out_dir = j_path.parent
    segments_dir = out_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    results_file = out_dir / "results.json"
    results: dict[str, Any] = {"results": {}}
    if results_file.is_file():
        try:
            results = json.loads(results_file.read_text(encoding="utf-8"))
        except Exception:
            results = {"results": {}}

    c = client or MuapiClient()

    print(f"[{'DRY-RUN' if dry_run else 'EXECUTE'}] Remake Runner: Processing {len(jobs)} job(s)...")

    for idx, j in enumerate(jobs, 1):
        jid = j["id"]
        executor = j.get("executor", "muapi")
        shots = j.get("shots", [j.get("shot")])
        shots_str = ",".join(str(s) for s in shots)
        dur = j.get("duration", 5.0)

        print(f"\n({idx}/{len(jobs)}) Job '{jid}' (Shots: {shots_str}) [{executor}] - Duration: {dur}s")

        if executor == "local_ffmpeg":
            img_path = j.get("image") or j.get("params", {}).get("image_path")
            out_clip = segments_dir / f"{jid}.mp4"
            print(f"  Rendering still motion locally from {Path(img_path).name if img_path else 'image'} -> {out_clip.name}")
            if not dry_run and img_path and Path(img_path).is_file():
                _render_still_clip(Path(img_path), out_clip, dur)
                results["results"][jid] = {"video": str(out_clip), "type": "local_still"}
            continue

        if executor == "code_render_spec":
            print(f"  Code/UI render specification ready for Remotion reconstruction.")
            continue

        # Muapi generation job
        params = j.get("params", {})
        slug = j.get("model_slug", "seedance-2.5-image-to-video")
        prompt = params.get("prompt", "")
        aspect = params.get("aspect_ratio", "9:16")
        duration = int(params.get("duration", 5))

        payload: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": aspect,
            "duration": duration,
        }

        start_img = params.get("start_image_path")
        end_img = params.get("end_image_path")

        if start_img and Path(start_img).is_file():
            payload["image_url"] = "<uploaded_image>" if dry_run else c.resolve_asset_url(start_img)
        if end_img and Path(end_img).is_file():
            payload["last_image"] = "<uploaded_image>" if dry_run else c.resolve_asset_url(end_img)

        print(f"  Muapi Model: {slug}")
        print(f"  Prompt: {prompt[:100]}...")

        if dry_run:
            print(f"  [Dry-run payload]: {json.dumps(payload, ensure_ascii=False)}")
            continue

        # Live execution
        if not c.is_configured:
            raise MuapiClientError("MUAPI_API_KEY is not configured.")

        out_clip = segments_dir / f"{jid}.mp4"
        print(f"  Submitting task to Muapi /api/v1/{slug}...")
        req_id = c.submit_task(slug, payload)
        print(f"  Task ID: {req_id}. Waiting for completion...")

        res_data = c.poll_result(req_id, progress_cb=lambda s: print(f"    Status: {s}...", end="\r"))
        print("\n  Task completed!")

        video_url = _find_video_url(res_data)
        if not video_url:
            raise MuapiClientError(f"No video URL in completed task response: {res_data}")

        print(f"  Downloading video -> {out_clip.name}...")
        c.download_file(video_url, out_clip)

        results["results"][jid] = {
            "video": str(out_clip),
            "unit": j.get("unit"),
            "model": slug,
            "request_id": req_id,
        }
        results_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    results_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def assemble_remake(breakdown_file: str | Path, results_file: str | Path,
                    out_dir: str | Path | None = None) -> tuple[Path, Path]:
    """Assembles all generated segments on the timeline and renders side-by-side compare.mp4."""
    b_path = Path(breakdown_file).resolve()
    r_path = Path(results_file).resolve()
    b = json.loads(b_path.read_text(encoding="utf-8"))
    res_data = json.loads(r_path.read_text(encoding="utf-8")).get("results", {})

    target_dir = Path(out_dir).resolve() if out_dir else r_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    src_video = Path(b["source"]["path"]).resolve()
    remake_video = target_dir / "remake.mp4"
    compare_video = target_dir / "compare.mp4"

    # Build concat file list
    concat_list = target_dir / "concat.txt"
    lines = []
    for sh in b["shots"]:
        s_idx = sh["index"]
        dur = sh["duration"]
        # Find matching result
        matched_video = None
        for k, v in res_data.items():
            if str(k) == f"shot_{s_idx:03d}" or str(k) == str(s_idx):
                matched_video = v.get("video")
                break
        if not matched_video:
            for k, v in res_data.items():
                if v.get("unit") and str(s_idx) in [str(x) for x in v.get("shots", [])]:
                    matched_video = v.get("video")
                    break

        if matched_video and Path(matched_video).is_file():
            # Fit clip to shot duration
            fitted = target_dir / "segments" / f"fitted_shot_{s_idx:03d}.mp4"
            _fit_clip_to_duration(Path(matched_video), fitted, dur)
            lines.append(f"file '{fitted.as_posix()}'")

    if not lines:
        raise ValueError("No valid video segments found to assemble.")

    concat_list.write_text("\n".join(lines), encoding="utf-8")

    # Concat segments with original audio
    concat_cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-i", str(src_video),
        "-map", "0:v", "-map", "1:a?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-shortest", str(remake_video)
    ]
    subprocess.run(concat_cmd, check=True)

    # Render side-by-side compare.mp4 (Original | Remake)
    compare_cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-i", str(src_video),
        "-i", str(remake_video),
        "-filter_complex", "[0:v][1:v]hstack[v]",
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        str(compare_video)
    ]
    subprocess.run(compare_cmd, check=True)

    return remake_video, compare_video


def _fit_clip_to_duration(src: Path, dst: Path, target_dur: float) -> None:
    """Trims or retimes a video clip to match the target shot duration exactly."""
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-i", str(src),
        "-t", f"{target_dur:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
        str(dst)
    ]
    subprocess.run(cmd, check=True)


def _render_still_clip(img_path: Path, out_path: Path, duration: float, fps: int = 30) -> None:
    """Creates a smooth Ken Burns pan/zoom mp4 from a still image."""
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-loop", "1", "-i", str(img_path),
        "-t", f"{duration:.3f}",
        "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0015,1.15)':d={int(duration*fps)}:s=1080x1920",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), "-an",
        str(out_path)
    ]
    subprocess.run(cmd, check=True)


def _find_video_url(res: dict) -> str | None:
    res_body = res.get("result") or res.get("data") or res
    if isinstance(res_body, str) and res_body.startswith("http"):
        return res_body
    if isinstance(res_body, dict):
        for k in ("video", "url", "output_url", "video_url"):
            v = res_body.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
    return None
