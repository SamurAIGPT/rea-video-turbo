"""Muapi API client for submitting tasks, polling results, and uploading/downloading media."""
from __future__ import annotations

import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Callable

import httpx

DEFAULT_BASE_URL = "https://api.muapi.ai/api/v1"


class MuapiClientError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class MuapiClient:
    """Client for interacting with the Muapi platform."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = (api_key or os.getenv("MUAPI_API_KEY", "")).strip()
        raw_base = (base_url or os.getenv("MUAPI_BASE_URL", "")).strip() or DEFAULT_BASE_URL
        self.base_url = raw_base.rstrip("/")
        self._upload_cache: dict[str, str] = {}

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise MuapiClientError("MUAPI_API_KEY is not configured.")
        return {
            "x-api-key": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
        }

    def upload_file(self, file_path: str | Path) -> str:
        """Uploads a local file to Muapi S3 bucket and returns the hosted URL."""
        p = Path(file_path).resolve()
        cache_key = str(p)
        if cache_key in self._upload_cache:
            return self._upload_cache[cache_key]

        if not p.is_file():
            raise FileNotFoundError(f"Local file to upload not found: {p}")

        url = f"{self.base_url}/upload_file"
        mime, _ = mimetypes.guess_type(str(p))
        mime = mime or "application/octet-stream"

        with open(p, "rb") as f:
            files = {"file": (p.name, f, mime)}
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(url, files=files, headers={"x-api-key": self.api_key})

        if resp.status_code >= 400:
            raise MuapiClientError(f"Upload failed ({resp.status_code}): {resp.text}", resp.status_code)

        data = resp.json()
        s3_url = data.get("url")
        if not s3_url:
            raise MuapiClientError(f"Upload response missing 'url': {data}")

        self._upload_cache[cache_key] = s3_url
        return s3_url

    def resolve_asset_url(self, path_or_url: str | Path) -> str:
        s = str(path_or_url)
        if s.startswith(("http://", "https://", "data:")):
            return s
        return self.upload_file(s)

    def submit_task(self, slug: str, payload: dict[str, Any]) -> str:
        """Submits an async prediction task to Muapi."""
        url = f"{self.base_url}/{slug.lstrip('/')}"
        headers = self._headers()
        headers["Content-Type"] = "application/json"

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload, headers=headers)

        if resp.status_code >= 400:
            raise MuapiClientError(f"Task submission failed ({resp.status_code}): {resp.text}", resp.status_code)

        data = resp.json()
        req_id = data.get("request_id") or data.get("id")
        if not req_id:
            raise MuapiClientError(f"Response missing request_id: {data}")
        return req_id

    def poll_result(self, request_id: str, max_seconds: int = 600, poll_interval: int = 4,
                    progress_cb: Callable[[str], None] | None = None) -> dict[str, Any]:
        """Polls until status is 'completed' or 'failed'."""
        url = f"{self.base_url}/predictions/{request_id}/result"
        headers = self._headers()
        deadline = time.time() + max_seconds

        with httpx.Client(timeout=30.0) as client:
            while time.time() < deadline:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status", "")
                    if progress_cb:
                        progress_cb(status)
                    if status == "completed":
                        return data
                    elif status == "failed":
                        err = data.get("error", "Unknown generation failure")
                        raise MuapiClientError(f"Generation task failed: {err}")
                elif resp.status_code >= 400:
                    raise MuapiClientError(f"Polling error ({resp.status_code}): {resp.text}", resp.status_code)

                time.sleep(poll_interval)

        raise TimeoutError(f"Timed out waiting for Muapi result after {max_seconds}s")

    def download_file(self, url: str, dest_path: Path) -> Path:
        """Downloads a remote media file to a local destination."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=180.0, follow_redirects=True) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        f.write(chunk)
        return dest_path
