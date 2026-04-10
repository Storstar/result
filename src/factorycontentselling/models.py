from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IntakeAnswers(BaseModel):
    app_name: str = ""
    product_summary: str = ""
    target_audience: str = ""
    core_pain: str = ""
    end_result: str = ""
    creative_language: str = ""
    blocked_archetypes: str = ""
    blocked_claims: str = ""
    cta: str = ""
    demo_walkthrough: str = ""
    extra_project_context: str = ""


class SubmissionMetadata(BaseModel):
    submission_id: str
    created_at: str = Field(default_factory=utc_now_iso)
    source: str = "telegram"
    telegram_user_id: Optional[int] = None
    telegram_username: Optional[str] = None
    telegram_chat_id: Optional[int] = None
    uploaded_video_name: str = "demo.mp4"
    status: str = "received"


class IntakeRecord(BaseModel):
    metadata: SubmissionMetadata
    answers: IntakeAnswers
    raw_updates: list[dict[str, Any]] = Field(default_factory=list)


class ClientBrief(BaseModel):
    app_name: str
    product_summary: str
    target_audience: str
    core_pain: str
    end_result: str
    creative_language: str
    tone: str
    allowed_archetypes: list[str]
    blocked_archetypes: list[str]
    blocked_claims: list[str]
    cta: str
    links: dict[str, str]
    creative_notes: str
    input_constraints: list[str]
    missing_fields: list[str]


class DetectedStep(BaseModel):
    step: int
    timestamp_start: float
    timestamp_end: float
    screen_type: str
    user_action: str
    visible_text: list[str]
    ui_elements: list[str]
    notes: str


class KeyMoment(BaseModel):
    type: str
    timestamp: float
    description: str


class DemoAnalysis(BaseModel):
    summary: str
    detected_steps: list[DetectedStep]
    key_moments: list[KeyMoment]
    candidate_voiceover_beats: list[str]
    uncertainties: list[str]
    ocr_text: list[str]
    transcript: str
    confidence_notes: list[str]


class VoiceoverSegment(BaseModel):
    timestamp_start: float
    timestamp_end: float
    goal: str
    what_happens_on_screen: str
    suggested_line: str
    line_type: str


class VoiceoverPlan(BaseModel):
    overall_angle: str
    voice_style: str
    segments: list[VoiceoverSegment]
    full_voiceover_draft: str
    warnings: list[str]


class RunSummary(BaseModel):
    submission_id: str
    status: str
    created_at: str = Field(default_factory=utc_now_iso)
    artifacts: dict[str, str]
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class SubmissionPaths(BaseModel):
    root: Path
    raw_dir: Path
    derived_dir: Path
    logs_dir: Path
    intake_json: Path
    demo_video: Path
    demo_walkthrough_voice: Path
    client_brief_json: Path
    demo_analysis_json: Path
    voiceover_plan_json: Path
    scenario_prompt_txt: Path
    run_summary_json: Path
