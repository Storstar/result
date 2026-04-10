from __future__ import annotations

from ..models import ClientBrief, DemoAnalysis, VoiceoverPlan


def build_scenario_prompt(
    client_brief: ClientBrief,
    demo_analysis: DemoAnalysis,
    voiceover_plan: VoiceoverPlan,
) -> str:
    step_lines = []
    for step in demo_analysis.detected_steps:
        visible_text = ", ".join(step.visible_text[:5]) or "no clear OCR text"
        step_lines.append(
            f"- {step.timestamp_start:.2f}-{step.timestamp_end:.2f}s | {step.screen_type} | "
            f"{step.user_action} | visible text: {visible_text}"
        )

    voiceover_lines = []
    for segment in voiceover_plan.segments:
        voiceover_lines.append(
            f"- {segment.timestamp_start:.2f}-{segment.timestamp_end:.2f}s | {segment.line_type} | "
            f"{segment.goal} | suggested line: {segment.suggested_line}"
        )

    blocked_claims = ", ".join(client_brief.blocked_claims) or "none provided"
    blocked_archetypes = ", ".join(client_brief.blocked_archetypes) or "none provided"
    allowed_archetypes = ", ".join(client_brief.allowed_archetypes) or "not specified"
    uncertainties = "\n".join(f"- {item}" for item in demo_analysis.uncertainties) or "- none"
    creative_notes = client_brief.creative_notes
    walkthrough = creative_notes.split("Operator walkthrough:", 1)[1].split("Extra project context:", 1)[0].strip() if "Operator walkthrough:" in creative_notes else "Not provided"
    extra_context = creative_notes.split("Extra project context:", 1)[1].strip() if "Extra project context:" in creative_notes else "Not provided"

    return f"""You are writing short-form ad concepts for an app demo-driven creative pipeline.

Objective
Create scenario directions and ad concept outputs that stay tightly grounded in the actual demo footage.
Do not invent product capabilities that are not visible or stated in the brief.

Product
- App name: {client_brief.app_name}
- Product summary: {client_brief.product_summary}
- Target audience: {client_brief.target_audience}
- Core pain: {client_brief.core_pain}
- End result: {client_brief.end_result}
- Creative language: {client_brief.creative_language}
- Desired tone: {client_brief.tone}
- CTA: {client_brief.cta}

Creative Boundaries
- Allowed archetypes: {allowed_archetypes}
- Blocked archetypes/styles: {blocked_archetypes}
- Blocked claims/legal constraints: {blocked_claims}
- Additional notes: {client_brief.creative_notes}
- Input constraints: {", ".join(client_brief.input_constraints) or "none"}

Demo Analysis
- Summary: {demo_analysis.summary}
- Transcript: {demo_analysis.transcript or "No transcript available"}
- Confidence notes: {", ".join(demo_analysis.confidence_notes) or "none"}
- Client walkthrough: {walkthrough}
- Extra project context: {extra_context}

Detected Demo Flow
{chr(10).join(step_lines)}

Key Moments
{chr(10).join(f"- {moment.type} at {moment.timestamp:.2f}s: {moment.description}" for moment in demo_analysis.key_moments)}

Voiceover Planning Constraints
- Overall angle: {voiceover_plan.overall_angle}
- Voice style: {voiceover_plan.voice_style}
- Full voiceover draft: {voiceover_plan.full_voiceover_draft}

Voiceover Beat Map
{chr(10).join(voiceover_lines)}

Writing Instructions
- Build hooks that connect immediately to the user's pain, but anchor them in what the demo visibly supports.
- If a creator-supplied walkthrough exists, use it as the main source of truth for click-by-click narration.
- Read the extra project context carefully and use it to fill gaps in positioning, links, restrictions, or audience nuance.
- Respect the demo timeline. Voiceover should feel synchronized to the on-screen actions.
- Call out input/setup moments when they matter, then accelerate toward the processing and result moments.
- Use the result screen as the proof/payoff moment.
- Keep claims realistic and avoid anything in the blocked claims list.
- Use allowed archetypes only if they support the tone and product truth.
- Avoid blocked archetypes even as parody.
- Treat low-confidence demo zones carefully. If a section is uncertain, use broader wording instead of fake specificity.
- End with the provided CTA or a very close variant.

Low-Confidence / Human Review Notes
{uncertainties}
"""
