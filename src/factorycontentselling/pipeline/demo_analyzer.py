from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from ..config import get_settings
from ..models import ClientBrief, DemoAnalysis, DetectedStep, KeyMoment
from ..services.ocr import OCRAdapter
from ..services.openai_adapter import OpenAIAdapter
from ..services.video import VideoService


SCREEN_KEYWORDS = {
    "upload": ["upload", "import", "attach", "choose file"],
    "processing": ["loading", "processing", "generating", "please wait", "analyzing"],
    "result": ["done", "result", "share", "export", "complete", "success"],
    "input": ["type", "prompt", "name", "enter", "describe", "create"],
    "editor": ["edit", "settings", "style", "template"],
    "share": ["share", "publish", "send", "download"],
}


def _classify_screen_type(texts: list[str]) -> str:
    blob = " ".join(texts).lower()
    for screen_type, keywords in SCREEN_KEYWORDS.items():
        if any(keyword in blob for keyword in keywords):
            return screen_type
    return "other"


def _guess_user_action(screen_type: str) -> str:
    return {
        "input": "User enters or selects input.",
        "editor": "User adjusts options or content.",
        "upload": "User uploads or imports source material.",
        "processing": "App processes the request.",
        "result": "App reveals the end result.",
        "share": "User can share or export the result.",
        "other": "Screen changes without a clearly classified action.",
    }[screen_type]


def _extract_ui_elements(texts: list[str]) -> list[str]:
    ui_elements: list[str] = []
    for text in texts:
        lowered = text.lower()
        if any(token in lowered for token in ["button", "continue", "next", "generate", "share", "download"]):
            ui_elements.append(text)
        if len(ui_elements) >= 5:
            break
    return ui_elements


def _mean_frame_difference(frame_a_path: Optional[Path], frame_b_path: Path) -> float:
    if frame_a_path is None:
        return 0.0
    try:
        image_a = Image.open(frame_a_path).convert("RGB")
        image_b = Image.open(frame_b_path).convert("RGB")
    except Exception:
        return 0.0
    resized_b = image_b.resize(image_a.size)
    array_a = np.asarray(image_a, dtype=np.int16)
    array_b = np.asarray(resized_b, dtype=np.int16)
    diff = np.abs(array_a - array_b)
    return float(diff.mean())


def analyze_demo_video(video_path: Path, artifacts_dir: Path, client_brief: ClientBrief) -> DemoAnalysis:
    settings = get_settings()
    video_service = VideoService()
    ocr = OCRAdapter()
    openai_adapter = OpenAIAdapter()

    metadata = video_service.inspect(video_path)
    sampled_frames = video_service.sample_frames(
        video_path=video_path,
        output_dir=artifacts_dir / "frames",
        interval_seconds=settings.frame_sample_seconds,
        max_frames=settings.max_analysis_frames,
    )

    transcript = ""
    uncertainties: list[str] = []
    confidence_notes: list[str] = []
    ocr_text_flat: list[str] = []
    detected_steps: list[DetectedStep] = []

    if metadata.has_audio:
        audio_path = video_service.extract_audio(video_path, artifacts_dir / "audio" / "demo_audio.mp3")
        if audio_path is not None:
            transcript = openai_adapter.transcribe_audio(audio_path)
            if not transcript:
                uncertainties.append("Audio exists but transcription is unavailable or failed.")
        else:
            uncertainties.append("Audio extraction failed.")
    else:
        confidence_notes.append("No audio stream detected in the demo.")

    previous_frame_path: Optional[Path] = None
    previous_texts: list[str] = []

    for index, (timestamp, frame_path) in enumerate(sampled_frames, start=1):
        texts = ocr.extract_text(frame_path)
        ocr_text_flat.extend(texts)
        screen_type = _classify_screen_type(texts)
        diff_score = _mean_frame_difference(previous_frame_path, frame_path) if previous_frame_path else 0.0
        notes = []
        if diff_score > 20:
            notes.append(f"Strong visual change from previous sampled frame (diff={diff_score:.1f}).")
        if texts == previous_texts and texts:
            notes.append("OCR text stayed mostly the same across adjacent sample frames.")
        if not texts:
            notes.append("Little or no OCR text detected on this frame.")

        next_timestamp = sampled_frames[index][0] if index < len(sampled_frames) else metadata.duration_seconds
        detected_steps.append(
            DetectedStep(
                step=index,
                timestamp_start=timestamp,
                timestamp_end=round(next_timestamp, 2),
                screen_type=screen_type,
                user_action=_guess_user_action(screen_type),
                visible_text=texts[:10],
                ui_elements=_extract_ui_elements(texts),
                notes=" ".join(notes).strip(),
            )
        )
        previous_frame_path = frame_path
        previous_texts = texts

    if not sampled_frames:
        uncertainties.append("No frames were sampled from the demo video.")

    key_moments: list[KeyMoment] = []
    for step in detected_steps:
        if step.screen_type == "input" and not any(moment.type == "input" for moment in key_moments):
            key_moments.append(KeyMoment(type="input", timestamp=step.timestamp_start, description="First clear input/setup moment."))
        if step.screen_type == "processing" and not any(moment.type == "magic_moment" for moment in key_moments):
            key_moments.append(
                KeyMoment(type="magic_moment", timestamp=step.timestamp_start, description="App appears to process or generate something."))
        if step.screen_type in {"result", "share"} and not any(moment.type == "result" for moment in key_moments):
            key_moments.append(KeyMoment(type="result", timestamp=step.timestamp_start, description="Result or payoff appears on screen."))

    if detected_steps:
        key_moments.insert(0, KeyMoment(type="hook_visual", timestamp=detected_steps[0].timestamp_start, description="Opening screen to anchor the first hook."))
        last_step = detected_steps[-1]
        key_moments.append(KeyMoment(type="cta", timestamp=last_step.timestamp_start, description="Closing visual where CTA can be layered."))

    candidate_voiceover_beats = [
        f"{step.timestamp_start:.2f}-{step.timestamp_end:.2f}s: {step.screen_type} | {step.user_action}"
        for step in detected_steps
    ]

    frame_summary = openai_adapter.summarize_frames(
        [frame_path for _, frame_path in sampled_frames],
        {
            "app_name": client_brief.app_name,
            "product_summary": client_brief.product_summary,
            "target_audience": client_brief.target_audience,
            "core_pain": client_brief.core_pain,
        },
    )

    summary_parts = [
        f"Demo for {client_brief.app_name} sampled across {len(sampled_frames)} frames.",
        f"Detected {len(detected_steps)} coarse step(s) over approximately {metadata.duration_seconds:.1f}s.",
    ]
    if frame_summary and frame_summary.get("summary"):
        summary_parts.append(frame_summary["summary"])
        uncertainties.extend(frame_summary.get("uncertainties", []))
        candidate_voiceover_beats.extend(frame_summary.get("voiceover_notes", []))
    else:
        summary_parts.append(
            "Heuristic analysis only: summary is based on sampled frames, OCR, scene changes, and optional transcript."
        )

    if not ocr.available:
        confidence_notes.append("OCR engine unavailable. Visible text extraction may be sparse.")
    elif not ocr_text_flat:
        confidence_notes.append("OCR ran but recovered little text from sampled frames.")

    walkthrough_marker = ""
    if "Operator walkthrough:" in client_brief.creative_notes:
        walkthrough_marker = client_brief.creative_notes.split("Operator walkthrough:", 1)[1].strip()

    if walkthrough_marker and walkthrough_marker.lower() != "not provided.":
        confidence_notes.append("Client-provided demo walkthrough is available and should be treated as the primary alignment aid for narration.")

    if not transcript:
        confidence_notes.append("No transcript available; voiceover alignment is based on visuals only.")

    summary = " ".join(summary_parts)
    if walkthrough_marker and walkthrough_marker.lower() != "not provided.":
        summary = f"{summary} Manual walkthrough provided: {walkthrough_marker}"

    debug_snapshot = {
        "video_metadata": {
            "duration_seconds": metadata.duration_seconds,
            "fps": metadata.fps,
            "frame_count": metadata.frame_count,
            "width": metadata.width,
            "height": metadata.height,
            "has_audio": metadata.has_audio,
        },
        "sampled_frames": [{"timestamp": ts, "path": str(path)} for ts, path in sampled_frames],
        "frame_summary": frame_summary,
    }
    (artifacts_dir / "analysis_debug.json").write_text(json.dumps(debug_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    return DemoAnalysis(
        summary=summary,
        detected_steps=detected_steps,
        key_moments=key_moments,
        candidate_voiceover_beats=candidate_voiceover_beats,
        uncertainties=uncertainties,
        ocr_text=ocr_text_flat[:200],
        transcript=transcript,
        confidence_notes=confidence_notes,
    )
