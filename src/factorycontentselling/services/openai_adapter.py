from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI

from ..config import get_settings


class OpenAIAdapter:
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = bool(settings.openai_api_key)
        self.vision_model = settings.openai_vision_model
        self.transcription_model = settings.openai_transcription_model
        self._client = OpenAI(api_key=settings.openai_api_key) if self.enabled else None

    def transcribe_audio(self, audio_path: Path) -> str:
        if not self.enabled or self._client is None or not audio_path.exists():
            return ""
        with audio_path.open("rb") as audio_file:
            transcript = self._client.audio.transcriptions.create(
                model=self.transcription_model,
                file=audio_file,
            )
        return getattr(transcript, "text", "") or ""

    def summarize_frames(self, frame_paths: list[Path], context: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not self.enabled or self._client is None or not frame_paths:
            return None

        input_content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": (
                    "Analyze these app demo frames for a creative-ops pipeline. "
                    "Return JSON with keys: summary, likely_flow, wow_moment, "
                    "voiceover_notes, uncertainties. Keep it short and practical.\n"
                    f"Context: {json.dumps(context, ensure_ascii=False)}"
                ),
            }
        ]
        for frame_path in frame_paths[:6]:
            image_b64 = base64.b64encode(frame_path.read_bytes()).decode("utf-8")
            input_content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{image_b64}",
                }
            )

        response = self._client.responses.create(
            model=self.vision_model,
            input=[{"role": "user", "content": input_content}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "demo_frame_analysis",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "likely_flow": {"type": "array", "items": {"type": "string"}},
                            "wow_moment": {"type": "string"},
                            "voiceover_notes": {"type": "array", "items": {"type": "string"}},
                            "uncertainties": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["summary", "likely_flow", "wow_moment", "voiceover_notes", "uncertainties"],
                        "additionalProperties": False,
                    },
                },
            },
        )
        text = response.output_text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
