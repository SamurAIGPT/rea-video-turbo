"""Model catalog and capability map for Muapi API models."""
from __future__ import annotations

import re
from typing import Any

MODELS: dict[str, dict[str, Any]] = {
    # ── Video Generation Models ──────────────────────────────────────────────
    "seedance-2.5": {
        "name": "Seedance 2.5",
        "category": "video",
        "limits": {"duration_min": 3, "duration_max": 30, "default_duration": 5},
        "capabilities": ["text_to_video", "image_to_video", "first_last_frame", "multimodal"],
        "endpoints": {
            "text_to_video": "seedance-2.5-text-to-video",
            "image_to_video": "seedance-2.5-image-to-video",
            "first_last_frame": "seedance-2.5-first-last-frame",
            "multimodal": "seedance-2.5-omni-reference",
        },
    },
    "seedance-2.0": {
        "name": "Seedance 2.0",
        "category": "video",
        "limits": {"duration_min": 3, "duration_max": 15, "default_duration": 5},
        "capabilities": ["text_to_video", "image_to_video", "first_last_frame", "multimodal"],
        "endpoints": {
            "text_to_video": "seedance-2-text-to-video",
            "image_to_video": "seedance-2-image-to-video",
            "first_last_frame": "seedance-2-first-last-frame",
            "multimodal": "seedance-2-omni-reference",
        },
    },
    "kling-v3.0-pro": {
        "name": "Kling 3.0 Pro",
        "category": "video",
        "limits": {"duration_min": 5, "duration_max": 10, "default_duration": 5},
        "capabilities": ["text_to_video", "image_to_video", "first_last_frame"],
        "endpoints": {
            "text_to_video": "kling-v3.0-pro-text-to-video",
            "image_to_video": "kling-o1-image-to-video",
            "first_last_frame": "kling-o1-image-to-video",
        },
    },
    "kling-4.0": {
        "name": "Kling 4.0 / 3.0 Omni",
        "category": "video",
        "limits": {"duration_min": 5, "duration_max": 15, "default_duration": 5},
        "capabilities": ["text_to_video", "image_to_video", "first_last_frame"],
        "endpoints": {
            "text_to_video": "kling-v3.0-omni-pro-text-to-video",
            "image_to_video": "kling-o1-image-to-video",
            "first_last_frame": "kling-o1-image-to-video",
        },
    },
    "veo-3.1": {
        "name": "Veo 3.1",
        "category": "video",
        "limits": {"duration_min": 3, "duration_max": 8, "default_duration": 5},
        "capabilities": ["text_to_video", "image_to_video"],
        "endpoints": {
            "text_to_video": "veo3.1-text-to-video",
            "image_to_video": "veo3-image-to-video",
        },
    },
    "wan-2.2": {
        "name": "Wan 2.2 / 2.1",
        "category": "video",
        "limits": {"duration_min": 3, "duration_max": 10, "default_duration": 5},
        "capabilities": ["text_to_video", "image_to_video"],
        "endpoints": {
            "text_to_video": "wan2.1-text-to-video",
            "image_to_video": "wan2.1-image-to-video",
        },
    },
    "minimax-hailuo": {
        "name": "MiniMax Hailuo 2.3",
        "category": "video",
        "limits": {"duration_min": 5, "duration_max": 10, "default_duration": 6},
        "capabilities": ["text_to_video", "image_to_video"],
        "endpoints": {
            "text_to_video": "minimax-hailuo-2.3-pro-t2v",
            "image_to_video": "minimax-hailuo-2.3-pro-i2v",
        },
    },

    # ── Image / Keyframe Models ──────────────────────────────────────────────
    "flux-dev": {
        "name": "FLUX.1 Dev",
        "category": "image",
        "endpoints": {"text_to_image": "flux-dev"},
    },
    "flux-pro": {
        "name": "FLUX Kontext Pro",
        "category": "image",
        "endpoints": {"text_to_image": "flux-kontext-pro-t2i"},
    },

    # ── Character & Lip-Sync Models ──────────────────────────────────────────
    "omnihuman-2.0": {
        "name": "OmniHuman 2.0 Lip-Sync",
        "category": "character",
        "endpoints": {"lip_sync": "omnihuman-2.0"},
    },
    "kling-avatar": {
        "name": "Kling Avatar v2",
        "category": "character",
        "endpoints": {"lip_sync": "kling-avatar-v2"},
    },

    # ── Audio & Narration Models ─────────────────────────────────────────────
    "elevenlabs": {
        "name": "ElevenLabs TTS",
        "category": "audio",
        "endpoints": {"tts": "elevenlabs-tts"},
    },

    # ── Vision / VLM Models ──────────────────────────────────────────────────
    "gemini-2.5-flash": {
        "name": "Gemini 2.5 Flash Multimodal",
        "category": "vlm",
        "model_id": "gemini-2.5-flash",
    },
    "gpt-4o": {
        "name": "GPT-4o Multimodal",
        "category": "vlm",
        "model_id": "gpt-4o",
    },
}


def resolve_model(model_name: str | None) -> tuple[str, dict[str, Any]]:
    """Normalizes input model name and finds matching catalog item."""
    if not model_name:
        return "seedance-2.5", MODELS["seedance-2.5"]

    raw = re.sub(r"[^a-z0-9.-]", "", model_name.lower())
    for k, v in MODELS.items():
        k_norm = re.sub(r"[^a-z0-9.-]", "", k.lower())
        if raw == k_norm or raw in k_norm or k_norm in raw:
            return k, v

    # Fallback to seedance-2.5
    return "seedance-2.5", MODELS["seedance-2.5"]


def get_endpoint_slug(model_key: str, generation_type: str) -> str:
    """Returns the exact Muapi endpoint slug for a model and generation type."""
    _, spec = resolve_model(model_key)
    endpoints = spec.get("endpoints", {})
    if generation_type in endpoints:
        return endpoints[generation_type]
    if "image_to_video" in endpoints:
        return endpoints["image_to_video"]
    if "text_to_video" in endpoints:
        return endpoints["text_to_video"]
    return "seedance-2.5-text-to-video"
