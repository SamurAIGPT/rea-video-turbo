import json

import pytest

from rea_video_turbo import memory, review


@pytest.fixture
def out(tmp_path, monkeypatch):
    monkeypatch.setenv("REA_VIDEO_TURBO_HOME", str(tmp_path / "home"))
    d = tmp_path / "out"
    d.mkdir()
    shots = [{"index": i, "id": f"shot_{i:03d}", "start": i - 1.0, "end": float(i), "duration": 1.0,
              "camera_motion": "static", "first_frame": "a.jpg", "last_frame": "b.jpg",
              "contact_sheet": "c.jpg", "vlm": {"label": "ai_video", "confidence": 0.5}} for i in (1, 2)]
    (d / "breakdown.json").write_text(json.dumps({"source": {}, "summary": {}, "shots": shots}))
    return d


def test_build_and_apply(out):
    tp, ap = review.build_review_tasks(out)
    assert len(json.loads(tp.read_text())["tasks"]) == 2
    data = json.loads(ap.read_text())
    data["answers"][0]["label"] = "live_action"
    ap.write_text(json.dumps(data))
    assert review.apply_review(out, by="tester") == 1
    b = json.loads((out / "breakdown.json").read_text())
    assert b["shots"][0]["vlm"]["label"] == "live_action"
    assert b["shots"][0]["vlm"]["original_label"] == "ai_video"
    assert b["summary"]["production_mix"] == {"live_action": 1, "ai_video": 1}
    assert (out / "VIDEO.md").is_file()


def test_apply_rejects_bad_label(out):
    _, ap = review.build_review_tasks(out)
    data = json.loads(ap.read_text())
    data["answers"][0]["label"] = "nope"
    ap.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        review.apply_review(out)


def test_correct_and_memory(out):
    assert review.correct(out, [2], "still_motion", "stop motion") == 1
    m = memory.list_memory()
    assert m["correction_counts"] == {"still_motion": 1}
    assert memory.corrections_for(str(out.resolve()))[0]["note"] == "stop motion"


def test_prefs(out):
    assert memory.get_prefs()["lang"] == "en"
    assert memory.set_pref("lang", "zh")["lang"] == "zh"
