"""Prompt templates for story generation."""

import random
import string

from studio.build_scene_blueprints.templates import STORY_CATEGORIES, TEMPLATES_BY_ID  # noqa: F401 — re-exported

# Approximate words per second for spoken narration at 1.0x speed
WORDS_PER_SECOND = 2.5


def compute_word_target(duration_seconds: int) -> int:
    """Compute approximate word count target from duration."""
    return max(20, round(duration_seconds * WORDS_PER_SECOND))


LANGUAGE_LEVEL_HINTS = {
    "beginner": "Use very simple vocabulary, short sentences (5-8 words), basic grammar, and common everyday words. Avoid idioms, slang, and complex structures.",
    "intermediate": "Use clear vocabulary with some descriptive words. Mix short and medium sentences. Occasional idioms are fine but keep language accessible.",
    "advanced": "Use rich vocabulary, varied sentence structures, literary devices, and natural idioms. Write with sophistication but keep it spoken-natural.",
    "native": "Write as a native speaker would naturally speak — colloquialisms, cultural references, natural rhythm, and full expressive range.",
}


def build_story_system_prompt(
    preset_style: str,
    story_category: str,
    duration: int,
    language: str,
    story_tone: str = None,
    language_level: str = None,
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

    # Language level instruction
    level_line = ""
    if language_level:
        hint = LANGUAGE_LEVEL_HINTS.get(language_level, "")
        level_line = f"LANGUAGE LEVEL: {language_level} — {hint}\n"

    return (
        f"You are a viral short-form content writer specializing in {story_category} stories.\n"
        f"Your stories are designed for {duration}-second spoken narration videos.\n\n"
        f"VISUAL STYLE: {style_name} — {style_desc}\n"
        f"{tone_line}"
        f"{level_line}"
        f"Match the emotional tone and vocabulary to this visual style.\n\n"
        f"Write in {language}. Target approximately {word_target} words total.\n\n"
        "The script must be written in a natural spoken flow suitable for voiceover — "
        "no titles, no summaries, no chapter markers, and no unnecessary meta-text.\n\n"
        "OUTPUT STRUCTURE (mandatory — use these exact labels):\n"
        "Hook: [1-2 sentences — immediate attention grab, pattern interrupt, or shocking statement "
        "that promises secret knowledge or a surprising truth]\n\n"
        "Build: [Core narrative — context, tension, escalation. This is the longest section. "
        "Use contrast between what people believe vs. what's really happening. "
        "Escalate from subtle, low-stakes observations to high-stakes revelations. "
        "Include practical, observable examples so the viewer can recognize them in real life. "
        "End key passages with open loops or transitions like 'but here's what most don't realize.']\n\n"
        "Climax: [Peak moment — the twist, revelation, or emotional peak. "
        "Blend authority (science, evolution, psychology) with emotional stakes.]\n\n"
        "CTA: [1 sentence — call to action, question, or cliffhanger that reminds the viewer what's at stake]\n\n"
        "WRITING RULES:\n"
        "- Use simple, everyday language — even when explaining complex ideas. "
        "Write like you're explaining to a smart friend, not a professor. "
        "Short words beat long words. If a 10-year-old can't follow it, simplify.\n"
        "- Plain text only. No markdown, no formatting, no emojis, no asterisks.\n"
        "- Write as spoken narration — short punchy sentences, conversational rhythm, "
        "natural pauses through line breaks.\n"
        "- Each section MUST be labeled exactly as shown: Hook: / Build: / Climax: / CTA:\n"
        f"- Total word count must be within ±10% of {word_target} words.\n"
        f"- Write entirely in {language}.\n"
        "- Do not include any meta-commentary, instructions, or stage directions in the output.\n"
        "- Reinforce key phrases and recurring motifs to build authority and memorability.\n"
    )


_ANGLE_STARTERS = [
    "Start with a little-known fact or paradox",
    "Open with a personal anecdote or first-person scenario",
    "Begin with a provocative question that challenges assumptions",
    "Start with a vivid sensory scene the listener can picture",
    "Open with a bold controversial claim",
    "Begin with a historical event most people have never heard of",
    "Start with a 'what if' thought experiment",
    "Open with a common belief and immediately subvert it",
    "Begin with a countdown, list, or pattern that builds tension",
    "Start mid-action, dropping the listener into a dramatic moment",
    "Open with a scientific discovery that sounds impossible",
    "Begin with a quiet, intimate confession",
    "Start with two contradictory truths side by side",
    "Open with a warning or ominous prediction",
    "Begin by describing something everyone does but nobody talks about",
]


def _unique_seed() -> str:
    """Generate a short random seed to break LLM/cache deduplication."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def build_story_user_prompt(
    preset_style: str,
    story_category: str,
    duration: int,
    language: str,
    idea: str = None,
) -> str:
    """Build the user prompt for the story generation call."""
    from studio.story.history import format_history_for_prompt

    word_target = compute_word_target(duration)
    seed = _unique_seed()
    angle = random.choice(_ANGLE_STARTERS)
    base = (
        f"Write a viral {story_category} story for a {duration}-second voiceover video. "
        f"Target: {word_target} words. Language: {language}. Style: {preset_style}. "
        "Natural spoken flow only — no titles, no meta-text, no formatting.\n\n"
        f"CREATIVE DIRECTION: {angle}. "
        "Choose a fresh, unexpected angle — avoid generic hooks about 'ancient wisdom' or 'what they don't tell you'. "
        f"[uid:{seed}]"
    )

    # Inject per-preset history so Gemini actively dodges its own past stories.
    history_block = format_history_for_prompt(preset_style, story_category, language)
    if history_block:
        base += f"\n\n{history_block}"

    if idea:
        base += f"\n\nBuild the story around this idea:\n{idea}"
    return base
