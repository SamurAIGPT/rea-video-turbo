import json

import numpy as np

from rea_video_turbo.packaging import (
    analyze_packaging, cut_rhythm, detect_overlays, track_text_lines, write_ass, write_srt,
)

BOX = [0.1, 0.8, 0.9, 0.9]


def test_tracking_merges_and_splits():
    obs = [
        (0.0, [{"text": "Hello world", "bbox": BOX}]),
        (0.5, [{"text": "Hello world", "bbox": BOX}]),
        (1.0, [{"text": "Hello wor1d", "bbox": BOX}]),
        (1.5, [{"text": "Buy now", "bbox": BOX}]),
        (3.0, [{"text": "Hello world", "bbox": BOX}]),  # gap -> new line
    ]
    lines = track_text_lines(obs, sample_interval=0.5)
    assert [l["text"] for l in lines] == ["Hello world", "Buy now", "Hello world"]
    assert lines[0]["start"] == 0.0 and lines[0]["end"] == 1.5 and lines[0]["samples"] == 3
    assert lines[2]["start"] == 3.0


def test_srt_and_ass(tmp_path):
    lines = [{"text": "Hi", "bbox": BOX, "start": 0.0, "end": 1.25},
             {"text": "Bye {x}", "bbox": [0.1, 0.1, 0.9, 0.2], "start": 3661.5, "end": 3662.0}]
    srt = write_srt(lines, tmp_path / "a.srt").read_text()
    assert "1\n00:00:00,000 --> 00:00:01,250\nHi" in srt
    assert "01:01:01,500 --> 01:01:02,000" in srt
    ass = write_ass(lines, tmp_path / "a.ass", 1080, 1920).read_text()
    assert "Dialogue: 0,0:00:00.00,0:00:01.25,Default" in ass
    assert "\\pos(540," in ass and "{x}" not in ass


def test_rhythm():
    shots = [{"start": 0, "end": 1, "duration": 1}, {"start": 1, "end": 3, "duration": 2},
             {"start": 3, "end": 6, "duration": 3}]
    r = cut_rhythm(shots)
    assert r["cuts"] == 2 and r["cuts_per_minute"] == 20.0 and r["avg_shot_length"] == 2.0
    assert cut_rhythm([])["shots"] == 0


def test_overlay_static_sticker():
    rng = np.random.default_rng(0)
    frames = []
    for _ in range(6):
        f = rng.integers(0, 60, (200, 200, 3), dtype=np.uint8)
        f[20:70, 20:70] = (0, 0, 255)  # static saturated red block
        frames.append(f)
    ov = detect_overlays(frames)
    assert len(ov) == 1
    x0, y0, x1, y1 = ov[0]["bbox"]
    assert 0.05 < x0 < 0.2 and 0.3 < x1 < 0.45


def test_analyze_without_ocr_is_json_safe(tmp_path):
    import cv2
    vid = tmp_path / "v.mp4"
    w = cv2.VideoWriter(str(vid), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
    for _ in range(30):
        w.write(np.zeros((64, 64, 3), np.uint8))
    w.release()
    shots = [{"id": "shot_001", "start": 0.0, "end": 3.0, "duration": 3.0}]
    res = analyze_packaging(vid, shots, tmp_path, ocr_engine=None)
    json.dumps(res)
    assert res["rhythm"]["shots"] == 1
    assert res["ocr"] in ("unavailable", "ok")
