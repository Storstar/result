from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .config import get_settings
from .models import IntakeRecord, SubmissionPaths


class SubmissionStorage:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        settings = get_settings()
        self.settings = settings
        self.base_dir = (base_dir or settings.submissions_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def new_submission_id(self) -> str:
        return uuid4().hex[:12]

    def paths_for(self, submission_id: str) -> SubmissionPaths:
        root = self.base_dir / submission_id
        raw_dir = root / "raw"
        derived_dir = root / "derived"
        logs_dir = root / "logs"
        for path in (raw_dir, derived_dir, logs_dir):
            path.mkdir(parents=True, exist_ok=True)
        return SubmissionPaths(
            root=root,
            raw_dir=raw_dir,
            derived_dir=derived_dir,
            logs_dir=logs_dir,
            intake_json=raw_dir / "intake.json",
            demo_video=raw_dir / "demo.mp4",
            app_icon=raw_dir / "app_icon.png",
            demo_walkthrough_voice=raw_dir / "demo_walkthrough.ogg",
            client_brief_json=derived_dir / "client_brief.json",
            demo_analysis_json=derived_dir / "demo_analysis.json",
            voiceover_plan_json=derived_dir / "voiceover_plan.json",
            scenario_concept_json=derived_dir / "scenario_concept.json",
            end_card_banner_json=derived_dir / "end_card_banner.json",
            end_card_banner_png=derived_dir / "end_card_banner.png",
            hook_image_png=derived_dir / "hook_image.png",
            hook_frame_png=derived_dir / "hook_frame.png",
            hook_audio_mp3=derived_dir / "hook_audio.mp3",
            demo_audio_mp3=derived_dir / "demo_audio.mp3",
            end_card_audio_mp3=derived_dir / "end_card_audio.mp3",
            final_creative_manifest_json=derived_dir / "final_creative_manifest.json",
            final_creative_mp4=derived_dir / "final_creative.mp4",
            content_factory_bridge_json=derived_dir / "content_factory_bridge.json",
            scenario_prompt_txt=derived_dir / "scenario_prompt.txt",
            run_summary_json=derived_dir / "run_summary.json",
            result_bundle_zip=root / "result_bundle.zip",
        )

    def save_intake(self, submission_id: str, record: IntakeRecord) -> SubmissionPaths:
        paths = self.paths_for(submission_id)
        self.write_json(paths.intake_json, record.model_dump(mode="json"))
        return paths

    def save_uploaded_video(self, submission_id: str, source_path: Path) -> Path:
        paths = self.paths_for(submission_id)
        shutil.copy2(source_path, paths.demo_video)
        return paths.demo_video

    def save_uploaded_icon(self, submission_id: str, source_path: Path) -> Path:
        paths = self.paths_for(submission_id)
        shutil.copy2(source_path, paths.app_icon)
        return paths.app_icon

    def write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def build_result_bundle(self, submission_id: str) -> Path:
        paths = self.paths_for(submission_id)
        archive_base = paths.result_bundle_zip.with_suffix("")
        archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=paths.root, base_dir=".")
        return Path(archive_path)

    def cleanup_old_submissions(self, retention_days: Optional[int] = None) -> list[Path]:
        days = self.settings.submission_retention_days if retention_days is None else retention_days
        if days < 0:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        deleted: list[Path] = []
        for submission_dir in self.base_dir.iterdir():
            if not submission_dir.is_dir():
                continue
            last_modified = datetime.fromtimestamp(submission_dir.stat().st_mtime, tz=timezone.utc)
            if last_modified >= cutoff:
                continue
            shutil.rmtree(submission_dir, ignore_errors=True)
            deleted.append(submission_dir)
        return deleted
