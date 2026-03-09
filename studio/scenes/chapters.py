"""Chapter-Based Scene Generation — Split segments into narrative chapters.

When a script produces more segments than a single LLM call can handle,
this module groups them into chapters and provides utilities to build
per-chapter webhook payloads and merge the results.
"""

import json
from loguru import logger

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
MAX_SINGLE_REQUEST = 20     # ≤ this many speech segments → skip chunking
SILENCE_THRESHOLD = 0.65    # filler duration (s) to consider a chapter break
ACCUMULATION_TARGET = 15.0  # seconds of speech before seeking a break
MIN_CHAPTER_SEGMENTS = 5
MAX_CHAPTER_SEGMENTS = 18


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def should_use_chapters(segments):
    """Return True if the segment list is large enough to need chunking."""
    speech_count = sum(1 for s in segments if not s.get("is_filler"))
    return speech_count > MAX_SINGLE_REQUEST


def group_into_chapters(segments, config=None):
    """Group segments into narrative chapters.

    Args:
        segments: Full segment list (including fillers) from segmenter.
        config:   Optional overrides (silence_threshold, accumulation_target,
                  min_chapter_segments, max_chapter_segments).

    Returns:
        List of chapter dicts, each containing:
          chapter        – 1-based chapter number
          segments       – [{index, words}, ...] for the webhook payload
          combined_text  – all words joined
          duration       – total speech duration in seconds
          first_words    – first ~8 words
          last_words     – last ~8 words
    """
    cfg = {
        "silence_threshold": SILENCE_THRESHOLD,
        "accumulation_target": ACCUMULATION_TARGET,
        "min_chapter_segments": MIN_CHAPTER_SEGMENTS,
        "max_chapter_segments": MAX_CHAPTER_SEGMENTS,
    }
    if config:
        cfg.update(config)

    silence_thr = cfg["silence_threshold"]
    accum_target = cfg["accumulation_target"]
    min_segs = cfg["min_chapter_segments"]
    max_segs = cfg["max_chapter_segments"]

    # Separate speech and track filler gaps that follow each speech segment
    speech_segments = []
    filler_after = {}  # speech_index → filler duration that follows it
    last_speech_idx = None
    for s in segments:
        if s.get("is_filler"):
            if last_speech_idx is not None:
                filler_after[last_speech_idx] = s.get("duration", 0)
        else:
            speech_segments.append(s)
            last_speech_idx = len(speech_segments) - 1

    if not speech_segments:
        return []

    # If small enough, single chapter
    if len(speech_segments) <= MAX_SINGLE_REQUEST:
        return [_build_chapter(1, speech_segments)]

    # Walk speech segments and cut chapters
    chapters = []
    current = []
    accum_dur = 0.0

    for i, seg in enumerate(speech_segments):
        current.append(seg)
        accum_dur += seg.get("duration", 2.5)

        # Check if we should cut after this segment
        gap = filler_after.get(i, 0)
        is_strong = seg.get("break_reason") in ("strong_break", "end_of_text")
        at_end = (i == len(speech_segments) - 1)

        should_cut = False

        if at_end:
            should_cut = True
        elif len(current) >= max_segs:
            # Force cut at max
            should_cut = True
        elif len(current) >= min_segs and accum_dur >= accum_target:
            # Enough accumulated — look for a good boundary
            if gap >= silence_thr:
                should_cut = True
            elif is_strong and accum_dur >= accum_target * 1.2:
                should_cut = True

        if should_cut:
            chapters.append(_build_chapter(len(chapters) + 1, current))
            current = []
            accum_dur = 0.0

    # Leftover (shouldn't happen due to at_end, but safety)
    if current:
        chapters.append(_build_chapter(len(chapters) + 1, current))

    logger.info("Split {} segments into {} chapters: {}",
                len(speech_segments), len(chapters),
                ", ".join(f"ch{c['chapter']}={len(c['segments'])}" for c in chapters))
    return chapters


def build_chapter_system_prompt(base_prompt, style_prompt, analysis_json,
                                chapter_idx, total_chapters, chapters):
    """Build the system prompt for a chapter webhook call.

    For chapter 1: base_prompt + chapter mode suffix + style instructions.
    For chapters 2+: chapter scene prompt with pre-computed analysis.
    """
    ch = chapters[chapter_idx]
    prev_words = chapters[chapter_idx - 1]["last_words"] if chapter_idx > 0 else ""
    next_words = chapters[chapter_idx + 1]["first_words"] if chapter_idx < total_chapters - 1 else ""

    chapter_context = (
        f"## CHAPTER MODE\n"
        f"This is Chapter {ch['chapter']} of {total_chapters}.\n"
        f"You are writing scenes ONLY for the {len(ch['segments'])} segments provided below.\n"
        f"The full script is given for thematic context — do NOT create scenes for segments outside this chapter.\n"
    )
    if prev_words:
        chapter_context += f'Previous chapter ended with: "{prev_words}"\n'
    if next_words:
        chapter_context += f'Next chapter starts with: "{next_words}"\n'

    if chapter_idx == 0:
        # Chapter 1: full prompt (includes ANALYZE step) + chapter scope
        prompt = base_prompt + "\n\n" + chapter_context
    else:
        # Chapters 2+: inject pre-computed analysis, skip ANALYZE step
        prompt = _build_continuation_prompt(analysis_json, chapter_context)

    if style_prompt:
        prompt += f"\n\n## STYLE INSTRUCTIONS\n{style_prompt}"

    return prompt


def merge_chapter_results(chapter_results):
    """Merge results from multiple chapter webhook calls into one.

    Args:
        chapter_results: List of parsed webhook response dicts, in chapter order.
                         chapter_results[0] must contain the analysis.

    Returns:
        Combined dict: {analysis, scenes, scene_count, ...}
    """
    if not chapter_results:
        return {"analysis": {}, "scenes": [], "scene_count": 0}

    # Analysis from chapter 1
    analysis = chapter_results[0].get("analysis", {})

    # Collect all scenes, preserving order
    all_scenes = []
    all_warnings = []
    all_errors = []
    for i, result in enumerate(chapter_results):
        scenes = result.get("scenes", [])
        all_scenes.extend(scenes)
        # Collect validation metadata
        for w in result.get("warnings", []):
            all_warnings.append(f"[ch{i+1}] {w}")
        for e in result.get("errors", []):
            all_errors.append(f"[ch{i+1}] {e}")

    # Sort by index to ensure correct order
    all_scenes.sort(key=lambda s: s.get("index", 0))

    # Check for duplicate indices
    seen = set()
    for s in all_scenes:
        idx = s.get("index")
        if idx in seen:
            all_warnings.append(f"Duplicate scene index {idx} across chapters")
        seen.add(idx)

    # Recompute type mix
    type_counts = {}
    for s in all_scenes:
        t = s.get("type_of_scene", "video")
        type_counts[t] = type_counts.get(t, 0) + 1
    total = len(all_scenes)
    type_mix = {}
    for t, c in type_counts.items():
        pct = round(c / total * 100) if total else 0
        type_mix[t] = f"{c} ({pct}%)"

    merged = {
        "valid": len(all_errors) == 0,
        "errors": all_errors,
        "warnings": all_warnings,
        "type_mix": type_mix,
        "analysis": analysis,
        "scenes": all_scenes,
        "scene_count": total,
        "chapters_used": len(chapter_results),
    }
    return merged


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_chapter(number, speech_segments):
    """Build a chapter dict from a list of speech segments."""
    segments = [{"index": s["index"], "words": s["words"]} for s in speech_segments]
    combined = " ".join(s["words"] for s in speech_segments)
    words_list = combined.split()
    duration = sum(s.get("duration", 2.5) for s in speech_segments)
    return {
        "chapter": number,
        "segments": segments,
        "combined_text": combined,
        "duration": round(duration, 2),
        "first_words": " ".join(words_list[:8]),
        "last_words": " ".join(words_list[-8:]) if len(words_list) > 8 else " ".join(words_list),
    }


def _build_continuation_prompt(analysis_json, chapter_context):
    """Build system prompt for chapters 2+ with pre-computed analysis."""
    if not analysis_json:
        analysis_json = {}
    analysis_str = json.dumps(analysis_json, indent=2) if isinstance(analysis_json, dict) else str(analysis_json)

    return f"""\
You are a visual scene prompt writer for short-form viral video.

## PRE-COMPUTED ANALYSIS
The analysis below was already computed for the full script. Return it UNCHANGED in your response under the "analysis" key.

```json
{analysis_str}
```

{chapter_context}

## SCENE RULES

### THEMATIC INTERPRETATION — CRITICAL
Every scene must visually serve the core_theme from the analysis, NOT literally translate the script's words into props.

**NEVER illustrate a metaphor literally.** The viewer hears the words while seeing the image. The visual should DEEPEN the meaning, not repeat it.

### Scene object keys
- index: integer (match input index exactly)
- title: string (2-6 words)
- narrative_role: "hook" | "buildup" | "peak" | "transition" | "cta"
- type_of_scene: "image" | "video"
- image_prompt: scene description (video: include 2-3 motion cues)
- duration: number (2.0-4.0 seconds)

## TYPE MIX
- 60-75% video, 20-30% image
- Default to VIDEO

## IMAGE_PROMPT RULES

**VIDEO**: living moment with motion. FORMAT: [shot type], [subject + action], [setting], [lighting], [mood], [2-3 motion cues], [style keywords]
Include motion from different categories: body, environment, camera, atmosphere.

**IMAGE**: one frozen photograph. No motion verbs. FORMAT: [shot type], [subject + details], [setting], [lighting], [mood], [style keywords]

**ALL TYPES**:
- Shot types: extreme-close-up | close-up | medium | wide | POV | bird's-eye | low-angle | high-angle | over-shoulder | centered-symmetrical
- No two consecutive scenes may use the same shot type
- Pick 2-4 style keywords consistent across all prompts
- NEVER mention aspect ratio or resolution
- Same environment, lighting temperature, and color palette throughout

## OUTPUT
Return ONLY valid JSON. No markdown. No code fences. No commentary. ENGLISH ONLY.

{{"analysis": {{copy the pre-computed analysis exactly}}, "scenes": [...]}}"""
