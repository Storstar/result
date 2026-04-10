from __future__ import annotations

from ..models import ClientBrief, IntakeRecord


def _split_csv(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.replace("\n", ",").split(",") if item.strip()]


def normalize_brief(record: IntakeRecord) -> ClientBrief:
    answers = record.answers
    missing_fields: list[str] = []

    def normalized_value(value: str, default: str, field_name: str) -> str:
        cleaned = value.strip()
        if cleaned:
            return cleaned
        missing_fields.append(field_name)
        return default

    extra_context = answers.extra_project_context.strip()
    urls = [token.strip(".,;()[]<>") for token in extra_context.split() if token.startswith("http")]
    optional_link = urls[0] if urls else ""
    links = {
        "website": optional_link if optional_link.startswith("http") else "",
        "app_store": optional_link if "app" in optional_link.lower() and "store" in optional_link.lower() else "",
        "landing_page": optional_link if optional_link.startswith("http") else "",
    }

    blocked_claims = _split_csv(answers.blocked_claims)
    blocked_archetypes = _split_csv(answers.blocked_archetypes)

    if not answers.blocked_claims.strip():
        missing_fields.append("blocked_claims")

    product_summary = normalized_value(
        answers.product_summary,
        "The app helps users complete a core task faster and with less friction.",
        "product_summary",
    )
    target_audience = normalized_value(
        answers.target_audience,
        "Busy mobile-first users who want a faster way to solve the problem.",
        "target_audience",
    )
    core_pain = normalized_value(
        answers.core_pain,
        "The existing way of getting this done is too slow, messy, or manual.",
        "core_pain",
    )
    end_result = normalized_value(
        answers.end_result,
        "The user reaches a clean result they can use or share immediately.",
        "end_result",
    )
    creative_language = normalized_value(answers.creative_language, "English", "creative_language")
    cta = normalized_value(answers.cta, "Try it now.", "cta")

    creative_notes = (
        f"Generate creative artifacts in {creative_language}. Use a clear, product-grounded tone. Keep claims grounded in the demo. "
        "Tie voiceover beats closely to the visible product actions. "
        f"Operator walkthrough: {answers.demo_walkthrough.strip() or 'Not provided.'} "
        f"Extra project context: {extra_context or 'Not provided.'}"
    )

    input_constraints = []
    if blocked_claims:
        input_constraints.append("Do not use blocked claims verbatim or imply them indirectly.")
    if blocked_archetypes:
        input_constraints.append("Avoid blocked heroes/archetypes in hooks, casting, and copy.")
    if answers.demo_walkthrough.strip():
        input_constraints.append("Prefer the creator-provided walkthrough over shaky visual guesses when aligning voiceover to clicks.")
    if extra_context:
        input_constraints.append("Review the extra project context before writing hooks, CTA framing, and claims.")

    return ClientBrief(
        app_name=normalized_value(answers.app_name, "Unknown App", "app_name"),
        product_summary=product_summary,
        target_audience=target_audience,
        core_pain=core_pain,
        end_result=end_result,
        creative_language=creative_language,
        tone="clear, product-grounded",
        allowed_archetypes=[],
        blocked_archetypes=blocked_archetypes,
        blocked_claims=blocked_claims,
        cta=cta,
        links=links,
        creative_notes=creative_notes,
        input_constraints=input_constraints,
        missing_fields=missing_fields,
    )
