"""Small on-disk memory: user preferences and corrections to earlier verdicts.

Stored as JSON under ``~/.rea_video_turbo`` (override with ``REA_VIDEO_TURBO_HOME``).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

DEFAULT_PREFS: dict[str, Any] = {"lang": "en", "vlm": False, "reviewer": "agent", "note": ""}


def home() -> Path:
    p = Path(os.environ.get("REA_VIDEO_TURBO_HOME") or Path.home() / ".rea_video_turbo")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read(name: str, default: Any) -> Any:
    f = home() / name
    if not f.is_file():
        return default
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(name: str, data: Any) -> None:
    (home() / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_prefs() -> dict[str, Any]:
    return {**DEFAULT_PREFS, **_read("prefs.json", {})}


def set_pref(key: str, value: Any) -> dict[str, Any]:
    prefs = _read("prefs.json", {})
    prefs[key] = value
    _write("prefs.json", prefs)
    return get_prefs()


def add_correction(source: str, shots: list[int], label: str, note: str = "") -> dict[str, Any]:
    entry = {"source": source, "shots": shots, "label": label, "note": note, "ts": int(time.time())}
    items = _read("corrections.json", [])
    items.append(entry)
    _write("corrections.json", items)
    return entry


def list_memory() -> dict[str, Any]:
    corrections = _read("corrections.json", [])
    counts: dict[str, int] = {}
    for c in corrections:
        counts[c["label"]] = counts.get(c["label"], 0) + 1
    return {"prefs": get_prefs(), "corrections": corrections, "correction_counts": counts}


def corrections_for(source: str) -> list[dict[str, Any]]:
    return [c for c in _read("corrections.json", []) if c.get("source") == source]
