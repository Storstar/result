from __future__ import annotations

import traceback
from typing import Optional

from .models import ClientBrief, DemoAnalysis, EndCardBanner, FinalCreative, RunSummary, VoiceoverPlan
from .pipeline.brief_normalizer import normalize_brief
from .pipeline.demo_analyzer import analyze_demo_video
from .pipeline.end_card_builder import build_end_card_banner
from .pipeline.final_video_builder import build_final_video
from .pipeline.scenario_concept_builder import build_scenario_concept
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

            scenario_concept = build_scenario_concept(client_brief, demo_analysis, voiceover_plan, scenario_prompt)
            self.storage.write_json(paths.scenario_concept_json, scenario_concept.model_dump(mode="json"))

            icon_path = paths.app_icon if paths.app_icon.exists() else None
            end_card_banner: EndCardBanner | None = build_end_card_banner(
                client_brief.app_name,
                client_brief.product_summary,
                icon_path,
                paths.end_card_banner_png,
            )
            if end_card_banner is not None:
                self.storage.write_json(paths.end_card_banner_json, end_card_banner.model_dump(mode="json"))
            else:
                warnings.append("end_card_skipped: no app icon uploaded.")

            final_creative: FinalCreative = build_final_video(paths, scenario_concept)
            warnings.extend(final_creative.warnings)

            content_factory_bridge = {
                "mode": "external_demo_video",
                "concept_source": str(paths.scenario_concept_json),
                "demo_video_source": str(paths.demo_video),
                "end_card_banner_source": str(paths.end_card_banner_png) if paths.end_card_banner_png.exists() else "",
                "final_video_source": str(paths.final_creative_mp4),
                "app_icon_source": str(paths.app_icon) if paths.app_icon.exists() else "",
                "notes": [
                    "Use the user-supplied demo video instead of rendering demo.mp4 from the old internal demo renderer.",
                    "Keep the real demo video as the source of truth for the product section.",
                    "Use the generated end card banner for the final app-name frame only when an app icon was uploaded.",
                    "Final creative is composed as hook image + voiced demo section + end card.",
                ],
            }
            self.storage.write_json(paths.content_factory_bridge_json, content_factory_bridge)
            status = "completed"
        except Exception as exc:
            status = "failed"
            errors.append(str(exc))
            traceback_path = paths.logs_dir / "pipeline_error.log"
            traceback_path.write_text(traceback.format_exc(), encoding="utf-8")

        run_summary = RunSummary(
            submission_id=submission_id,
            status=status,
            artifacts={
                "intake_json": str(paths.intake_json),
                "demo_video": str(paths.demo_video),
                "client_brief_json": str(paths.client_brief_json),
                "demo_analysis_json": str(paths.demo_analysis_json),
                "voiceover_plan_json": str(paths.voiceover_plan_json),
                "scenario_concept_json": str(paths.scenario_concept_json),
                "end_card_banner_json": str(paths.end_card_banner_json) if paths.end_card_banner_json.exists() else "",
                "end_card_banner_png": str(paths.end_card_banner_png) if paths.end_card_banner_png.exists() else "",
                "hook_image_png": str(paths.hook_image_png),
                "hook_frame_png": str(paths.hook_frame_png),
                "hook_audio_mp3": str(paths.hook_audio_mp3),
                "demo_audio_mp3": str(paths.demo_audio_mp3),
                "end_card_audio_mp3": str(paths.end_card_audio_mp3),
                "final_creative_manifest_json": str(paths.final_creative_manifest_json),
                "final_creative_mp4": str(paths.final_creative_mp4),
                "content_factory_bridge_json": str(paths.content_factory_bridge_json),
                "scenario_prompt_txt": str(paths.scenario_prompt_txt),
                "result_bundle_zip": "",
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
