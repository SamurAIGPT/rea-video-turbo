"""Tests for rea-video-turbo models catalog, planner, and client."""
from pathlib import Path
from rea_video_turbo.models_catalog import resolve_model, get_endpoint_slug, MODELS
from rea_video_turbo.client import MuapiClient
from rea_video_turbo.planner import _create_generation_job


def test_models_catalog_resolution():
    key, spec = resolve_model("seedance-2.5")
    assert key == "seedance-2.5"
    assert "video" in spec["category"]

    key_kling, _ = resolve_model("kling-4.0")
    assert key_kling == "kling-4.0"

    # Fallback check
    fallback_key, _ = resolve_model("unknown-model-xyz")
    assert fallback_key == "seedance-2.5"


def test_endpoint_slug_mapping():
    assert get_endpoint_slug("seedance-2.5", "text_to_video") == "seedance-2.5-text-to-video"
    assert get_endpoint_slug("seedance-2.5", "image_to_video") == "seedance-2.5-image-to-video"
    assert get_endpoint_slug("kling-v3.0-pro", "text_to_video") == "kling-v3.0-pro-text-to-video"
    assert get_endpoint_slug("kling-v3.0-pro", "image_to_video") == "kling-o1-image-to-video"
    assert get_endpoint_slug("veo-3.1", "text_to_video") == "veo3.1-text-to-video"


def test_create_generation_job():
    shots = [
        {
            "index": 1,
            "duration": 4.5,
            "first_frame": "shot_001_first.jpg",
            "last_frame": "shot_001_last.jpg",
            "vlm": {
                "label": "ai_video",
                "prompt": "Futuristic flying car hovering over cyberpunk city street at night, neon reflections."
            }
        }
    ]
    job = _create_generation_job(shots, unit_idx=1, model_key="seedance-2.5", aspect_ratio="9:16", default_duration=5)
    assert job["id"] == "G1"
    assert job["executor"] == "muapi"
    assert job["generation_type"] == "first_last_frame"
    assert job["model_slug"] == "seedance-2.5-first-last-frame"
    assert job["params"]["duration"] == 5
    assert "cyberpunk" in job["params"]["prompt"]


def test_client_configuration():
    client = MuapiClient(api_key="test_key_123", base_url="https://api.muapi.ai")
    assert client.is_configured
    assert client.base_url == "https://api.muapi.ai"
    assert client._headers()["x-api-key"] == "test_key_123"
