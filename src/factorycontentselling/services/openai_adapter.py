from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI
from PIL import Image

from ..config import get_settings


class OpenAIAdapter:
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = bool(settings.openai_api_key)
        self.vision_model = settings.openai_vision_model
        self.transcription_model = settings.openai_transcription_model
        self.image_model = settings.openai_image_model
        self.speech_model = settings.openai_speech_model
        self.speech_voice = settings.openai_speech_voice
        self._client = OpenAI(api_key=settings.openai_api_key, timeout=60.0, max_retries=2) if self.enabled else None

    def _log_openai_error(self, operation: str, exc: Exception) -> None:
        log_path = get_settings().submissions_dir / "_openai_errors.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{operation}: {type(exc).__name__}: {exc}\n")

    def _encode_frame_for_openai(self, frame_path: Path, max_side: int = 768, quality: int = 70) -> str:
        with Image.open(frame_path) as image:
            converted = image.convert("RGB")
            converted.thumbnail((max_side, max_side))
            import io

            buffer = io.BytesIO()
            converted.save(buffer, format="JPEG", quality=quality, optimize=True)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def transcribe_audio(self, audio_path: Path) -> str:
        if not self.enabled or self._client is None or not audio_path.exists():
            return ""
        try:
            with audio_path.open("rb") as audio_file:
                transcript = self._client.audio.transcriptions.create(
                    model=self.transcription_model,
                    file=audio_file,
                )
            return getattr(transcript, "text", "") or ""
        except Exception as exc:
            self._log_openai_error("transcribe_audio", exc)
            raise RuntimeError(f"OpenAI transcription failed: {exc}") from exc

    def generate_image(self, prompt: str, output_path: Path) -> Optional[Path]:
        if not self.enabled or self._client is None:
            return None
        try:
            response = self._client.images.generate(
                model=self.image_model,
                prompt=prompt,
                size="1024x1536",
                quality="medium",
                output_format="png",
            )
            image_data = getattr(response.data[0], "b64_json", None) if getattr(response, "data", None) else None
        except Exception as exc:
            self._log_openai_error("generate_image", exc)
            return None
        if not image_data:
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(image_data))
        return output_path

    def synthesize_speech(self, text: str, output_path: Path, *, instructions: str = "") -> Optional[Path]:
        if not self.enabled or self._client is None or not text.strip():
            return None
        try:
            response = self._client.audio.speech.create(
                model=self.speech_model,
                voice=self.speech_voice,
                input=text,
                instructions=instructions or "Natural creator ad voice.",
                response_format="mp3",
            )
        except Exception as exc:
            self._log_openai_error("synthesize_speech", exc)
            raise RuntimeError(f"OpenAI speech synthesis failed: {exc}") from exc
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.read())
        return output_path

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
        for frame_path in frame_paths[:4]:
            image_b64 = self._encode_frame_for_openai(frame_path)
            input_content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{image_b64}",
                }
            )

        try:
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
        except Exception as exc:
            self._log_openai_error("summarize_frames", exc)
            raise RuntimeError(f"OpenAI frame summary failed: {exc}") from exc
        text = response.output_text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def generate_scenario_concept(
        self,
        *,
        client_brief: Any,
        demo_analysis: Any,
        voiceover_plan: Any,
        scenario_prompt: str,
    ) -> Optional[dict[str, Any]]:
        if not self.enabled or self._client is None:
            return None

        try:
            response = self._client.responses.create(
                model=self.vision_model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Build one structured scenario concept for a short-form app ad pipeline. "
                                    "The concept must stay grounded in the provided app brief, demo analysis, and voiceover plan. "
                                    "Do not invent product capabilities that are not supported by the prompt.\n\n"
                                    f"Scenario prompt:\n{scenario_prompt}\n\n"
                                    f"Client brief: {json.dumps(client_brief.model_dump(mode='json'), ensure_ascii=False)}\n\n"
                                    f"Demo analysis: {json.dumps(demo_analysis.model_dump(mode='json'), ensure_ascii=False)}\n\n"
                                    f"Voiceover plan: {json.dumps(voiceover_plan.model_dump(mode='json'), ensure_ascii=False)}"
                                ),
                            }
                        ],
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "scenario_concept",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "app_name": {"type": "string"},
                                "creative_language": {"type": "string"},
                                "concept_title": {"type": "string"},
                                "character_description": {"type": "string"},
                                "environment_description": {"type": "string"},
                                "hook_text": {"type": "string"},
                                "hook_type": {"type": "string", "enum": ["pain", "curiosity", "flex", "mistake", "speed", "replacement"]},
                                "post_hook_voiceover": {"type": "string"},
                                "creator_archetype": {"type": "string"},
                                "persona_summary": {"type": "string"},
                                "scenario": {"type": "string"},
                                "problem_frame": {"type": "string"},
                                "payoff": {"type": "string"},
                                "voice_style": {"type": "string"},
                                "ugc_opener": {"type": "string"},
                                "demo_voiceover_outline": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 4},
                                "demo_voiceover_full_text": {"type": "string"},
                                "cta_text": {"type": "string"},
                                "visual_notes": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 6},
                                "blocked_claims": {"type": "array", "items": {"type": "string"}},
                                "blocked_archetypes": {"type": "array", "items": {"type": "string"}},
                                "confidence_notes": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": [
                                "app_name",
                                "creative_language",
                                "concept_title",
                                "character_description",
                                "environment_description",
                                "hook_text",
                                "hook_type",
                                "post_hook_voiceover",
                                "creator_archetype",
                                "persona_summary",
                                "scenario",
                                "problem_frame",
                                "payoff",
                                "voice_style",
                                "ugc_opener",
                                "demo_voiceover_outline",
                                "demo_voiceover_full_text",
                                "cta_text",
                                "visual_notes",
                                "blocked_claims",
                                "blocked_archetypes",
                                "confidence_notes",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
            )
        except Exception as exc:
            self._log_openai_error("generate_scenario_concept", exc)
            raise RuntimeError(f"OpenAI scenario concept failed: {exc}") from exc
        text = response.output_text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
