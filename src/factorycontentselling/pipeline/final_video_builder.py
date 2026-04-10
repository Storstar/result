from __future__ import annotations

import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from ..models import FinalCreative, ScenarioConcept, SubmissionPaths
from ..services.openai_adapter import OpenAIAdapter


def _safe_filename_text(value: str) -> str:
    return " ".join(value.strip().split())


def _duration_seconds(media_path: Path) -> float:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [ffmpeg_path, "-i", str(media_path)],
        capture_output=True,
        text=True,
    )
    stderr = result.stderr
    marker = "Duration:"
    if marker not in stderr:
        return 0.0
    try:
        chunk = stderr.split(marker, 1)[1].split(",", 1)[0].strip()
        hours, minutes, seconds = chunk.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except Exception:
        return 0.0


def _create_fallback_hook_image(output_path: Path, app_name: str, scenario_concept: ScenarioConcept) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (1024, 1536), (17, 24, 39))
    draw = ImageDraw.Draw(canvas)
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 64)
        body_font = ImageFont.truetype("DejaVuSans.ttf", 34)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
    draw.text((80, 120), _safe_filename_text(app_name), fill=(255, 255, 255), font=title_font)
    draw.multiline_text(
        (80, 260),
        _safe_filename_text(scenario_concept.character_description),
        fill=(229, 231, 235),
        font=body_font,
        spacing=10,
    )
    draw.multiline_text(
        (80, 520),
        _safe_filename_text(scenario_concept.environment_description),
        fill=(156, 163, 175),
        font=body_font,
        spacing=10,
    )
    canvas.save(output_path, format="PNG")


def _build_hook_frame(hook_image_path: Path, hook_text: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(hook_image_path) as raw_image:
        image = raw_image.convert("RGB")
        target_size = (1080, 1920)
        image = image.resize(target_size)
        overlay = Image.new("RGBA", target_size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        for index in range(8):
            alpha = 18 + index * 16
            y_start = 1200 + index * 90
            overlay_draw.rectangle((0, y_start, 1080, 1920), fill=(0, 0, 0, alpha))
        combined = Image.alpha_composite(image.convert("RGBA"), overlay)
        draw = ImageDraw.Draw(combined)
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 74)
        except Exception:
            font = ImageFont.load_default()
        text = _safe_filename_text(hook_text)[:220]
        max_width = 920
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), trial, font=font)
            if bbox[2] - bbox[0] <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        rendered = "\n".join(lines[:4])
        draw.multiline_text((80, 1260), rendered, fill=(255, 255, 255), font=font, spacing=16)
        combined.convert("RGB").save(output_path, format="PNG")
    return output_path


def _run_ffmpeg(args: list[str]) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ffmpeg_path, *args], check=True, capture_output=True, text=True)


def _render_still_segment(image_path: Path, audio_path: Path, output_path: Path, min_duration: float) -> Path:
    duration = max(min_duration, _duration_seconds(audio_path) + 0.25)
    _run_ffmpeg(
        [
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-t",
            f"{duration:.2f}",
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ]
    )
    return output_path


def _render_demo_segment(demo_video_path: Path, demo_audio_path: Path, output_path: Path) -> Path:
    duration = _duration_seconds(demo_audio_path)
    extra = []
    if duration > 0:
        extra = ["-t", f"{duration:.2f}"]
    _run_ffmpeg(
        [
            "-y",
            "-i",
            str(demo_video_path),
            "-i",
            str(demo_audio_path),
            *extra,
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ]
    )
    return output_path


def _concat_segments(segment_paths: list[Path], output_path: Path) -> Path:
    concat_file = output_path.with_suffix(".txt")
    concat_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in segment_paths), encoding="utf-8")
    _run_ffmpeg(
        [
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(output_path),
        ]
    )
    return output_path


def build_final_video(paths: SubmissionPaths, scenario_concept: ScenarioConcept) -> FinalCreative:
    adapter = OpenAIAdapter()
    warnings: list[str] = []

    image_prompt = (
        f"Vertical cinematic UGC ad still. One believable creator on camera. "
        f"Character: {scenario_concept.character_description}. "
        f"Environment: {scenario_concept.environment_description}. "
        f"Persona: {scenario_concept.persona_summary}. "
        f"Natural smartphone-shot realism, clean face visibility, strong ad hook energy, no UI, no app screenshot, no text."
    )
    hook_image_path = adapter.generate_image(image_prompt, paths.hook_image_png)
    if hook_image_path is None:
        warnings.append("hook_image_generation_failed")
        _create_fallback_hook_image(paths.hook_image_png, scenario_concept.app_name, scenario_concept)
        hook_image_path = paths.hook_image_png

    hook_frame_path = _build_hook_frame(hook_image_path, scenario_concept.hook_text, paths.hook_frame_png)

    voice_instructions = f"Short-form ad voice. {scenario_concept.voice_style}. Keep it natural, confident, creator-like."
    hook_audio = adapter.synthesize_speech(
        scenario_concept.hook_text,
        paths.hook_audio_mp3,
        instructions=voice_instructions,
    )
    if hook_audio is None:
        raise RuntimeError("Failed to generate hook audio.")

    demo_text = " ".join(
        part.strip()
        for part in [scenario_concept.post_hook_voiceover, scenario_concept.demo_voiceover_full_text]
        if part.strip()
    )
    demo_audio = adapter.synthesize_speech(
        demo_text,
        paths.demo_audio_mp3,
        instructions=voice_instructions,
    )
    if demo_audio is None:
        raise RuntimeError("Failed to generate demo voiceover audio.")

    hook_segment = paths.logs_dir / "hook_segment.mp4"
    demo_segment = paths.logs_dir / "demo_segment.mp4"

    _render_still_segment(hook_frame_path, hook_audio, hook_segment, min_duration=3.0)
    _render_demo_segment(paths.demo_video, demo_audio, demo_segment)

    end_card_text = ""
    end_card_audio: Path | None = None
    end_card_segment = paths.logs_dir / "end_card_segment.mp4"
    segment_paths = [hook_segment, demo_segment]
    if paths.end_card_banner_png.exists():
        end_card_text = " ".join(
            part.strip().rstrip(".") + "."
            for part in [scenario_concept.cta_text, scenario_concept.app_name]
            if part.strip()
        )
        end_card_audio = adapter.synthesize_speech(
            end_card_text,
            paths.end_card_audio_mp3,
            instructions="Short closing CTA for a mobile ad. Clear and direct.",
        )
        if end_card_audio is None:
            raise RuntimeError("Failed to generate end-card audio.")
        _render_still_segment(paths.end_card_banner_png, end_card_audio, end_card_segment, min_duration=2.4)
        segment_paths.append(end_card_segment)
    else:
        warnings.append("end_card_segment_skipped")

    _concat_segments(segment_paths, paths.final_creative_mp4)

    manifest = {
        "hook_image_prompt": image_prompt,
        "hook_text": scenario_concept.hook_text,
        "demo_text": demo_text,
        "end_card_text": end_card_text,
        "segments": {
            "hook_segment": str(hook_segment),
            "demo_segment": str(demo_segment),
            "end_card_segment": str(end_card_segment) if end_card_audio is not None else "",
        },
        "warnings": warnings,
    }
    paths.final_creative_manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return FinalCreative(
        final_video=str(paths.final_creative_mp4),
        hook_image=str(hook_image_path),
        hook_frame=str(hook_frame_path),
        hook_audio=str(hook_audio),
        demo_audio=str(demo_audio),
        end_card_audio=str(end_card_audio) if end_card_audio is not None else "",
        creative_manifest=str(paths.final_creative_manifest_json),
        warnings=warnings,
    )
