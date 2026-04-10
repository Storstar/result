from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    openai_vision_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_VISION_MODEL")
    openai_transcription_model: str = Field(default="gpt-4o-mini-transcribe", alias="OPENAI_TRANSCRIPTION_MODEL")
    openai_image_model: str = Field(default="gpt-image-1", alias="OPENAI_IMAGE_MODEL")
    openai_speech_model: str = Field(default="gpt-4o-mini-tts", alias="OPENAI_SPEECH_MODEL")
    openai_speech_voice: str = Field(default="alloy", alias="OPENAI_SPEECH_VOICE")
    demo_analyzer_provider: str = Field(default="heuristic", alias="DEMO_ANALYZER_PROVIDER")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_timeout_seconds: int = Field(default=120, alias="GEMINI_TIMEOUT_SECONDS")
    submissions_dir: Path = Field(default=Path("submissions"), alias="SUBMISSIONS_DIR")
    frame_sample_seconds: float = Field(default=1.5, alias="FRAME_SAMPLE_SECONDS")
    max_analysis_frames: int = Field(default=12, alias="MAX_ANALYSIS_FRAMES")
    max_demo_seconds: int = Field(default=20, alias="MAX_DEMO_SECONDS")
    submission_retention_days: int = Field(default=7, alias="SUBMISSION_RETENTION_DAYS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
