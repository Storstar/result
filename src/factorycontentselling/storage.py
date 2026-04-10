from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .config import get_settings
from .models import IntakeRecord, SubmissionPaths


class SubmissionStorage:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        settings = get_settings()
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
            demo_walkthrough_voice=raw_dir / "demo_walkthrough.ogg",
            client_brief_json=derived_dir / "client_brief.json",
            demo_analysis_json=derived_dir / "demo_analysis.json",
            voiceover_plan_json=derived_dir / "voiceover_plan.json",
            scenario_prompt_txt=derived_dir / "scenario_prompt.txt",
            run_summary_json=derived_dir / "run_summary.json",
        )

    def save_intake(self, submission_id: str, record: IntakeRecord) -> SubmissionPaths:
        paths = self.paths_for(submission_id)
        self.write_json(paths.intake_json, record.model_dump(mode="json"))
        return paths

    def save_uploaded_video(self, submission_id: str, source_path: Path) -> Path:
        paths = self.paths_for(submission_id)
        shutil.copy2(source_path, paths.demo_video)
        return paths.demo_video

    def write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
