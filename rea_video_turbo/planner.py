"""Planner module: batches shots into generation units and writes jobs.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models_catalog import resolve_model, get_endpoint_slug


def plan_remake(breakdown_file: str | Path, model_name: str = "seedance-2.5",
                out_dir: str | Path | None = None) -> Path:
    """Plans generation units and creates jobs.json for a breakdown."""
    b_path = Path(breakdown_file).resolve()
    if not b_path.is_file():
        raise FileNotFoundError(f"Breakdown file not found: {b_path}")

    b = json.loads(b_path.read_text(encoding="utf-8"))
    shots = b.get("shots", [])
    source_meta = b.get("source", {})
    aspect_ratio = source_meta.get("aspect_ratio", "9:16")

    model_key, model_spec = resolve_model(model_name)
    limits = model_spec.get("limits", {})
    max_duration = limits.get("duration_max", 15)
    default_duration = limits.get("default_duration", 5)

    jobs = []
    current_unit_shots: list[dict[str, Any]] = []
    current_dur = 0.0
    unit_idx = 1

    for sh in shots:
        label = (sh.get("vlm") or {}).get("label") or sh.get("label", "ai_video")

        if label in ("still_motion", "static_hold"):
            # Local deterministic Ken Burns / hold
            jobs.append({
                "shot": sh["index"],
                "id": f"shot_{sh['index']:03d}",
                "shots": [sh["index"]],
                "executor": "local_ffmpeg",
                "label": label,
                "duration": sh["duration"],
                "image": sh.get("first_frame"),
                "params": {
                    "image_path": sh.get("first_frame"),
                    "duration": sh["duration"],
                    "aspect_ratio": aspect_ratio,
                    "motion": sh.get("camera_motion", "static"),
                },
            })
            continue

        if label in ("code_render", "screen_capture"):
            jobs.append({
                "shot": sh["index"],
                "id": f"shot_{sh['index']:03d}",
                "shots": [sh["index"]],
                "executor": "code_render_spec",
                "label": label,
                "duration": sh["duration"],
                "params": {
                    "duration": sh["duration"],
                    "aspect_ratio": aspect_ratio,
                },
            })
            continue

        # AI-generative shots (ai_video, live_action, avatar, cg_3d, etc.)
        # Check if we should batch with previous
        if current_dur + sh["duration"] <= max_duration and current_unit_shots:
            current_unit_shots.append(sh)
            current_dur += sh["duration"]
        else:
            if current_unit_shots:
                jobs.append(_create_generation_job(current_unit_shots, unit_idx, model_key, aspect_ratio, default_duration))
                unit_idx += 1
            current_unit_shots = [sh]
            current_dur = sh["duration"]

    if current_unit_shots:
        jobs.append(_create_generation_job(current_unit_shots, unit_idx, model_key, aspect_ratio, default_duration))

    target_dir = Path(out_dir).resolve() if out_dir else b_path.parent / "remake"
    target_dir.mkdir(parents=True, exist_ok=True)
    jobs_file = target_dir / "jobs.json"

    jobs_data = {
        "breakdown": str(b_path),
        "model": model_key,
        "model_name": model_spec.get("name", model_key),
        "aspect_ratio": aspect_ratio,
        "total_jobs": len(jobs),
        "jobs": jobs,
    }

    jobs_file.write_text(json.dumps(jobs_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return jobs_file


def _create_generation_job(shots: list[dict], unit_idx: int, model_key: str,
                           aspect_ratio: str, default_duration: int) -> dict[str, Any]:
    total_dur = sum(s["duration"] for s in shots)
    primary_shot = shots[0]
    vlm = primary_shot.get("vlm", {})
    prompt = vlm.get("prompt") or "Cinematic shot with high fidelity details."

    first_frame = primary_shot.get("first_frame")
    last_frame = shots[-1].get("last_frame")

    # Determine strategy
    endpoint_fl = get_endpoint_slug(model_key, "first_last_frame")
    if first_frame and last_frame and "first-last" in endpoint_fl:
        gtype = "first_last_frame"
    elif first_frame:
        gtype = "image_to_video"
    else:
        gtype = "text_to_video"

    unit_id = f"G{unit_idx}"
    slug = get_endpoint_slug(model_key, gtype)

    return {
        "shot": primary_shot["index"],
        "id": unit_id,
        "unit": unit_id,
        "shots": [s["index"] for s in shots],
        "executor": "muapi",
        "label": vlm.get("label", "ai_video"),
        "generation_type": gtype,
        "model_slug": slug,
        "duration": round(total_dur, 2),
        "params": {
            "prompt": prompt,
            "engine": model_key,
            "generation_type": gtype,
            "duration": max(default_duration, int(round(total_dur))),
            "aspect_ratio": aspect_ratio,
            "start_image_path": first_frame,
            "end_image_path": last_frame,
        },
    }
