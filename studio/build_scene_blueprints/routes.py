"""Scenes Module — AI Scene Script Generation Routes"""

import json
import os
import time
from datetime import datetime

import requests as http_requests
from flask import Blueprint, jsonify, request
from loguru import logger

from config import SCENES_DIR, ALIGN_DIR, N8N_WEBHOOK_URL, generate_project_id
from studio.io_utils import safe_json_write
from studio.security import is_safe_webhook_url, sanitize_folder_name, sanitize_project_id
from studio.validation import validate_json
from studio.build_scene_blueprints.schemas import SceneGenerateRequest
from studio.build_scene_blueprints.templates import SCENE_STYLE_TEMPLATES, TEMPLATES_BY_ID
from studio.build_scene_blueprints.style_compiler import public_template_payload, resolve_template_bundle
from studio.build_scene_blueprints.planner import (
    build_scene_blueprints,
    build_visual_bible,
    slice_scene_blueprints,
    summarize_blueprints,
)
from studio.build_scene_blueprints.prompts import build_scene_system_prompt
from studio.build_scene_blueprints.continuity import build_progress_state
from studio.build_scene_blueprints.validators import ensure_analysis_payload, finalize_scene_result
from studio.build_scene_blueprints.chapters import (
    should_use_chapters, group_into_chapters,
    build_chapter_system_prompt, merge_chapter_results,
    chunk_segments, build_script_window, validate_scene_indexes,
)

scenes_bp = Blueprint("scenes", __name__)


# ---------------------------------------------------------------------------
# Segment normalization
# ---------------------------------------------------------------------------

def _normalize_segments(segments):
    """Normalize segments from mixed formats to [{index, words, ...}] dicts.

    Accepts:
      - Plain strings: ["text1", "text2"] -> [{index:0, words:"text1"}, ...]
      - SegmentItem objects: preserved with model_dump()
      - Dicts: passed through
    """
    result = []
    for i, seg in enumerate(segments):
        if isinstance(seg, str):
            result.append({"index": i, "words": seg})
        elif hasattr(seg, "model_dump"):
            result.append(seg.model_dump())
        elif isinstance(seg, dict):
            result.append(seg)
        else:
            result.append({"index": i, "words": str(seg)})
    return result


def _normalize_webhook_response(result):
    """Normalize webhook response to expected {scenes: [...]} format.

    Handles both:
      - Current format: {analysis, scenes: [{index, image_prompt, type_of_scene, ...}]}
      - Simplified format: {analysis, segments: [{index, prompt, type, ...}]}
    """
    if not isinstance(result, dict):
        return result

    if "segments" in result and "scenes" not in result:
        scenes = []
        for seg in result["segments"]:
            scene = {
                "index": seg.get("index"),
                "image_prompt": seg.get("prompt", seg.get("image_prompt", "")),
                "type_of_scene": seg.get("type", seg.get("type_of_scene", "video")),
                "title": seg.get("title", ""),
                "narrative_role": seg.get("narrative_role", "buildup"),
                "text_content": seg.get("text_content"),
            }
            scenes.append(scene)
        result["scenes"] = scenes
        del result["segments"]

    return result


def _planning_segments(segments, full_segments=None):
    if full_segments:
        speech = [dict(seg) for seg in full_segments if not seg.get("is_filler")]
        if speech:
            return speech
    return [dict(seg) for seg in segments]


def _build_generation_context(script, style_id, segments, full_segments=None, custom_style_notes=""):
    planning_segments = _planning_segments(segments, full_segments)
    bundle = resolve_template_bundle(style_id, TEMPLATES_BY_ID, custom_style_notes)
    visual_bible = build_visual_bible(script, planning_segments, bundle["style_spec"])
    scene_blueprints = build_scene_blueprints(planning_segments, visual_bible, bundle["style_spec"])
    plan_summary = summarize_blueprints(scene_blueprints)
    return bundle, visual_bible, scene_blueprints, plan_summary


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

def _coerce_float(value):
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _build_timed_segment_refs(segments, full_segments=None):
    """Return speech segments with stable timing, ordered by time."""
    merged_by_index = {}

    for seg in full_segments or []:
        if seg.get("is_filler"):
            continue
        try:
            idx = int(seg.get("index"))
        except (TypeError, ValueError):
            continue
        merged_by_index[idx] = dict(seg)

    ordered = []
    seen = set()
    for seg in segments or []:
        try:
            idx = int(seg.get("index"))
        except (TypeError, ValueError):
            continue
        base = dict(merged_by_index.get(idx, {}))
        base.update(seg)
        start = _coerce_float(base.get("start"))
        end = _coerce_float(base.get("end"))
        if start is None or end is None or end < start:
            continue
        base["index"] = idx
        base["start"] = start
        base["end"] = end
        base["duration"] = round(end - start, 3)
        merged_by_index[idx] = base
        if idx not in seen:
            ordered.append(base)
            seen.add(idx)

    if not ordered:
        for idx, seg in merged_by_index.items():
            start = _coerce_float(seg.get("start"))
            end = _coerce_float(seg.get("end"))
            if start is None or end is None or end < start:
                continue
            seg["index"] = idx
            seg["start"] = start
            seg["end"] = end
            seg["duration"] = round(end - start, 3)
            ordered.append(seg)

    ordered.sort(key=lambda seg: (seg["start"], seg["index"]))

    total_end = 0.0
    for seg in full_segments or []:
        end = _coerce_float(seg.get("end"))
        if end is not None:
            total_end = max(total_end, end)
    if total_end <= 0 and ordered:
        total_end = ordered[-1]["end"]

    return ordered, round(total_end, 3)


def _apply_segmenter_timing(result, segments, full_segments=None):
    """Make segmenter timing the source of truth for saved scene placement."""
    scenes = result.get("scenes", []) if isinstance(result, dict) else []
    if not scenes:
        return

    timed_segments, total_end = _build_timed_segment_refs(segments, full_segments)
    if not timed_segments:
        return

    missing, unexpected = validate_scene_indexes(result, timed_segments)
    if missing or unexpected:
        raise RuntimeError(
            f"scene index mismatch (missing={missing}, unexpected={unexpected})"
        )

    scene_by_index = {}
    for scene in scenes:
        try:
            idx = int(scene.get("index"))
        except (TypeError, ValueError, AttributeError):
            continue
        scene_by_index[idx] = scene

    ordered_scenes = []
    for pos, seg in enumerate(timed_segments):
        scene = scene_by_index[seg["index"]]
        timeline_start = 0.0 if pos == 0 else seg["start"]
        next_start = timed_segments[pos + 1]["start"] if pos + 1 < len(timed_segments) else total_end
        timeline_end = max(next_start, timeline_start)
        visual_duration = round(timeline_end - timeline_start, 3)
        speech_duration = round(seg["end"] - seg["start"], 3)

        # Enforce minimum scene duration (too-short scenes produce unusable video)
        MIN_SCENE_DURATION = 1.5
        if visual_duration < MIN_SCENE_DURATION:
            visual_duration = MIN_SCENE_DURATION
            timeline_end = timeline_start + visual_duration

        original_duration = scene.get("duration")
        if original_duration is not None:
            scene["model_duration"] = original_duration

        scene["timestamp"] = timeline_start
        scene["timeline_start"] = timeline_start
        scene["timeline_end"] = timeline_end
        scene["duration"] = visual_duration
        scene["segment_start"] = seg["start"]
        scene["segment_end"] = seg["end"]
        scene["segment_duration"] = speech_duration
        scene["segment_words"] = seg.get("words", "")
        ordered_scenes.append(scene)

    result["scenes"] = ordered_scenes
    final_end = max(
        (_coerce_float(scene.get("timeline_end")) or 0.0)
        for scene in ordered_scenes
    )
    result["total_duration"] = round(max(total_end, final_end), 3)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@scenes_bp.route("/api/scenes/templates")
def get_templates():
    """Return all available scene style templates."""
    return jsonify([public_template_payload(template) for template in SCENE_STYLE_TEMPLATES])


@scenes_bp.route("/api/scenes/webhook-url")
def get_webhook_url():
    """Return the current scene webhook URL."""
    return jsonify({"url": N8N_WEBHOOK_URL})


@scenes_bp.route("/api/scenes/generate", methods=["POST"])
@validate_json(SceneGenerateRequest)
def generate_scenes(data: SceneGenerateRequest):
    """Forward segmented data to n8n webhook for AI scene generation.

    Accepts JSON body:
      - script: full transcript text
      - style: visual style preset
      - segments: array of {index, words} (non-filler segments only)
      - full_segments: optional full segment list (with fillers) for chapter mode
      - source_folder, aspect_ratio: optional metadata
      - webhook_url: optional override for the webhook URL
    """
    style_id = data.style
    custom_style_notes = getattr(data, "custom_style_notes", None) or data.style_prompt or ""
    webhook_url = data.webhook_url or N8N_WEBHOOK_URL
    allow_private = os.environ.get("STS_ALLOW_PRIVATE_WEBHOOKS", "true").lower() == "true"
    if not is_safe_webhook_url(webhook_url, allow_private=allow_private):
        return jsonify({"error": "Unsafe webhook URL"}), 400
    script = data.script

    segments_raw = _normalize_segments(data.segments)
    full_segments_raw = data.full_segments or []
    bundle, visual_bible, scene_blueprints, plan_summary = _build_generation_context(
        script,
        style_id,
        segments_raw,
        full_segments_raw,
        custom_style_notes,
    )

    # Strip timing for webhook — LLM only sees {index, words}
    segments_for_webhook = [
        {"index": s["index"], "words": s["words"]} for s in segments_raw
    ]

    started = time.perf_counter()

    try:
        # Check if we should use chapter-based generation
        full_segments = full_segments_raw
        if full_segments and should_use_chapters(full_segments):
            result = _generate_with_chapters(
                script,
                style_id,
                bundle["style_spec"],
                bundle["style_prompt"],
                visual_bible,
                scene_blueprints,
                plan_summary,
                full_segments,
                webhook_url,
                custom_style_notes,
            )
        else:
            system_prompt = build_scene_system_prompt(
                bundle["style_spec"],
                visual_bible,
                scene_blueprints,
                plan_summary=plan_summary,
                custom_style_notes=custom_style_notes,
            )
            result = _call_webhook(webhook_url, {
                "script": script,
                "style": style_id,
                "style_prompt": bundle["style_prompt"],
                "system_prompt": system_prompt,
                "segments": segments_for_webhook,
                "style_spec": bundle["style_spec"],
                "visual_bible": visual_bible,
                "scene_blueprints": scene_blueprints,
                "plan_summary": plan_summary,
            })
        result = _normalize_webhook_response(result)
        _apply_segmenter_timing(result, segments_raw, full_segments_raw)
        ensure_analysis_payload(result, visual_bible, bundle["style_spec"], bundle["template"])
        result["style_spec"] = bundle["style_spec"]
        result["style_prompt"] = bundle["style_prompt"]
        result["scene_blueprints"] = scene_blueprints
        finalize_scene_result(result, scene_blueprints, visual_bible)

        # Save to disk
        project_id_raw = (data.project_id or result.get("pp_randomId")
                          or result.get("project_id") or generate_project_id("pm"))
        project_id = sanitize_project_id(project_id_raw)
        if not project_id:
            return jsonify({"error": "Invalid project id"}), 400
        result["project_id"] = project_id
        result["timestamp"] = datetime.now().isoformat()
        result["generation_time"] = round(time.perf_counter() - started, 3)
        result["source_folder"] = sanitize_folder_name(data.source_folder or "")
        result["style"] = style_id
        if custom_style_notes:
            result["custom_style_notes"] = custom_style_notes
        if data.parent_id:
            result["parent_id"] = data.parent_id

        safe_json_write(os.path.join(SCENES_DIR, project_id, "scenes.json"), result, indent=2)

        logger.success("Generated {} scenes -> {}", len(result.get("scenes", [])), project_id)
        return jsonify(result)

    except http_requests.Timeout:
        return jsonify({"error": "Webhook timed out (300s). Your n8n workflow may need more time — check if the LLM node has a timeout setting."}), 504
    except http_requests.RequestException as e:
        logger.error("Scene webhook request error: {!r}", e)
        return jsonify({"error": f"Webhook connection error: {e}"}), 502
    except Exception as e:
        logger.exception("Unexpected error in scene generation")
        return jsonify({"error": f"Server error: {e}"}), 500


# ---------------------------------------------------------------------------
# Chapter-based generation
# ---------------------------------------------------------------------------

def generate_with_chapters_chunked(script, style_id, style_spec, style_prompt,
                                   visual_bible, scene_blueprints, plan_summary,
                                   full_segments, webhook_url, progress_cb=None,
                                   custom_style_notes=""):
    """Generate scenes in chapter mode with digestible payload chunks.

    Each chapter is split into small segment batches and validated to ensure
    all expected indexes are returned, preventing silent scene drops.
    """
    chapters = group_into_chapters(full_segments)
    total = len(chapters)
    expected_total = sum(len(c["segments"]) for c in chapters)
    logger.info("Chapter mode: {} chapters from {} segments",
                total, expected_total)

    chapter_results = []
    analysis = None
    failed_chapters = []
    generated_scenes = []

    for i, ch in enumerate(chapters):
        chapter_no = i + 1
        script_window = build_script_window(chapters, i)
        chunk_size = 8
        chapter_done = False

        while not chapter_done:
            seg_chunks = chunk_segments(ch["segments"], chunk_size=chunk_size)
            chunk_results = []
            logger.info("Generating Chapter {}/{}: {} segments as {} chunk(s) of <= {}",
                        chapter_no, total, len(ch["segments"]), len(seg_chunks), chunk_size)
            if progress_cb:
                progress_cb(
                    f"Chapter {chapter_no}/{total}: {len(ch['segments'])} segments "
                    f"in {len(seg_chunks)} chunk(s)"
                )

            try:
                for chunk_idx, seg_chunk in enumerate(seg_chunks, start=1):
                    chunk_blueprints = slice_scene_blueprints(scene_blueprints, seg_chunk)
                    continuation_state = build_progress_state(
                        generated_scenes,
                        visual_bible,
                        plan_summary,
                    ) if generated_scenes else None
                    prompt = build_chapter_system_prompt(
                        style_spec,
                        visual_bible,
                        chunk_blueprints,
                        analysis,
                        i,
                        total,
                        chapters,
                        plan_summary=plan_summary,
                        continuation_state=continuation_state,
                        custom_style_notes=custom_style_notes,
                    )
                    payload = {
                        "script": script_window,
                        "style": style_id,
                        "style_prompt": style_prompt,
                        "system_prompt": prompt,
                        "segments": seg_chunk,
                        "style_spec": style_spec,
                        "visual_bible": visual_bible,
                        "scene_blueprints": chunk_blueprints,
                        "plan_summary": plan_summary,
                        "continuation_state": continuation_state or {},
                        "chapter": chapter_no,
                        "total_chapters": total,
                        "chapter_chunk": chunk_idx,
                        "chapter_chunk_total": len(seg_chunks),
                    }

                    if progress_cb:
                        progress_cb(
                            f"Chapter {chapter_no}/{total}, chunk {chunk_idx}/{len(seg_chunks)}: "
                            f"{len(seg_chunk)} segments"
                        )
                    result = _normalize_webhook_response(
                        _call_webhook(webhook_url, payload, timeout=300)
                    )
                    missing, unexpected = validate_scene_indexes(result, seg_chunk)
                    if missing or unexpected:
                        raise RuntimeError(
                            f"chapter {chapter_no} chunk {chunk_idx} mismatch "
                            f"(missing={missing}, unexpected={unexpected})"
                        )
                    chunk_results.append(result)
                    generated_scenes.extend(result.get("scenes", []))

                    if analysis is None and result.get("analysis"):
                        analysis = result["analysis"]

                chapter_results.append(merge_chapter_results(chunk_results))
                chapter_done = True

            except Exception as e:
                logger.error("Chapter {}/{} failed at chunk_size {}: {}",
                             chapter_no, total, chunk_size, e)
                if chunk_size <= 3:
                    failed_chapters.append(chapter_no)
                    if chapter_no == 1:
                        raise
                    break
                chunk_size = max(3, chunk_size // 2)
                logger.warning("Retrying chapter {}/{} with smaller chunk_size={}",
                               chapter_no, total, chunk_size)

    merged = merge_chapter_results(chapter_results)
    scene_count = len(merged.get("scenes", []))
    if failed_chapters:
        merged.setdefault("warnings", []).append(
            f"Chapters {failed_chapters} failed and were skipped — "
            f"{len(chapter_results)}/{total} chapters completed"
        )
    if scene_count != expected_total:
        raise RuntimeError(
            f"Scene count mismatch after chunked generation: got {scene_count}, "
            f"expected {expected_total}"
        )
    return merged


def _generate_with_chapters(script, style_id, style_spec, style_prompt,
                            visual_bible, scene_blueprints, plan_summary,
                            full_segments, webhook_url,
                            custom_style_notes=""):
    """Backward-compatible wrapper used by /api/scenes/generate."""
    return generate_with_chapters_chunked(
        script,
        style_id,
        style_spec,
        style_prompt,
        visual_bible,
        scene_blueprints,
        plan_summary,
        full_segments,
        webhook_url,
        custom_style_notes=custom_style_notes,
    )


# ---------------------------------------------------------------------------
# Webhook helpers — delegate to shared module
# ---------------------------------------------------------------------------

from studio.webhooks import call_webhook as _call_webhook  # noqa: E402


# ---------------------------------------------------------------------------
# Other routes
# ---------------------------------------------------------------------------

@scenes_bp.route("/api/scenes/history")
def list_scenes():
    """List all generated scene projects."""
    items = []
    if not os.path.exists(SCENES_DIR):
        return jsonify(items)
    for entry in os.listdir(SCENES_DIR):
        json_path = os.path.join(SCENES_DIR, entry, "scenes.json")
        if os.path.isfile(json_path):
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
                item = {
                    "project_id": data.get("project_id", entry),
                    "scene_count": len(data.get("scenes", [])),
                    "timestamp": data.get("timestamp", ""),
                    "source_folder": data.get("source_folder", ""),
                    "style": data.get("style", ""),
                    "generation_time": (
                        data.get("generation_time")
                        or (data.get("pipeline_timing", {}) or {}).get("scenes", 0)
                    ),
                }
                if data.get("parent_id"):
                    item["parent_id"] = data["parent_id"]
                items.append(item)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
                logger.debug("Skipping unreadable scenes history entry {}: {}", json_path, error)
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return jsonify(items)


@scenes_bp.route("/api/scenes/<project_id>")
def get_scenes(project_id):
    """Get full scene data for a project."""
    project_id = os.path.basename(project_id)
    json_path = os.path.join(SCENES_DIR, project_id, "scenes.json")
    if not os.path.isfile(json_path):
        return jsonify({"error": "Not found"}), 404
    try:
        with open(json_path, encoding="utf-8") as f:
            return jsonify(json.load(f))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        return jsonify({"error": f"Failed to read scene data: {e}"}), 500


@scenes_bp.route("/api/scenes/audio/<source_folder>")
def get_scene_audio(source_folder):
    """Resolve audio file URL for a source folder."""
    source_folder = os.path.basename(source_folder)
    folder_path = os.path.join(ALIGN_DIR, source_folder)
    if not os.path.isdir(folder_path):
        return jsonify({"error": "Not found"}), 404
    for f in os.listdir(folder_path):
        if f.endswith((".wav", ".mp3")):
            return jsonify({"url": f"/output/alignments/{source_folder}/{f}"})
    return jsonify({"error": "No audio file found"}), 404
