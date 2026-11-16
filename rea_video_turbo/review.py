"""Visual review loop: an agent that can view images checks each shot, answers are merged back."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import memory
from .report import generate_reports

LABELS = ["ai_video", "live_action", "avatar", "cg_3d", "code_render", "screen_capture", "still_motion", "static_hold"]


def _load(out_dir: str | Path) -> tuple[Path, dict[str, Any]]:
    out = Path(out_dir).resolve()
    f = out / "breakdown.json"
    if not f.is_file():
        raise FileNotFoundError(f"breakdown.json not found in {out}. Run 'decompose' first.")
    return out, json.loads(f.read_text(encoding="utf-8"))


def _save(out: Path, b: dict[str, Any]) -> None:
    mix: dict[str, int] = {}
    for sh in b["shots"]:
        lbl = (sh.get("vlm") or {}).get("label", "ai_video")
        mix[lbl] = mix.get(lbl, 0) + 1
    b.setdefault("summary", {}).update(
        total_shots=len(b["shots"]), production_mix=mix,
        production_mix_str=", ".join(f"{k}: {v}" for k, v in mix.items()))
    generate_reports(b, out)


def build_review_tasks(out_dir: str | Path) -> tuple[Path, Path]:
    """Write review_tasks.json (what to look at) and review_answers.json (template to fill)."""
    out, b = _load(out_dir)
    tasks, answers = [], []
    for sh in b["shots"]:
        v = sh.get("vlm") or {}
        tasks.append({
            "shot": sh["index"], "start": sh["start"], "end": sh["end"], "duration": sh["duration"],
            "images": [sh.get("first_frame"), sh.get("contact_sheet"), sh.get("last_frame")],
            "current_label": v.get("label"), "current_confidence": v.get("confidence"),
            "camera_motion": sh.get("camera_motion"), "allowed_labels": LABELS,
        })
        answers.append({"shot": sh["index"], "label": v.get("label"), "confidence": None, "note": ""})
    tp, ap = out / "review_tasks.json", out / "review_answers.json"
    tp.write_text(json.dumps({"tasks": tasks}, indent=2), encoding="utf-8")
    ap.write_text(json.dumps({"by": "", "answers": answers}, indent=2), encoding="utf-8")
    return tp, ap


def apply_review(out_dir: str | Path, answers_path: str | Path | None = None, by: str | None = None) -> int:
    """Merge answers into breakdown.json and regenerate reports. Returns number of shots changed."""
    out, b = _load(out_dir)
    ap = Path(answers_path) if answers_path else out / "review_answers.json"
    data = json.loads(ap.read_text(encoding="utf-8"))
    reviewer = by or data.get("by") or memory.get_prefs()["reviewer"]
    by_idx = {sh["index"]: sh for sh in b["shots"]}
    changed = 0
    for a in data.get("answers", []):
        sh = by_idx.get(a.get("shot"))
        label = a.get("label")
        if sh is None or not label:
            continue
        if label not in LABELS:
            raise ValueError(f"shot {a['shot']}: unknown label {label!r}; allowed: {LABELS}")
        v = sh.setdefault("vlm", {})
        if v.get("label") != label:
            changed += 1
            v["original_label"] = v.get("label")
        v["label"] = label
        if a.get("confidence") is not None:
            v["confidence"] = a["confidence"]
        v["reviewed_by"] = reviewer
        if a.get("note"):
            v["review_note"] = a["note"]
    b.setdefault("summary", {})["reviewed_by"] = reviewer
    _save(out, b)
    return changed


def correct(out_dir: str | Path, shots: list[int], label: str, note: str = "") -> int:
    """Apply a user correction to the given shot indexes and remember it. Returns shots changed."""
    if label not in LABELS:
        raise ValueError(f"unknown label {label!r}; allowed: {LABELS}")
    out, b = _load(out_dir)
    wanted, changed = set(shots), 0
    for sh in b["shots"]:
        if sh["index"] in wanted:
            v = sh.setdefault("vlm", {})
            if v.get("label") != label:
                v["original_label"] = v.get("label")
                changed += 1
            v.update(label=label, confidence=1.0, reviewed_by="user")
            if note:
                v["review_note"] = note
    _save(out, b)
    memory.add_correction(str(out), sorted(wanted), label, note)
    return changed
