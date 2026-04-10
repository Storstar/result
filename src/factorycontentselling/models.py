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
    app_icon_note: str = ""
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
    uploaded_icon_name: str = ""
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


class ScenarioConcept(BaseModel):
    app_name: str
    creative_language: str
    concept_title: str
    character_description: str
    environment_description: str
    hook_text: str
    hook_type: str
    post_hook_voiceover: str
    creator_archetype: str
    persona_summary: str
    scenario: str
    problem_frame: str
    payoff: str
    voice_style: str
    ugc_opener: str
    demo_voiceover_outline: list[str]
    demo_voiceover_full_text: str
    cta_text: str
    visual_notes: list[str]
    blocked_claims: list[str]
    blocked_archetypes: list[str]
    confidence_notes: list[str]


class EndCardBanner(BaseModel):
    app_name: str
    background_color: str
    text_color: str
    icon_source: str
    output_image: str
    layout_notes: list[str]


class FinalCreative(BaseModel):
    final_video: str
    hook_image: str
    hook_frame: str
    hook_audio: str
    demo_audio: str
    end_card_audio: str
    creative_manifest: str
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
    app_icon: Path
    demo_walkthrough_voice: Path
    client_brief_json: Path
    demo_analysis_json: Path
    voiceover_plan_json: Path
    scenario_concept_json: Path
    end_card_banner_json: Path
    end_card_banner_png: Path
    hook_image_png: Path
    hook_frame_png: Path
    hook_audio_mp3: Path
    demo_audio_mp3: Path
    end_card_audio_mp3: Path
    final_creative_manifest_json: Path
    final_creative_mp4: Path
    content_factory_bridge_json: Path
    scenario_prompt_txt: Path
    run_summary_json: Path
    result_bundle_zip: Path
