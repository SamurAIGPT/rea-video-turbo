"""On-screen text and packaging analysis: captions (SRT/ASS), overlays, cut rhythm."""
from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

import cv2
import numpy as np

OCR_HINT = "pip install rea-video-turbo[ocr]"


# ---------------------------------------------------------------- OCR

def _load_ocr():
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
    except Exception:
        return None
    try:
        return RapidOCR()
    except Exception:
        return None


def ocr_frame(engine: Any, frame: np.ndarray, min_conf: float = 0.6) -> list[dict[str, Any]]:
    """Run OCR on a BGR frame. Returns [{text, bbox:[x0,y0,x1,y1] normalised, conf}]."""
    h, w = frame.shape[:2]
    result, _ = engine(frame)
    out = []
    for item in result or []:
        box, text, conf = item[0], str(item[1]).strip(), float(item[2])
        if not text or conf < min_conf:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append({
            "text": text,
            "bbox": [round(min(xs) / w, 4), round(min(ys) / h, 4),
                     round(max(xs) / w, 4), round(max(ys) / h, 4)],
            "conf": round(conf, 3),
        })
    return out


# ---------------------------------------------------------------- tracking

def _iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def track_text_lines(
    observations: list[tuple[float, list[dict[str, Any]]]],
    sample_interval: float = 0.5,
    min_iou: float = 0.3,
    min_similarity: float = 0.7,
    min_duration: float = 0.0,
) -> list[dict[str, Any]]:
    """Merge per-frame OCR hits into timed lines.

    observations: [(time_sec, [ {text, bbox, ...}, ... ]), ...] sorted by time.
    A hit continues an open track if its bbox overlaps and the text is similar
    and the track was seen within ~1.5 sample intervals. Track end = last seen + interval.
    """
    tracks: list[dict[str, Any]] = []
    open_tracks: list[dict[str, Any]] = []
    for t, hits in sorted(observations, key=lambda o: o[0]):
        still_open = []
        for tr in open_tracks:
            if t - tr["_last"] <= sample_interval * 1.5 + 1e-6:
                still_open.append(tr)
        open_tracks = still_open
        used: set[int] = set()
        for hit in hits:
            best, best_score = None, 0.0
            for i, tr in enumerate(open_tracks):
                if i in used:
                    continue
                sim = difflib.SequenceMatcher(None, tr["text"], hit["text"]).ratio()
                ov = _iou(tr["bbox"], hit["bbox"])
                if sim >= min_similarity and ov >= min_iou and sim + ov > best_score:
                    best, best_score = i, sim + ov
            if best is not None:
                tr = open_tracks[best]
                used.add(best)
                tr["_last"] = t
                tr["end"] = round(t + sample_interval, 3)
                tr["_n"] += 1
                if len(hit["text"]) > len(tr["text"]):
                    tr["text"] = hit["text"]
                    tr["bbox"] = hit["bbox"]
            else:
                tr = {"text": hit["text"], "bbox": list(hit["bbox"]),
                      "start": round(t, 3), "end": round(t + sample_interval, 3),
                      "_last": t, "_n": 1}
                tracks.append(tr)
                open_tracks.append(tr)
                used.add(len(open_tracks) - 1)
    lines = []
    for tr in tracks:
        if tr["end"] - tr["start"] < min_duration:
            continue
        lines.append({"text": tr["text"], "bbox": tr["bbox"],
                      "start": tr["start"], "end": tr["end"], "samples": tr["_n"]})
    lines.sort(key=lambda l: (l["start"], l["bbox"][1]))
    return lines


# ---------------------------------------------------------------- SRT / ASS

def _srt_time(sec: float) -> str:
    ms = int(round(max(0.0, sec) * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_time(sec: float) -> str:
    cs = int(round(max(0.0, sec) * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def write_srt(lines: list[dict[str, Any]], path: str | Path) -> Path:
    p = Path(path)
    body = []
    for i, l in enumerate(sorted(lines, key=lambda x: x["start"]), 1):
        body.append(f"{i}\n{_srt_time(l['start'])} --> {_srt_time(l['end'])}\n{l['text']}\n")
    p.write_text("\n".join(body), encoding="utf-8")
    return p


def write_ass(lines: list[dict[str, Any]], path: str | Path,
              width: int = 1080, height: int = 1920) -> Path:
    """Simple styled ASS: Bottom style for lower-third captions, Top for upper text.
    Position follows each line's bbox centre via an \\pos override."""
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,56,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,1,0,0,0,"
        "100,100,0,0,1,3,1,5,40,40,40,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    ev = []
    for l in sorted(lines, key=lambda x: x["start"]):
        x0, y0, x1, y1 = l["bbox"]
        cx, cy = int((x0 + x1) / 2 * width), int((y0 + y1) / 2 * height)
        size = max(24, int((y1 - y0) * height * 0.9))
        text = l["text"].replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", "\\N")
        ev.append(f"Dialogue: 0,{_ass_time(l['start'])},{_ass_time(l['end'])},Default,,0,0,0,,"
                  f"{{\\pos({cx},{cy})\\fs{size}}}{text}")
    p = Path(path)
    p.write_text(header + "\n".join(ev) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------- overlays

def _sat_mask(frame: np.ndarray, sat_min: int = 160, val_min: int = 90) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    return ((hsv[..., 1] >= sat_min) & (hsv[..., 2] >= val_min)).astype(np.uint8)


def detect_overlays(
    frames: list[np.ndarray],
    min_persist: float = 0.8,
    min_area_frac: float = 0.002,
    max_area_frac: float = 0.35,
) -> list[dict[str, Any]]:
    """Heuristic sticker/overlay finder: regions saturated in >= min_persist of the
    sampled frames AND with near-zero temporal variance (static). Returns normalised bboxes."""
    if len(frames) < 3:
        return []
    h, w = frames[0].shape[:2]
    small = [cv2.resize(f, (w // 4 or 1, h // 4 or 1)) for f in frames]
    masks = np.stack([_sat_mask(f) for f in small])
    persist = masks.mean(axis=0) >= min_persist
    gray = np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32) for f in small])
    static = gray.std(axis=0) < 6.0
    region = (persist & static).astype(np.uint8)
    region = cv2.morphologyEx(region, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(region)
    sh, sw = region.shape
    out = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        frac = area / float(sh * sw)
        if frac < min_area_frac or frac > max_area_frac:
            continue
        out.append({"bbox": [round(x / sw, 4), round(y / sh, 4),
                             round((x + bw) / sw, 4), round((y + bh) / sh, 4)],
                    "area_frac": round(frac, 4)})
    return out


# ---------------------------------------------------------------- rhythm

def cut_rhythm(shots: list[dict[str, Any]]) -> dict[str, Any]:
    if not shots:
        return {"shots": 0, "cuts": 0, "cuts_per_minute": 0.0, "avg_shot_length": 0.0,
                "min_shot_length": 0.0, "max_shot_length": 0.0, "pace": "n/a"}
    durs = [float(s.get("duration") or (s["end"] - s["start"])) for s in shots]
    total = max(float(shots[-1]["end"]) - float(shots[0]["start"]), 1e-6)
    cuts = len(shots) - 1
    cpm = cuts / total * 60.0
    avg = sum(durs) / len(durs)
    pace = "fast" if avg < 1.5 else "medium" if avg < 4.0 else "slow"
    return {"shots": len(shots), "cuts": cuts, "cuts_per_minute": round(cpm, 2),
            "avg_shot_length": round(avg, 3), "min_shot_length": round(min(durs), 3),
            "max_shot_length": round(max(durs), 3), "pace": pace}


# ---------------------------------------------------------------- orchestration

def _sample_times(shots: list[dict[str, Any]], interval: float, duration: float) -> list[float]:
    ts: set[float] = set()
    for s in shots:
        t = float(s["start"]) + 0.05
        end = float(s["end"])
        while t < end:
            ts.add(round(t, 3))
            t += interval
    return sorted(x for x in ts if x < duration) if duration else sorted(ts)


def analyze_packaging(
    video: str | Path,
    shots: list[dict[str, Any]],
    out_dir: str | Path,
    sample_interval: float = 0.5,
    max_samples: int = 240,
    ocr_engine: Any = None,
) -> dict[str, Any]:
    """Analyse on-screen text, overlays and cut rhythm. Writes captions.srt / captions.ass
    into out_dir/packaging when OCR is available. Result is JSON-serialisable."""
    out = Path(out_dir) / "packaging"
    out.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"rhythm": cut_rhythm(shots), "ocr": "unavailable",
                              "text_lines": [], "overlays": []}

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    duration = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    times = _sample_times(shots, sample_interval, duration)
    if len(times) > max_samples:  # widen interval on long videos
        step = len(times) / max_samples
        times = [times[int(i * step)] for i in range(max_samples)]
        sample_interval = sample_interval * step

    frames: list[tuple[float, np.ndarray]] = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, f = cap.read()
        if ok and f is not None:
            frames.append((t, f))
    cap.release()
    if not frames:
        result["ocr_hint"] = OCR_HINT
        return result
    height, width = frames[0][1].shape[:2]

    # overlays: per shot, on that shot's sampled frames
    for s in shots:
        sf = [f for t, f in frames if float(s["start"]) <= t < float(s["end"])]
        for ov in detect_overlays(sf[:12]):
            ov["shot"] = s.get("id") or s.get("index")
            ov["start"], ov["end"] = float(s["start"]), float(s["end"])
            result["overlays"].append(ov)

    engine = ocr_engine or _load_ocr()
    if engine is None:
        result["ocr_hint"] = OCR_HINT
        return result

    obs = [(t, ocr_frame(engine, f)) for t, f in frames]
    lines = track_text_lines(obs, sample_interval=sample_interval)
    result["ocr"] = "ok"
    result["text_lines"] = lines
    if lines:
        result["srt"] = str(write_srt(lines, out / "captions.srt"))
        result["ass"] = str(write_ass(lines, out / "captions.ass", width=width, height=height))
    return result
