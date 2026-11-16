"""Multimodal VLM client using Muapi's OpenAI-compatible /v1/chat/completions endpoint."""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

SYSTEM_PROMPT = """You are an expert video reverse-engineer and forensic cinematographer.
For the given shot image(s) from a video, analyze the visual and return a JSON object with:
1. "label": Choose exactly one from ["ai_video", "live_action", "avatar", "cg_3d", "code_render", "screen_capture", "still_motion", "static_hold"]
2. "confidence": A float from 0.0 to 1.0
3. "description": A concise description of what is happening in the shot
4. "framing": Shot size e.g. "close_up", "medium_shot", "wide_shot", "macro"
5. "camera_move": Camera motion e.g. "static", "dolly_in", "pan_left", "handheld", "orbit"
6. "lighting": Lighting setup e.g. "softbox_key_fill", "natural_window", "neon_cyberpunk", "high_contrast", "studio_bright"
7. "prompt": A high-quality, descriptive English prompt suitable for generating this exact shot in Kling 3.0 / Seedance 2.5
8. "narrative_role": Choose from ["hook", "problem", "demonstration", "proof", "transition", "cta"]

Respond ONLY with valid JSON, without markdown formatting or code fences."""


class MuapiVLM:
    """Interacts with Muapi's multimodal LLM endpoints for video understanding."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.api_key = (api_key or os.getenv("MUAPI_API_KEY", "")).strip()
        raw_base = (base_url or os.getenv("MUAPI_BASE_URL", "")).strip() or "https://api.muapi.ai"
        # OpenAI-compatible route on Muapi
        self.endpoint = f"{raw_base.rstrip('/')}/v1/chat/completions"
        self.model = model or os.getenv("MUAPI_VLM_MODEL", "gemini-2.5-flash")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def analyze_shot(self, image_path: str | Path, shot_meta: dict[str, Any] | None = None) -> dict[str, Any]:
        """Analyzes a shot image using the Multimodal VLM."""
        if not self.is_configured:
            return self._heuristic_fallback(shot_meta)

        p = Path(image_path).resolve()
        if not p.is_file():
            return self._heuristic_fallback(shot_meta)

        # Base64 encode image
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{b64}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this video shot and reverse-engineer how to recreate it."},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                },
            ],
            "temperature": 0.2,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(self.endpoint, json=payload, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                # Clean up any potential markdown code blocks
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
                return json.loads(content)
        except Exception:
            pass

        return self._heuristic_fallback(shot_meta)

    def _heuristic_fallback(self, shot_meta: dict[str, Any] | None) -> dict[str, Any]:
        """Deterministic heuristic fallback when VLM is disabled or unavailable."""
        dur = (shot_meta or {}).get("duration", 4.0)
        motion = (shot_meta or {}).get("camera_motion", "static")
        return {
            "label": "ai_video" if motion != "static" else "still_motion",
            "confidence": 0.65,
            "description": "Visual scene identified via deterministic heuristics.",
            "framing": "medium_shot",
            "camera_move": motion,
            "lighting": "natural_balanced",
            "prompt": "Cinematic high quality shot, professional lighting, photorealistic details.",
            "narrative_role": "demonstration",
        }
