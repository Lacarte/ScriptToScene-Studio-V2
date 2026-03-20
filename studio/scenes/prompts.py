"""Prompt builders for structured scene generation."""

from __future__ import annotations

import json


SHOT_TYPES = (
    "extreme-close-up | close-up | medium | wide | POV | bird's-eye | "
    "low-angle | high-angle | over-shoulder | centered-symmetrical"
)


def _json_block(data: object) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)


def _build_header(chapter_context: str = "") -> str:
    parts = [
        "You are a visual scene planner and prompt writer for short-form viral video.",
        "",
        "## INPUT",
        "You receive JSON with:",
        "- script: full spoken transcript",
        "- style: style id",
        "- segments: array of speech segments, each with index and words",
        "- style_spec: structured visual template constraints",
        "- visual_bible: project-level continuity contract",
        "- scene_blueprints: per-segment targets for role, type, shot, and continuity",
    ]
    if chapter_context:
        parts.extend(["", chapter_context.strip()])
    return "\n".join(parts)


def _build_scene_contract(include_analysis: bool) -> str:
    analysis_section = ""
    if include_analysis:
        analysis_section = """
## STEP 1: ANALYZE
Read the full script first.
Return an "analysis" object that sharpens the story's meaning while staying inside the provided VISUAL BIBLE.

Rules:
- Preserve the visual bible as the source of truth for continuity.
- You may improve wording, but do not replace the world anchor, palette guardrails, anchor subject, or camera grammar.
- The returned analysis must include:
  - core_theme
  - mood
  - environment
  - color_palette
  - tone
  - visual_style
  - visual_bible
"""
    return f"""{analysis_section}
## STEP 2: WRITE SCENES

Every scene must serve the script's meaning, not literally illustrate words.
The viewer hears the transcript while seeing the image. The image should deepen meaning, not duplicate the narration.

## RULE HIERARCHY
1. Segment contract
2. Visual bible continuity
3. Scene blueprint compliance
4. Style spec constraints
5. Creative enrichment

## SEGMENT CONTRACT
- Return exactly ONE scene for every input segment.
- Match each input index exactly.
- Do NOT merge, split, reorder, omit, or add segments.

## CONTINUITY RULES
- All scenes belong to one coherent visual world.
- Keep the anchor subject or anchor motifs visible across the sequence.
- Stay inside the palette guardrails and lighting baseline unless the script clearly demands a contrast moment.
- If you change environment, it must still feel part of the same world anchor.

## BLUEPRINT RULES
- Each scene blueprint tells you the target narrative role, preferred scene type, target shot type, and continuity priority.
- Follow the blueprint unless the segment would become nonsensical.
- Prefer exact blueprint role/type/shot matches.
- If a blueprint marks anchor_required=true, include the anchor subject or one of the anchor motifs.

## Scene object keys (output ONLY these — no extra fields)
- index: integer (match input index exactly)
- title: string (2-6 words)
- narrative_role: "hook" | "buildup" | "peak" | "transition" | "text_accent" | "cta"
- type_of_scene: "image" | "video" | "text"
- image_prompt: scene description
- text_content: string or null

## TYPE RULES
- First and last scenes must NOT be text.
- Default to the blueprint's preferred scene type.
- Text scenes use the hardest-hitting line only.

## IMAGE PROMPT RULES

VIDEO:
- Must feel like a living moment with motion — never a static pose.
- Format: [shot type], [subject + action], [setting], [lighting], [mood], [2-3 motion cues]
- MANDATORY: include at least TWO motion cues from different categories:
  body (gesturing, walking, turning), environment (wind, rain, flickering lights),
  camera (slow pan, tracking, dolly), atmosphere (smoke drifting, dust particles, shadows shifting).
- If no obvious action exists, use subtle ambient motion (swaying fabric, breathing, light flicker).

IMAGE:
- One frozen photographic moment.
- No motion verbs.
- Format: [shot type], [subject + details], [setting], [lighting], [mood]

TEXT:
- Use a blurred or abstract background from the same world anchor.
- Do NOT include text inside the prompt itself.

ALL TYPES:
- Valid shot types: {SHOT_TYPES}
- Start each image_prompt with the shot type.
- No two consecutive scenes may use the same shot type.
- Never mention aspect ratio or resolution.
- Weave style cues naturally into the description (lighting, texture, mood).
- NEVER append raw style labels or tag lists at the end of a prompt (e.g. "Noir, Mystery, High contrast").
  Instead, embed the style through concrete visual details throughout the description.

## OUTPUT
Return ONLY valid JSON. No markdown. No code fences. No commentary. ENGLISH ONLY.
"""


def build_scene_system_prompt(
    style_spec: dict,
    visual_bible: dict,
    scene_blueprints: list[dict],
    *,
    plan_summary: dict | None = None,
    custom_style_notes: str = "",
    continuation_state: dict | None = None,
    chapter_context: str = "",
) -> str:
    """Build the prompt used for single-call generation and chapter 1."""
    sections = [
        _build_header(chapter_context),
        "",
        "## STYLE SPECIFICATION",
        _json_block(style_spec),
        "",
        "## VISUAL BIBLE",
        _json_block(visual_bible),
    ]
    if plan_summary:
        sections.extend(["", "## GLOBAL PLAN SUMMARY", _json_block(plan_summary)])
    sections.extend(["", "## SCENE BLUEPRINTS", _json_block(scene_blueprints)])
    if continuation_state:
        sections.extend(["", "## CONTINUITY STATE", _json_block(continuation_state)])
    if custom_style_notes:
        sections.extend(["", "## CUSTOM STYLE NOTES", custom_style_notes.strip()])
    sections.extend([
        "",
        _build_scene_contract(include_analysis=True),
        "",
        """{
  "analysis": {
    "core_theme": "...",
    "mood": "...",
    "environment": "...",
    "color_palette": ["..."],
    "tone": "...",
    "visual_style": "...",
    "visual_bible": { "...": "..." }
  },
  "scenes": [ ... ]
}""",
    ])
    return "\n".join(sections)


def build_scene_continuation_prompt(
    precomputed_analysis: dict,
    style_spec: dict,
    visual_bible: dict,
    scene_blueprints: list[dict],
    *,
    plan_summary: dict | None = None,
    custom_style_notes: str = "",
    continuation_state: dict | None = None,
    chapter_context: str = "",
) -> str:
    """Build the prompt used for later chapter/chunk requests."""
    analysis = dict(precomputed_analysis or {})
    analysis.setdefault("visual_bible", visual_bible)

    sections = [
        _build_header(chapter_context),
        "",
        "## PRE-COMPUTED ANALYSIS",
        "Return this analysis UNCHANGED under the `analysis` key.",
        _json_block(analysis),
        "",
        "## STYLE SPECIFICATION",
        _json_block(style_spec),
        "",
        "## VISUAL BIBLE",
        _json_block(visual_bible),
    ]
    if plan_summary:
        sections.extend(["", "## GLOBAL PLAN SUMMARY", _json_block(plan_summary)])
    sections.extend(["", "## SCENE BLUEPRINTS", _json_block(scene_blueprints)])
    if continuation_state:
        sections.extend(["", "## CONTINUITY STATE", _json_block(continuation_state)])
    if custom_style_notes:
        sections.extend(["", "## CUSTOM STYLE NOTES", custom_style_notes.strip()])
    sections.extend([
        "",
        _build_scene_contract(include_analysis=False),
        "",
        '{"analysis": {copy the pre-computed analysis exactly}, "scenes": [...]}',
    ])
    return "\n".join(sections)


SCENE_GENERATOR_PROMPT = (
    "Structured scene prompt builder module. "
    "Use build_scene_system_prompt() or build_scene_continuation_prompt()."
)
