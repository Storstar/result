from __future__ import annotations

import traceback
from typing import Optional

from .models import ClientBrief, DemoAnalysis, RunSummary, VoiceoverPlan
from .pipeline.brief_normalizer import normalize_brief
from .pipeline.demo_analyzer import analyze_demo_video
from .pipeline.scenario_prompt_builder import build_scenario_prompt
from .pipeline.voiceover_planner import build_voiceover_plan
from .storage import SubmissionStorage


class SubmissionOrchestrator:
    def __init__(self, storage: Optional[SubmissionStorage] = None) -> None:
        self.storage = storage or SubmissionStorage()

    def run(self, submission_id: str) -> RunSummary:
        paths = self.storage.paths_for(submission_id)
        warnings: list[str] = []
        errors: list[str] = []

        try:
            intake_record = self._load_intake(submission_id)

            client_brief: ClientBrief = normalize_brief(intake_record)
            self.storage.write_json(paths.client_brief_json, client_brief.model_dump(mode="json"))
            warnings.extend(f"brief: missing {field}" for field in client_brief.missing_fields)

            demo_analysis: DemoAnalysis = analyze_demo_video(paths.demo_video, paths.logs_dir, client_brief)
            self.storage.write_json(paths.demo_analysis_json, demo_analysis.model_dump(mode="json"))
            warnings.extend(demo_analysis.uncertainties)

            voiceover_plan: VoiceoverPlan = build_voiceover_plan(client_brief, demo_analysis)
            self.storage.write_json(paths.voiceover_plan_json, voiceover_plan.model_dump(mode="json"))
            warnings.extend(voiceover_plan.warnings)

            scenario_prompt = build_scenario_prompt(client_brief, demo_analysis, voiceover_plan)
            self.storage.write_text(paths.scenario_prompt_txt, scenario_prompt)
            bundle_path = self.storage.build_result_bundle(submission_id)

            status = "completed"
        except Exception as exc:
            status = "failed"
            errors.append(str(exc))
            traceback_path = paths.logs_dir / "pipeline_error.log"
            traceback_path.write_text(traceback.format_exc(), encoding="utf-8")
            bundle_path = self.storage.build_result_bundle(submission_id)

        run_summary = RunSummary(
            submission_id=submission_id,
            status=status,
            artifacts={
                "intake_json": str(paths.intake_json),
                "demo_video": str(paths.demo_video),
                "client_brief_json": str(paths.client_brief_json),
                "demo_analysis_json": str(paths.demo_analysis_json),
                "voiceover_plan_json": str(paths.voiceover_plan_json),
                "scenario_prompt_txt": str(paths.scenario_prompt_txt),
                "result_bundle_zip": str(bundle_path),
            },
            warnings=sorted(set(warnings)),
            errors=errors,
        )
        self.storage.write_json(paths.run_summary_json, run_summary.model_dump(mode="json"))
        return run_summary

    def _load_intake(self, submission_id: str):
        from .models import IntakeRecord

        paths = self.storage.paths_for(submission_id)
        payload = paths.intake_json.read_text(encoding="utf-8")
        return IntakeRecord.model_validate_json(payload)
