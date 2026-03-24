"""Hybrid Analyzer & Scorer.

Phase A: Heuristic checks (zero API cost) — measurable quality signals.
Phase B: LLM scoring (Gemini 2.5 Flash) — subjective quality assessment.
Phase C: Merge into unified 5-dimension scores.
"""

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from .config import THRESHOLDS, WEIGHTS, ALL_STEPS
from .llm import call_llm, call_llm_with_images
from .prepare import PipelineSnapshot


# ── Data Classes ─────────────────────────────────────────────────────────

@dataclass
class Issue:
    module: str        # tts, alignment, segments, scenes, storyboard, cross
    severity: str      # critical, warning, info
    description: str
    root_cause: str
    suggested_fix: str
    metric_name: str = ""
    metric_value: float = 0.0
    metric_threshold: float = 0.0


@dataclass
class HeuristicReport:
    issues: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


@dataclass
class LLMScores:
    hook_strength: int = 0
    narrative_flow: int = 0
    visual_consistency: int = 0
    emotional_progression: int = 0
    style_adherence: int = 0
    raw_response: dict = field(default_factory=dict)


@dataclass
class UnifiedScores:
    style_consistency: int = 0
    visual_quality: int = 0
    narrative_coherence: int = 0
    audio_visual_sync: int = 0
    viral_score: int = 0
    viral_breakdown: dict = field(default_factory=dict)
    overall: float = 0.0


@dataclass
class ImageScores:
    style_consistency: int = 0     # 0-100, do all images share same style/palette?
    composition_quality: int = 0   # 0-100, framing, balance, visual interest
    prompt_adherence: int = 0      # 0-100, does generated image match the prompt?
    visual_flow: int = 0           # 0-100, do images flow as a sequence?
    overall: int = 0
    per_scene: list = field(default_factory=list)  # per-scene feedback
    raw_response: dict = field(default_factory=dict)


@dataclass
class AnalysisResult:
    heuristic: HeuristicReport = field(default_factory=HeuristicReport)
    llm_scores: LLMScores = field(default_factory=LLMScores)
    image_scores: ImageScores = field(default_factory=ImageScores)
    unified: UnifiedScores = field(default_factory=UnifiedScores)
    snapshot_id: str = ""


# ── Helpers ──────────────────────────────────────────────────────────────

def _clamp(v, lo=0, hi=100):
    try:
        return max(lo, min(hi, int(v)))
    except (ValueError, TypeError):
        return 50


# ── Heuristic Checks ────────────────────────────────────────────────────

def _check_tts(snap: PipelineSnapshot):
    issues, metrics = [], {}
    tts = snap.tts
    if not tts:
        issues.append(Issue("tts", "critical", "No TTS output found", "Missing tts.json", "Re-run pipeline"))
        return issues, metrics

    th = THRESHOLDS["tts"]
    duration = tts.get("duration_seconds", 0)
    words = tts.get("words", 0)
    speed = tts.get("speed", 1.0)

    wps = words / duration if duration > 0 else 0
    metrics["tts_wps"] = round(wps, 2)
    metrics["tts_duration"] = duration
    metrics["tts_word_count"] = words

    if wps < th.min_wps:
        issues.append(Issue(
            "tts", "warning",
            f"Speech too slow: {wps:.1f} wps (min {th.min_wps})",
            "TTS speed too low or excessive pauses",
            f"Increase speed from {speed} to {min(speed + 0.15, 2.0):.2f}",
            "tts_wps", wps, th.min_wps,
        ))
    elif wps > th.max_wps:
        issues.append(Issue(
            "tts", "warning",
            f"Speech too fast: {wps:.1f} wps (max {th.max_wps})",
            "TTS speed too high",
            f"Decrease speed from {speed} to {max(speed - 0.15, 0.5):.2f}",
            "tts_wps", wps, th.max_wps,
        ))

    if duration < th.min_duration:
        issues.append(Issue(
            "tts", "warning",
            f"Audio too short: {duration:.1f}s (min {th.min_duration}s)",
            "Input text too short", "Provide longer text (120-180 words)",
            "tts_duration", duration, th.min_duration,
        ))
    elif duration > th.max_duration:
        issues.append(Issue(
            "tts", "warning",
            f"Audio too long: {duration:.1f}s (max {th.max_duration}s)",
            "Input text too long for <60s format",
            "Trim text or increase TTS speed",
            "tts_duration", duration, th.max_duration,
        ))

    return issues, metrics


def _check_alignment(snap: PipelineSnapshot):
    issues, metrics = [], {}
    align_data = snap.alignment
    if not align_data:
        issues.append(Issue("alignment", "critical", "No alignment data", "Missing alignment.json", "Re-run pipeline"))
        return issues, metrics

    words = align_data.get("alignment", [])
    if not words:
        return issues, metrics

    th = THRESHOLDS["alignment"]

    zero_dur = sum(1 for w in words if w["begin"] == w["end"])
    zero_pct = (zero_dur / len(words)) * 100 if words else 0
    metrics["align_zero_duration_pct"] = round(zero_pct, 1)
    metrics["align_word_count"] = len(words)

    if zero_pct > th.max_zero_duration_pct:
        issues.append(Issue(
            "alignment", "warning",
            f"{zero_pct:.1f}% of words have zero duration (threshold: {th.max_zero_duration_pct}%)",
            "Alignment model struggled with word boundaries",
            "Try different voice or slower speed",
            "align_zero_duration_pct", zero_pct, th.max_zero_duration_pct,
        ))

    drifts = []
    large_gaps = 0
    for i in range(len(words) - 1):
        gap_ms = (words[i + 1]["begin"] - words[i]["end"]) * 1000
        drifts.append(gap_ms)
        if abs(gap_ms) > th.max_word_drift_ms:
            large_gaps += 1

    if drifts:
        avg_drift = sum(abs(d) for d in drifts) / len(drifts)
        max_drift = max(abs(d) for d in drifts)
        metrics["align_avg_drift_ms"] = round(avg_drift, 1)
        metrics["align_max_drift_ms"] = round(max_drift, 1)
        metrics["align_large_gap_count"] = large_gaps

        if large_gaps > len(words) * 0.1:
            issues.append(Issue(
                "alignment", "warning",
                f"{large_gaps} words have excessive timing gaps (>{th.max_word_drift_ms}ms)",
                "Force aligner produced unreliable timestamps",
                "Try a different voice with clearer enunciation",
                "align_large_gap_count", large_gaps, len(words) * 0.1,
            ))

    return issues, metrics


def _check_segments(snap: PipelineSnapshot):
    issues, metrics = [], {}
    seg_data = snap.segments
    if not seg_data:
        issues.append(Issue("segments", "critical", "No segment data", "Missing segmented.json", "Re-run pipeline"))
        return issues, metrics

    th = THRESHOLDS["segments"]
    segments = seg_data.get("segments", [])
    speech_segs = [s for s in segments if not s.get("is_filler")]
    stats = seg_data.get("stats", {})

    seg_count = len(speech_segs)
    metrics["seg_count"] = seg_count
    metrics["seg_avg_duration"] = stats.get("avg_duration", 0)
    metrics["seg_min_duration"] = stats.get("min_duration", 0)
    metrics["seg_max_duration"] = stats.get("max_duration", 0)

    if seg_count < th.min_segments:
        issues.append(Issue(
            "segments", "warning",
            f"Only {seg_count} segments (min: {th.min_segments})",
            "Segmenter target_max too high or text too short",
            "Lower target_max to 3.5 or target_min to 1.2",
            "seg_count", seg_count, th.min_segments,
        ))
    elif seg_count > th.max_segments:
        issues.append(Issue(
            "segments", "warning",
            f"{seg_count} segments is excessive (max: {th.max_segments})",
            "Segmenter target_min too low",
            "Raise target_min to 2.0 and target_max to 4.5",
            "seg_count", seg_count, th.max_segments,
        ))

    reasons = Counter(s.get("break_reason", "") for s in speech_segs)
    hard_max_count = reasons.get("hard_max", 0)
    hard_max_pct = (hard_max_count / seg_count * 100) if seg_count > 0 else 0
    metrics["seg_hard_max_pct"] = round(hard_max_pct, 1)
    metrics["seg_break_reasons"] = dict(reasons)

    if hard_max_pct > th.hard_max_break_pct:
        issues.append(Issue(
            "segments", "warning",
            f"{hard_max_pct:.0f}% of breaks are hard_max forced cuts (threshold: {th.hard_max_break_pct}%)",
            "Segmenter can't find natural breaks within limits",
            "Increase hard_max to 6.0 and target_max to 5.0",
            "seg_hard_max_pct", hard_max_pct, th.hard_max_break_pct,
        ))

    durations = [s["duration"] for s in speech_segs]
    if len(durations) >= 2:
        mean_d = sum(durations) / len(durations)
        std_d = math.sqrt(sum((d - mean_d) ** 2 for d in durations) / len(durations))
        cv = std_d / mean_d if mean_d > 0 else 0
        metrics["seg_duration_cv"] = round(cv, 3)

        if cv > th.cv_threshold:
            issues.append(Issue(
                "segments", "info",
                f"Segment durations are uneven (CV={cv:.2f}, threshold: {th.cv_threshold})",
                "Wide range between shortest and longest segments",
                "Tighten target_min/target_max range (e.g., 2.0-3.5)",
                "seg_duration_cv", cv, th.cv_threshold,
            ))

    return issues, metrics


def _check_scenes(snap: PipelineSnapshot):
    issues, metrics = [], {}
    scene_data = snap.scenes
    if not scene_data:
        issues.append(Issue("scenes", "critical", "No scene data", "Missing scenes.json", "Re-run pipeline"))
        return issues, metrics

    th = THRESHOLDS["scenes"]
    scenes = scene_data.get("scenes", [])
    if not scenes:
        return issues, metrics

    prompt_lengths = [len(s.get("image_prompt", "")) for s in scenes]
    short_prompts = sum(1 for l in prompt_lengths if l < th.min_prompt_length)
    avg_prompt_len = sum(prompt_lengths) / len(prompt_lengths) if prompt_lengths else 0
    metrics["scene_avg_prompt_length"] = round(avg_prompt_len, 0)
    metrics["scene_short_prompt_count"] = short_prompts

    if short_prompts > 0:
        issues.append(Issue(
            "scenes", "warning",
            f"{short_prompts} scene(s) have prompts under {th.min_prompt_length} chars",
            "LLM generated insufficient visual description",
            "Add custom_style_notes requesting detailed descriptions",
            "scene_short_prompt_count", short_prompts, 0,
        ))

    roles = [s.get("narrative_role", "buildup") for s in scenes]
    role_set = set(roles)
    role_counts = Counter(roles)
    metrics["scene_roles"] = dict(role_counts)
    metrics["scene_role_variety"] = len(role_set)

    for req in th.required_roles:
        if req not in role_set:
            issues.append(Issue(
                "scenes", "critical",
                f"Missing required narrative role: '{req}'",
                f"LLM did not assign any scene the '{req}' role",
                "Add style note: 'First scene MUST be hook, include a peak'",
                "scene_missing_role", 0, 1,
            ))

    if len(role_set) < th.min_role_variety:
        issues.append(Issue(
            "scenes", "warning",
            f"Only {len(role_set)} distinct roles (need {th.min_role_variety}+)",
            "Monotonous narrative arc",
            "Request more role variety in custom_style_notes",
            "scene_role_variety", len(role_set), th.min_role_variety,
        ))

    # Shot type variety
    shot_types = []
    for s in scenes:
        prompt = s.get("image_prompt", "")
        first_phrase = prompt.split(",")[0].strip().lower() if prompt else ""
        shot_types.append(first_phrase)

    metrics["scene_type_variety"] = len(set(shot_types))

    max_run = 1
    current_run = 1
    for i in range(1, len(shot_types)):
        if shot_types[i] == shot_types[i - 1] and shot_types[i]:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 1
    metrics["scene_max_consecutive_shot"] = max_run

    if max_run > th.max_consecutive_same_shot:
        issues.append(Issue(
            "scenes", "warning",
            f"{max_run} consecutive scenes use the same shot type",
            "LLM is repeating visual composition",
            "Add note: 'Never repeat the same shot type consecutively'",
            "scene_max_consecutive_shot", max_run, th.max_consecutive_same_shot,
        ))

    scene_types = Counter(s.get("type_of_scene", "video") for s in scenes)
    metrics["scene_types"] = dict(scene_types)

    if len(scene_types) < th.min_type_variety:
        issues.append(Issue(
            "scenes", "warning",
            f"Only {len(scene_types)} scene type(s) (need {th.min_type_variety}+: video + text)",
            "All scenes are the same type — no text accent scenes",
            "Add note: 'Include at least one text_accent scene for variety'",
            "scene_type_variety", len(scene_types), th.min_type_variety,
        ))

    return issues, metrics


def _check_storyboard(snap: PipelineSnapshot):
    issues, metrics = [], {}
    sb = snap.storyboard
    if not sb:
        return issues, metrics

    th = THRESHOLDS["storyboard"]
    total = sb.get("total", 0)
    errors = sb.get("errors", 0)
    error_rate = (errors / total * 100) if total > 0 else 0
    metrics["sb_total"] = total
    metrics["sb_ready"] = sb.get("ready", 0)
    metrics["sb_errors"] = errors
    metrics["sb_error_rate"] = round(error_rate, 1)

    if error_rate > th.max_error_rate:
        issues.append(Issue(
            "storyboard", "warning",
            f"{errors}/{total} images failed ({error_rate:.0f}% error rate)",
            "WaveSpeed API rejected some prompts or timed out",
            "Check prompt length for failed scenes; retry",
            "sb_error_rate", error_rate, th.max_error_rate,
        ))

    return issues, metrics


def _check_cross_module(snap: PipelineSnapshot):
    issues, metrics = [], {}
    seg_data = snap.segments
    scene_data = snap.scenes
    if not seg_data or not scene_data:
        return issues, metrics

    th = THRESHOLDS["cross"]
    speech_segs = [s for s in seg_data.get("segments", []) if not s.get("is_filler")]
    scenes = scene_data.get("scenes", [])

    delta = abs(len(scenes) - len(speech_segs))
    metrics["cross_seg_scene_delta"] = delta

    if delta > th.max_segment_scene_mismatch:
        issues.append(Issue(
            "cross", "critical",
            f"Scene count ({len(scenes)}) != segment count ({len(speech_segs)})",
            "Scene generator added/removed segments",
            "This is a segment contract violation — re-run scenes",
            "cross_seg_scene_delta", delta, th.max_segment_scene_mismatch,
        ))

    timing_drifts = []
    for scene in scenes:
        seg_start = scene.get("segment_start")
        idx = scene.get("index", -1)
        if seg_start is not None and 0 <= idx < len(speech_segs):
            expected_start = speech_segs[idx]["start"]
            drift_ms = abs(seg_start - expected_start) * 1000
            timing_drifts.append(drift_ms)

    if timing_drifts:
        avg_drift = sum(timing_drifts) / len(timing_drifts)
        max_drift = max(timing_drifts)
        metrics["cross_avg_timing_drift_ms"] = round(avg_drift, 1)
        metrics["cross_max_timing_drift_ms"] = round(max_drift, 1)

        if max_drift > th.max_timing_drift_ms:
            issues.append(Issue(
                "cross", "warning",
                f"Max timing drift: {max_drift:.0f}ms between scene and segment boundaries",
                "Scene timing applied incorrectly",
                "Check timing merge logic",
                "cross_max_timing_drift_ms", max_drift, th.max_timing_drift_ms,
            ))

    return issues, metrics


# Check function registry keyed by step name
_CHECKS = {
    "tts": _check_tts,
    "alignment": _check_alignment,
    "segments": _check_segments,
    "scenes": _check_scenes,
    "storyboard": _check_storyboard,
}


def run_heuristics(snap: PipelineSnapshot, steps: Optional[list] = None) -> HeuristicReport:
    """Run heuristic checks. If steps is provided, only run those."""
    report = HeuristicReport()
    target_steps = steps or ALL_STEPS

    for step_name in target_steps:
        check_fn = _CHECKS.get(step_name)
        if check_fn:
            step_issues, step_metrics = check_fn(snap)
            report.issues.extend(step_issues)
            report.metrics.update(step_metrics)

    # Always run cross-module if both segments and scenes are in scope
    if (not steps) or ("segments" in target_steps and "scenes" in target_steps):
        cross_issues, cross_metrics = _check_cross_module(snap)
        report.issues.extend(cross_issues)
        report.metrics.update(cross_metrics)

    return report


# ── LLM Scoring ──────────────────────────────────────────────────────────

LLM_SYSTEM_PROMPT = """You are a TikTok/Reels video quality analyst. You evaluate AI-generated scene scripts for short-form viral video (under 60 seconds).

You receive the full transcript, the scene breakdown with prompts, narrative roles, and timing data.

Score each dimension from 0 to 100. Be critical — 50 is average, 70 is good, 90+ is exceptional.

Return ONLY valid JSON:
{
  "hook_strength": <0-100, does scene 0 grab attention in first 2 seconds?>,
  "narrative_flow": <0-100, does the arc work for <60s TikTok? hook>buildup>peak>resolution>,
  "visual_consistency": <0-100, do all prompts maintain the same world, palette, style?>,
  "emotional_progression": <0-100, is there buildup>peak>resolution emotional arc?>,
  "style_adherence": <0-100, do prompts match the requested style template?>,
  "reasoning": {
    "hook_strength": "brief explanation",
    "narrative_flow": "brief explanation",
    "visual_consistency": "brief explanation",
    "emotional_progression": "brief explanation",
    "style_adherence": "brief explanation"
  }
}"""


def _build_llm_user_prompt(snap: PipelineSnapshot) -> str:
    scenes = snap.scenes.get("scenes", [])
    analysis = snap.scenes.get("analysis", {})
    config = snap.config

    scene_summary = []
    for s in scenes:
        scene_summary.append({
            "index": s.get("index"),
            "title": s.get("title"),
            "narrative_role": s.get("narrative_role"),
            "type_of_scene": s.get("type_of_scene"),
            "image_prompt": s.get("image_prompt", ""),
            "duration": s.get("segment_duration", s.get("duration", 0)),
        })

    return json.dumps({
        "transcript": config.get("text", "")[:2000],
        "style": config.get("style", ""),
        "visual_style": config.get("visual_style", ""),
        "total_duration": snap.tts.get("duration_seconds", 0),
        "analysis": analysis,
        "scenes": scene_summary,
    }, indent=2)


def run_llm_scoring(snap: PipelineSnapshot) -> LLMScores:
    """Call Gemini 2.5 Flash for subjective scoring."""
    if not snap.scenes.get("scenes"):
        return LLMScores()

    user_prompt = _build_llm_user_prompt(snap)
    try:
        result = call_llm(LLM_SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        print(f"    LLM scoring failed: {e}")
        return LLMScores()

    return LLMScores(
        hook_strength=_clamp(result.get("hook_strength", 50)),
        narrative_flow=_clamp(result.get("narrative_flow", 50)),
        visual_consistency=_clamp(result.get("visual_consistency", 50)),
        emotional_progression=_clamp(result.get("emotional_progression", 50)),
        style_adherence=_clamp(result.get("style_adherence", 50)),
        raw_response=result,
    )


# ── Image Scoring (Vision) ────────────────────────────────────────────────

IMAGE_SCORING_PROMPT = """You are a visual quality analyst for short-form video storyboards. You receive storyboard reference images for a TikTok/Reels video along with their scene prompts.

Evaluate the ACTUAL GENERATED IMAGES (not just the prompts). Score each dimension 0-100. Be critical.

Return ONLY valid JSON:
{
  "style_consistency": <0-100, do all images share the same visual style, color palette, lighting?>,
  "composition_quality": <0-100, are images well-composed? good framing, visual interest, clarity?>,
  "prompt_adherence": <0-100, do the generated images accurately match what was described in the prompts?>,
  "visual_flow": <0-100, viewed as a sequence, do the images tell a coherent visual story?>,
  "per_scene": [
    {"scene": 0, "score": <0-100>, "note": "brief feedback"},
    ...
  ],
  "suggestions": ["actionable improvement suggestion 1", "suggestion 2"]
}"""


def _get_storyboard_images(snap: PipelineSnapshot) -> list:
    """Get paths to storyboard images for a project."""
    from .config import STORYBOARD_DIR
    project_dir = STORYBOARD_DIR / snap.project_id
    if not project_dir.is_dir():
        return []

    images = []
    scenes = snap.scenes.get("scenes", [])
    for i in range(len(scenes)):
        img_path = project_dir / str(i) / "image.jpeg"
        if not img_path.is_file():
            img_path = project_dir / str(i) / "image.png"
        if img_path.is_file():
            images.append((i, img_path))
    return images


def run_image_scoring(snap: PipelineSnapshot) -> ImageScores:
    """Score storyboard images using Gemini vision."""
    image_entries = _get_storyboard_images(snap)
    if not image_entries:
        print("    Image scoring: no storyboard images found")
        return ImageScores()

    # Limit to 10 images to keep token cost reasonable
    if len(image_entries) > 10:
        step = len(image_entries) / 10
        image_entries = [image_entries[int(i * step)] for i in range(10)]

    scenes = snap.scenes.get("scenes", [])
    scene_info = []
    image_paths = []
    for idx, path in image_entries:
        image_paths.append(path)
        prompt = scenes[idx].get("image_prompt", "") if idx < len(scenes) else ""
        scene_info.append({"scene": idx, "prompt": prompt[:200]})

    user_text = json.dumps({
        "style": snap.config.get("style", ""),
        "total_scenes": len(scenes),
        "scenes_shown": scene_info,
    }, indent=2)

    try:
        result = call_llm_with_images(IMAGE_SCORING_PROMPT, user_text, image_paths)
    except Exception as e:
        print(f"    Image scoring failed: {e}")
        return ImageScores()

    return ImageScores(
        style_consistency=_clamp(result.get("style_consistency", 50)),
        composition_quality=_clamp(result.get("composition_quality", 50)),
        prompt_adherence=_clamp(result.get("prompt_adherence", 50)),
        visual_flow=_clamp(result.get("visual_flow", 50)),
        overall=_clamp(int(
            0.30 * _clamp(result.get("style_consistency", 50))
            + 0.25 * _clamp(result.get("composition_quality", 50))
            + 0.25 * _clamp(result.get("prompt_adherence", 50))
            + 0.20 * _clamp(result.get("visual_flow", 50))
        )),
        per_scene=result.get("per_scene", []),
        raw_response=result,
    )


def _check_images(image: 'ImageScores') -> list:
    """Generate issues from image scoring results."""
    issues = []
    th = THRESHOLDS.get("images")
    if not th or image.overall == 0:
        return issues

    if image.style_consistency < th.min_style_consistency:
        issues.append(Issue(
            "storyboard", "warning",
            f"Image style consistency low: {image.style_consistency}/100 (min {th.min_style_consistency})",
            "Generated images don't share a consistent visual style",
            "Add style note: 'All images must share identical color palette, lighting style, and render technique'",
            "img_style_consistency", image.style_consistency, th.min_style_consistency,
        ))

    if image.prompt_adherence < th.min_prompt_adherence:
        issues.append(Issue(
            "scenes", "warning",
            f"Image-prompt adherence low: {image.prompt_adherence}/100 (min {th.min_prompt_adherence})",
            "Generated images don't match the scene prompts accurately",
            "Add style note: 'Write prompts with concrete, specific visual details — avoid abstract descriptions'",
            "img_prompt_adherence", image.prompt_adherence, th.min_prompt_adherence,
        ))

    if image.visual_flow < th.min_visual_flow:
        issues.append(Issue(
            "scenes", "warning",
            f"Visual flow between scenes low: {image.visual_flow}/100 (min {th.min_visual_flow})",
            "Storyboard images don't flow as a coherent visual sequence",
            "Add style note: 'Maintain visual continuity — consistent environment, subject, and color temperature across scenes'",
            "img_visual_flow", image.visual_flow, th.min_visual_flow,
        ))

    # Use LLM suggestions from image scoring as issues
    suggestions = image.raw_response.get("suggestions", [])
    for suggestion in suggestions[:3]:
        issues.append(Issue(
            "scenes", "info",
            f"Image feedback: {suggestion}",
            "Gemini vision analysis",
            suggestion,
            "img_suggestion", 0, 0,
        ))

    return issues


# ── Unified Score Computation ────────────────────────────────────────────

def compute_unified_scores(heuristic: HeuristicReport, llm: LLMScores, image: Optional[ImageScores] = None) -> UnifiedScores:
    m = heuristic.metrics

    img = image or ImageScores()
    has_images = img.overall > 0

    # Style Consistency — blend image scoring if available
    shot_rep_penalty = min(50, (m.get("scene_max_consecutive_shot", 1) - 1) * 20)
    if has_images:
        style_consistency = int(0.4 * llm.style_adherence + 0.3 * img.style_consistency + 0.3 * (100 - shot_rep_penalty))
    else:
        style_consistency = int(0.6 * llm.style_adherence + 0.4 * (100 - shot_rep_penalty))

    # Visual Quality — blend image scoring if available
    avg_len = m.get("scene_avg_prompt_length", 150)
    prompt_quality = _clamp(min(100, (avg_len / 200) * 100))
    sb_err = m.get("sb_error_rate", 0)
    sb_penalty = min(100, sb_err * 5)
    if has_images:
        visual_quality = int(0.25 * llm.visual_consistency + 0.25 * img.composition_quality + 0.25 * img.prompt_adherence + 0.25 * (100 - sb_penalty))
    else:
        visual_quality = int(0.4 * llm.visual_consistency + 0.3 * prompt_quality + 0.3 * (100 - sb_penalty))

    # Narrative Coherence
    roles = m.get("scene_roles", {})
    has_hook = 1 if roles.get("hook", 0) > 0 else 0
    has_peak = 1 if roles.get("peak", 0) > 0 else 0
    has_cta = 1 if roles.get("cta", 0) > 0 else 0
    role_arc_score = _clamp(int(has_hook * 40 + has_peak * 40 + has_cta * 20))
    cv = m.get("seg_duration_cv", 0.3)
    evenness_penalty = min(50, int(cv * 80))
    narrative_coherence = int(0.5 * llm.narrative_flow + 0.3 * role_arc_score + 0.2 * (100 - evenness_penalty))

    # Audio-Visual Sync
    max_drift = m.get("cross_max_timing_drift_ms", 0)
    timing_accuracy = _clamp(int(100 - (max_drift / 10)))
    cross_delta = m.get("cross_seg_scene_delta", 0)
    cross_penalty = min(100, cross_delta * 50)
    wps = m.get("tts_wps", 3.0)
    pacing_score = _clamp(int(100 - abs(wps - 3.0) * 30))
    audio_visual_sync = int(0.5 * timing_accuracy + 0.3 * (100 - cross_penalty) + 0.2 * pacing_score)

    # Viral Score
    seg_avg = m.get("seg_avg_duration", 3.0)
    retention_pacing = _clamp(int(100 - abs(seg_avg - 2.5) * 25))
    peak_count = roles.get("peak", 0)
    climax_clarity = 100 if peak_count == 1 else max(0, 100 - abs(peak_count - 1) * 40)
    cta_effectiveness = 80 if has_cta else 30

    viral_breakdown = {
        "hook_strength": llm.hook_strength,
        "retention_pacing": retention_pacing,
        "emotional_progression": llm.emotional_progression,
        "climax_clarity": climax_clarity,
        "cta_effectiveness": cta_effectiveness,
    }
    viral_score = int(
        0.30 * llm.hook_strength
        + 0.25 * retention_pacing
        + 0.20 * llm.emotional_progression
        + 0.15 * climax_clarity
        + 0.10 * cta_effectiveness
    )

    # Overall weighted
    w = WEIGHTS
    overall = (
        w.style_consistency * _clamp(style_consistency)
        + w.visual_quality * _clamp(visual_quality)
        + w.narrative_coherence * _clamp(narrative_coherence)
        + w.audio_visual_sync * _clamp(audio_visual_sync)
        + w.viral_score * _clamp(viral_score)
    )

    return UnifiedScores(
        style_consistency=_clamp(style_consistency),
        visual_quality=_clamp(visual_quality),
        narrative_coherence=_clamp(narrative_coherence),
        audio_visual_sync=_clamp(audio_visual_sync),
        viral_score=_clamp(viral_score),
        viral_breakdown=viral_breakdown,
        overall=round(overall, 1),
    )


# ── Main Entry ───────────────────────────────────────────────────────────

def analyze(snap: PipelineSnapshot, steps: Optional[list] = None) -> AnalysisResult:
    """Full analysis: heuristics + LLM scoring + unified scores."""
    print(f"  Analyzing {snap.project_id}...")
    heuristic = run_heuristics(snap, steps)
    print(f"    Heuristics: {len(heuristic.issues)} issues")

    # Only run LLM scoring if scenes exist and scenes are in scope
    target_steps = steps or ALL_STEPS
    if "scenes" in target_steps and snap.scenes.get("scenes"):
        llm = run_llm_scoring(snap)
        print(f"    LLM: hook={llm.hook_strength} flow={llm.narrative_flow} "
              f"visual={llm.visual_consistency} emotion={llm.emotional_progression} "
              f"style={llm.style_adherence}")
    else:
        llm = LLMScores()
        print("    LLM: skipped (no scenes data or not in scope)")

    # Image scoring if storyboard images exist
    image = ImageScores()
    if "storyboard" in target_steps and _get_storyboard_images(snap):
        image = run_image_scoring(snap)
        print(f"    Images: style={image.style_consistency} comp={image.composition_quality} "
              f"adherence={image.prompt_adherence} flow={image.visual_flow} | overall={image.overall}")
        # Add image-based issues to heuristic report
        img_issues = _check_images(image)
        heuristic.issues.extend(img_issues)
        if img_issues:
            print(f"    Image issues: {len(img_issues)}")
    else:
        print("    Images: skipped (no storyboard images or not in scope)")

    unified = compute_unified_scores(heuristic, llm, image)
    print(f"    Scores: style={unified.style_consistency} visual={unified.visual_quality} "
          f"narrative={unified.narrative_coherence} sync={unified.audio_visual_sync} "
          f"viral={unified.viral_score} | overall={unified.overall}")

    return AnalysisResult(
        heuristic=heuristic,
        llm_scores=llm,
        image_scores=image,
        unified=unified,
        snapshot_id=snap.project_id,
    )
