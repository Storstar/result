from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from google import genai

from ..config import get_settings


class GeminiAdapter:
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = bool(settings.gemini_api_key)
        self.model = settings.gemini_model
        self.timeout_seconds = settings.gemini_timeout_seconds
        self._client = genai.Client(api_key=settings.gemini_api_key) if self.enabled else None

    def analyze_video(
        self,
        *,
        video_path: Path,
        prompt: str,
        logs_dir: Path,
    ) -> Optional[dict[str, Any]]:
        if not self.enabled or self._client is None or not video_path.exists():
            return None

        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "gemini_prompt.txt").write_text(prompt, encoding="utf-8")
        upload_path = self._prepare_upload_path(video_path)
        uploaded = self._client.files.upload(file=str(upload_path))
        started_at = time.time()
        state_name = getattr(getattr(uploaded, "state", None), "name", "")

        while state_name == "PROCESSING":
            if time.time() - started_at > self.timeout_seconds:
                raise RuntimeError(f"Gemini video processing timed out after {self.timeout_seconds} seconds.")
            time.sleep(2)
            uploaded = self._client.files.get(name=uploaded.name)
            state_name = getattr(getattr(uploaded, "state", None), "name", "")

        if state_name and state_name != "ACTIVE":
            raise RuntimeError(f"Gemini file upload ended in state: {state_name}")

        response = self._client.models.generate_content(
            model=self.model,
            contents=[uploaded, prompt],
            config={
                "response_mime_type": "application/json",
            },
        )
        response_text = getattr(response, "text", "") or ""
        (logs_dir / "gemini_response.txt").write_text(response_text, encoding="utf-8")
        if not response_text.strip():
            raise RuntimeError("Gemini returned empty response text.")

        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Gemini returned non-JSON response: {exc}") from exc

        (logs_dir / "gemini_parsed.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        return parsed

    def _prepare_upload_path(self, video_path: Path) -> Path:
        suffix = video_path.suffix or ".mp4"
        temp_dir = Path(tempfile.mkdtemp(prefix="gemini_upload_"))
        temp_path = temp_dir / f"demo_upload{suffix}"
        shutil.copy2(video_path, temp_path)
        return temp_path
