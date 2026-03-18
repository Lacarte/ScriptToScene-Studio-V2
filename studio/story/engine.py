"""Story generation engine — parses LLM output into structured sections."""

import re


def parse_story_sections(raw_text: str) -> dict:
    """Parse raw LLM output into structured story sections.

    Expects labels: Hook:, Build:, Climax:, CTA:
    Returns dict with keys: hook, build, climax, cta, story_text
    """
    text = raw_text.strip()

    sections = {"hook": "", "build": "", "climax": "", "cta": ""}
    labels = ["Hook", "Build", "Climax", "CTA"]

    # Build a regex that splits on section labels
    pattern = r"(?:^|\n)\s*(" + "|".join(labels) + r")\s*:\s*"
    parts = re.split(pattern, text, flags=re.IGNORECASE)

    # parts alternates: [preamble, label, content, label, content, ...]
    current_key = None
    for part in parts:
        normalized = part.strip().lower()
        if normalized in [l.lower() for l in labels]:
            current_key = normalized
        elif current_key and current_key in sections:
            sections[current_key] = part.strip()

    # If parsing failed (no labels found), put everything in build
    if not any(sections.values()):
        sections["build"] = text

    # Reconstruct full story text
    story_parts = []
    for label in labels:
        key = label.lower()
        if sections.get(key):
            story_parts.append(f"{label}: {sections[key]}")
    story_text = "\n\n".join(story_parts) if story_parts else text

    word_count = len(story_text.split())

    return {
        "sections": sections,
        "story_text": story_text,
        "word_count": word_count,
    }
