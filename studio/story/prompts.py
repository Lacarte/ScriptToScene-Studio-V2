"""Prompt templates for story generation."""

from studio.build_scene_blueprints.templates import STORY_CATEGORIES, TEMPLATES_BY_ID  # noqa: F401 — re-exported

# Approximate words per second for spoken narration at 1.0x speed
WORDS_PER_SECOND = 2.5


def compute_word_target(duration_seconds: int) -> int:
    """Compute approximate word count target from duration."""
    return max(20, round(duration_seconds * WORDS_PER_SECOND))


def build_story_system_prompt(
    preset_style: str,
    story_category: str,
    duration: int,
    language: str,
    story_tone: str = None,
) -> str:
    """Build the system prompt for the LLM story generation call."""
    word_target = compute_word_target(duration)

    # Resolve style description
    template = TEMPLATES_BY_ID.get(preset_style, {})
    style_name = template.get("name", preset_style)
    style_desc = template.get("description", "")

    # Resolve story tone (from niche system)
    tone_line = ""
    if story_tone:
        from studio.niches.presets import STORY_TONES
        tone_desc = STORY_TONES.get(story_tone, "")
        if tone_desc:
            tone_line = f"NARRATION TONE: {story_tone} — {tone_desc}\n"

    return (
        f"You are a viral short-form content writer specializing in {story_category} stories.\n"
        f"Your stories are designed for {duration}-second spoken narration videos.\n\n"
        f"VISUAL STYLE: {style_name} — {style_desc}\n"
        f"{tone_line}"
        f"Match the emotional tone and vocabulary to this visual style.\n\n"
        f"Write in {language}. Target approximately {word_target} words total.\n\n"
        "OUTPUT STRUCTURE (mandatory — use these exact labels):\n"
        "Hook: [1-2 sentences — immediate attention grab, pattern interrupt, or shocking statement]\n\n"
        "Build: [Core narrative — context, tension, escalation. This is the longest section.]\n\n"
        "Climax: [Peak moment — the twist, revelation, or emotional peak]\n\n"
        "CTA: [1 sentence — call to action, question, or cliffhanger for engagement]\n\n"
        "RULES:\n"
        "- Plain text only. No markdown, no formatting, no emojis, no asterisks.\n"
        "- Write as spoken narration — short sentences, conversational rhythm.\n"
        "- Each section MUST be labeled exactly as shown: Hook: / Build: / Climax: / CTA:\n"
        f"- Total word count must be within ±10% of {word_target} words.\n"
        f"- Write entirely in {language}.\n"
        "- Do not include any meta-commentary or instructions in the output.\n"
    )


def build_story_user_prompt(
    preset_style: str,
    story_category: str,
    duration: int,
    language: str,
    idea: str = None,
) -> str:
    """Build the user prompt for the story generation call."""
    word_target = compute_word_target(duration)
    base = (
        f"Write a viral {story_category} story for a {duration}-second video. "
        f"Target: {word_target} words. Language: {language}. Style: {preset_style}."
    )
    if idea:
        base += f"\n\nBuild the story around this idea:\n{idea}"
    return base
