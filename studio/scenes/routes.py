"""Scenes Module — AI Scene Script Generation Routes"""

import json
import os
from datetime import datetime

import requests as http_requests
from flask import Blueprint, jsonify, request
from loguru import logger

from config import SCENES_DIR, ALIGN_DIR, N8N_WEBHOOK_URL, generate_project_id
from studio.scenes.templates import SCENE_STYLE_TEMPLATES, TEMPLATES_BY_ID
from studio.scenes.prompts import SCENE_GENERATOR_PROMPT
from studio.scenes.chapters import (
    should_use_chapters, group_into_chapters,
    build_chapter_system_prompt, merge_chapter_results,
    chunk_segments, build_script_window, validate_scene_indexes,
)

scenes_bp = Blueprint("scenes", __name__)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@scenes_bp.route("/api/scenes/templates")
def get_templates():
    """Return all available scene style templates."""
    return jsonify(SCENE_STYLE_TEMPLATES)


@scenes_bp.route("/api/scenes/webhook-url")
def get_webhook_url():
    """Return the current scene webhook URL."""
    return jsonify({"url": N8N_WEBHOOK_URL})


@scenes_bp.route("/api/scenes/generate", methods=["POST"])
def generate_scenes():
    """Forward segmented data to n8n webhook for AI scene generation.

    Accepts JSON body:
      - script: full transcript text
      - style: visual style preset
      - segments: array of {index, words} (non-filler segments only)
      - full_segments: optional full segment list (with fillers) for chapter mode
      - source_folder, aspect_ratio: optional metadata
      - webhook_url: optional override for the webhook URL
    """
    data = request.get_json(silent=True)
    if not data or not data.get("segments"):
        return jsonify({"error": "No segments data provided"}), 400

    style_id = data.get("style", "cinematic")
    template = TEMPLATES_BY_ID.get(style_id, {})
    style_prompt = data.get("style_prompt") or template.get("style_prompt", "")
    webhook_url = data.get("webhook_url") or N8N_WEBHOOK_URL
    script = data.get("script", "")
    dna_context = {}
    if data.get("dna_consistency"):
        dna_context["dna_consistency"] = data["dna_consistency"]
    if data.get("dna_constraints"):
        dna_context["dna_constraints"] = data["dna_constraints"]

    try:
        # Check if we should use chapter-based generation
        full_segments = data.get("full_segments")
        if full_segments and should_use_chapters(full_segments):
            result = _generate_with_chapters(
                script, style_id, style_prompt, full_segments,
                webhook_url, dna_context,
            )
        else:
            system_prompt = SCENE_GENERATOR_PROMPT
            if style_prompt:
                system_prompt += f"\n\n## STYLE INSTRUCTIONS\n{style_prompt}"
            result = _call_webhook(webhook_url, {
                "script": script,
                "style": style_id,
                "system_prompt": system_prompt,
                "segments": data.get("segments", []),
                **dna_context,
            })

        # Save to disk
        project_id = (data.get("project_id") or result.get("pp_randomId")
                      or result.get("project_id") or generate_project_id("pm"))
        result["project_id"] = project_id
        result["timestamp"] = datetime.now().isoformat()
        result["source_folder"] = data.get("source_folder", "")

        job_dir = os.path.join(SCENES_DIR, project_id)
        os.makedirs(job_dir, exist_ok=True)
        with open(os.path.join(job_dir, "scenes.json"), "w") as f:
            json.dump(result, f, indent=2)

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

def generate_with_chapters_chunked(script, style_id, style_prompt, full_segments,
                                   webhook_url, dna_context, progress_cb=None):
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
                    prompt = build_chapter_system_prompt(
                        SCENE_GENERATOR_PROMPT, style_prompt, analysis,
                        i, total, chapters,
                    )
                    payload = {
                        "script": script_window,
                        "style": style_id,
                        "system_prompt": prompt,
                        "segments": seg_chunk,
                        "chapter": chapter_no,
                        "total_chapters": total,
                        "chapter_chunk": chunk_idx,
                        "chapter_chunk_total": len(seg_chunks),
                        **dna_context,
                    }

                    if progress_cb:
                        progress_cb(
                            f"Chapter {chapter_no}/{total}, chunk {chunk_idx}/{len(seg_chunks)}: "
                            f"{len(seg_chunk)} segments"
                        )
                    result = _call_webhook(webhook_url, payload, timeout=300)
                    missing, unexpected = validate_scene_indexes(result, seg_chunk)
                    if missing or unexpected:
                        raise RuntimeError(
                            f"chapter {chapter_no} chunk {chunk_idx} mismatch "
                            f"(missing={missing}, unexpected={unexpected})"
                        )
                    chunk_results.append(result)

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


def _generate_with_chapters(script, style_id, style_prompt, full_segments,
                            webhook_url, dna_context):
    """Backward-compatible wrapper used by /api/scenes/generate."""
    return generate_with_chapters_chunked(
        script, style_id, style_prompt, full_segments, webhook_url, dna_context
    )


# ---------------------------------------------------------------------------
# Webhook helpers
# ---------------------------------------------------------------------------

def _call_webhook(webhook_url, payload, timeout=180):
    """POST payload to webhook, parse and return the result dict."""
    resp = http_requests.post(webhook_url, json=payload, timeout=timeout)

    if resp.status_code != 200:
        body_text = resp.text[:500]
        logger.error("Scene webhook returned {} — {}", resp.status_code, body_text)
        error_msg = f"Webhook returned {resp.status_code}"
        try:
            err_data = resp.json()
            msg = err_data.get("message", "")
            hint = err_data.get("hint", "")
            if msg:
                error_msg = msg
            if hint:
                error_msg += f". {hint}"
        except Exception:
            if body_text:
                error_msg += f": {body_text[:200]}"
        raise RuntimeError(error_msg)

    body = resp.text.strip()
    if not body:
        raise RuntimeError(
            "Webhook returned an empty response. If using n8n, make sure "
            "the workflow is activated and uses the production URL (/webhook/) "
            "instead of the test URL (/webhook-test/)."
        )

    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"Webhook returned non-JSON response: {body[:200]}")

    # n8n returns an array — unwrap the first element
    if isinstance(result, list):
        if not result:
            raise RuntimeError("Webhook returned an empty array")
        result = result[0]

    if not isinstance(result, dict):
        raise RuntimeError("Webhook returned unexpected format (expected JSON object)")

    return result


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
                with open(json_path) as f:
                    data = json.load(f)
                items.append({
                    "project_id": data.get("project_id", entry),
                    "scene_count": len(data.get("scenes", [])),
                    "timestamp": data.get("timestamp", ""),
                    "source_folder": data.get("source_folder", ""),
                })
            except (json.JSONDecodeError, OSError):
                pass
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
        with open(json_path) as f:
            return jsonify(json.load(f))
    except (json.JSONDecodeError, OSError) as e:
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
