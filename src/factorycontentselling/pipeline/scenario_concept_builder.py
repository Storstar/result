from __future__ import annotations

from ..models import ClientBrief, DemoAnalysis, ScenarioConcept, VoiceoverPlan
from ..services.openai_adapter import OpenAIAdapter


def build_scenario_concept(
    client_brief: ClientBrief,
    demo_analysis: DemoAnalysis,
    voiceover_plan: VoiceoverPlan,
    scenario_prompt: str,
) -> ScenarioConcept:
    generated = OpenAIAdapter().generate_scenario_concept(
        client_brief=client_brief,
        demo_analysis=demo_analysis,
        voiceover_plan=voiceover_plan,
        scenario_prompt=scenario_prompt,
    )
    if generated:
        return ScenarioConcept.model_validate(generated)

    opening_segment = voiceover_plan.segments[0].suggested_line if voiceover_plan.segments else client_brief.product_summary
    creator_archetype = client_brief.target_audience
    outline = [segment.suggested_line for segment in voiceover_plan.segments[:4]]
    if len(outline) < 3:
        outline.extend(
            [
                f"Show the user entering the core input in {client_brief.app_name}.",
                "Show the app processing or transforming the input.",
                f"Show the result landing clearly on screen: {client_brief.end_result}.",
            ]
        )
    visual_notes = [
        f"Use the real product demo as the source of truth for the product section.",
        f"Lead with a hook for {client_brief.target_audience}.",
        f"Land the payoff around {client_brief.end_result}.",
    ]
    return ScenarioConcept(
        app_name=client_brief.app_name,
        creative_language=client_brief.creative_language,
        concept_title=f"{client_brief.app_name} demo-driven concept",
        hook_text=opening_segment,
        hook_type="pain",
        creator_archetype=creator_archetype,
        persona_summary=f"A creator speaking to {client_brief.target_audience} with a grounded product-first angle.",
        scenario=client_brief.product_summary,
        problem_frame=client_brief.core_pain,
        payoff=client_brief.end_result,
        voice_style=voiceover_plan.voice_style,
        ugc_opener=opening_segment,
        demo_voiceover_outline=outline[:4],
        demo_voiceover_full_text=voiceover_plan.full_voiceover_draft,
        cta_text=client_brief.cta,
        visual_notes=visual_notes,
        blocked_claims=client_brief.blocked_claims,
        blocked_archetypes=client_brief.blocked_archetypes,
        confidence_notes=demo_analysis.confidence_notes,
    )
