from __future__ import annotations

from ..models import ClientBrief, DemoAnalysis, VoiceoverPlan, VoiceoverSegment


def build_voiceover_plan(client_brief: ClientBrief, demo_analysis: DemoAnalysis) -> VoiceoverPlan:
    segments: list[VoiceoverSegment] = []
    warnings = list(demo_analysis.uncertainties)

    for index, step in enumerate(demo_analysis.detected_steps):
        if index == 0:
            goal = "Hook the viewer fast."
            line_type = "hook"
            suggested_line = (
                f"{client_brief.target_audience} can stop fighting {client_brief.core_pain.lower()}."
            )
        elif step.screen_type in {"input", "editor", "upload"}:
            goal = "Explain the setup without talking over the UI too much."
            line_type = "explain"
            suggested_line = (
                f"Here the user gives {client_brief.app_name} the exact input it needs to do the heavy lifting."
            )
        elif step.screen_type == "processing":
            goal = "Underline the magic moment."
            line_type = "transition"
            suggested_line = f"This is where the app turns a messy task into a fast, structured outcome."
        elif step.screen_type in {"result", "share"}:
            goal = "Land the payoff and value."
            line_type = "proof" if index < len(demo_analysis.detected_steps) - 1 else "cta"
            suggested_line = (
                f"And the user gets {client_brief.end_result.lower()} without extra back-and-forth."
                if line_type == "proof"
                else client_brief.cta
            )
        else:
            goal = "Bridge the viewer to the next beat."
            line_type = "transition"
            suggested_line = f"The flow stays simple, fast, and focused on the result."

        segments.append(
            VoiceoverSegment(
                timestamp_start=step.timestamp_start,
                timestamp_end=step.timestamp_end,
                goal=goal,
                what_happens_on_screen=f"{step.screen_type}: {step.user_action}",
                suggested_line=suggested_line,
                line_type=line_type,
            )
        )

    if segments and segments[-1].line_type != "cta":
        last = segments[-1]
        segments[-1] = VoiceoverSegment(
            timestamp_start=last.timestamp_start,
            timestamp_end=last.timestamp_end,
            goal="Close with the CTA.",
            what_happens_on_screen=last.what_happens_on_screen,
            suggested_line=client_brief.cta,
            line_type="cta",
        )

    full_voiceover_draft = " ".join(segment.suggested_line for segment in segments)
    overall_angle = (
        f"{client_brief.app_name} helps {client_brief.target_audience} move from "
        f"{client_brief.core_pain.lower()} to {client_brief.end_result.lower()}."
    )
    voice_style = f"{client_brief.tone} with tight alignment to on-screen product actions"

    if demo_analysis.confidence_notes:
        warnings.extend(demo_analysis.confidence_notes)

    return VoiceoverPlan(
        overall_angle=overall_angle,
        voice_style=voice_style,
        segments=segments,
        full_voiceover_draft=full_voiceover_draft,
        warnings=warnings,
    )

