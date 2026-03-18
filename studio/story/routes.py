"""Story Module — AI Story Generation Routes

Provides:
  POST /api/story/generate       — generate a story via n8n/Gemini webhook
  GET  /api/story/webhook-url    — return the configured story webhook URL
  GET  /api/story/history        — list generated stories
  GET  /api/story/<project_id>   — get a specific story
  GET  /api/story/categories     — list available story categories
"""

import json
import os
import time
from datetime import datetime

import requests as http_requests
from flask import Blueprint, jsonify, request
from loguru import logger

from config import STORIES_DIR, N8N_STORY_WEBHOOK_URL, generate_project_id
from studio.io_utils import safe_json_write
from studio.security import is_safe_webhook_url, sanitize_project_id
from studio.validation import validate_json
from studio.story.schemas import StoryGenerateRequest
from studio.story.prompts import (
    build_story_system_prompt,
    build_story_user_prompt,
    compute_word_target,
    STORY_CATEGORIES,
)
from studio.story.engine import parse_story_sections

story_bp = Blueprint("story", __name__)

# ---------------------------------------------------------------------------
# Webhook helper (reuses pattern from scenes module)
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BASE_DELAY = 2
_RETRYABLE_STATUS = {502, 503, 504, 429}


def _call_story_webhook(webhook_url, payload, timeout=120):
    """POST payload to story webhook with retry + exponential backoff."""
    last_exc = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = http_requests.post(webhook_url, json=payload, timeout=timeout)

            if resp.status_code in _RETRYABLE_STATUS:
                body_text = resp.text[:300]
                logger.warning(
                    "Story webhook returned {} (attempt {}/{})",
                    resp.status_code, attempt, _MAX_RETRIES,
                )
                last_exc = RuntimeError(f"Webhook returned {resp.status_code}: {body_text[:200]}")
                if attempt < _MAX_RETRIES:
                    time.sleep(_BASE_DELAY * (2 ** (attempt - 1)))
                    continue
                raise last_exc

            if resp.status_code != 200:
                body_text = resp.text[:500]
                raise RuntimeError(f"Webhook returned {resp.status_code}: {body_text[:200]}")

            body = resp.text.strip()
            if not body:
                raise RuntimeError("Webhook returned an empty response")

            result = json.loads(body)
            if isinstance(result, list):
                result = result[0] if result else {}
            return result

        except (http_requests.ConnectionError, http_requests.Timeout) as e:
            logger.warning("Story webhook {} (attempt {}/{}): {}", type(e).__name__, attempt, _MAX_RETRIES, e)
            last_exc = e
            if attempt < _MAX_RETRIES:
                time.sleep(_BASE_DELAY * (2 ** (attempt - 1)))
                continue
            raise

    raise last_exc


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@story_bp.route("/api/story/webhook-url")
def get_webhook_url():
    """Return the configured story webhook URL."""
    return jsonify({"url": N8N_STORY_WEBHOOK_URL})


@story_bp.route("/api/story/categories")
def get_categories():
    """Return available story categories."""
    return jsonify(STORY_CATEGORIES)


@story_bp.route("/api/story/generate", methods=["POST"])
@validate_json(StoryGenerateRequest)
def generate_story(data: StoryGenerateRequest):
    """Generate a story via n8n webhook (Gemini provider).

    Accepts JSON body:
      - preset_style: visual style preset ID
      - story_category: story genre/category
      - duration: target duration in seconds (15-180)
      - language: output language (english, french, spanish)
      - project_name_id: optional existing project ID to link to
      - webhook_url: optional override for the webhook URL
    """
    webhook_url = data.webhook_url or N8N_STORY_WEBHOOK_URL
    allow_private = os.environ.get("STS_ALLOW_PRIVATE_WEBHOOKS", "true").lower() == "true"
    if not is_safe_webhook_url(webhook_url, allow_private=allow_private):
        return jsonify({"error": "Unsafe webhook URL"}), 400

    system_prompt = build_story_system_prompt(
        data.preset_style, data.story_category, data.duration, data.language,
    )
    user_prompt = build_story_user_prompt(
        data.preset_style, data.story_category, data.duration, data.language,
    )
    word_target = compute_word_target(data.duration)

    payload = {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "preset_style": data.preset_style,
        "story_category": data.story_category,
        "duration": data.duration,
        "language": data.language,
        "word_target": word_target,
        "structure": ["hook", "build", "climax", "cta"],
    }

    started = time.perf_counter()

    try:
        result = _call_story_webhook(webhook_url, payload)

        # Extract story text — webhook may return {story_text} or {output} or {text}
        raw_text = (
            result.get("story_text")
            or result.get("output")
            or result.get("text")
            or result.get("response")
            or ""
        )
        if not raw_text:
            return jsonify({"error": "Webhook returned no story text"}), 502

        parsed = parse_story_sections(raw_text)
        generation_time = round(time.perf_counter() - started, 3)

        # Generate project ID
        project_id = sanitize_project_id(
            data.project_name_id or generate_project_id("ps")
        )
        if not project_id:
            project_id = generate_project_id("ps")

        # Build response
        estimated_duration = round(parsed["word_count"] / 2.5)
        response = {
            "success": True,
            "project_id": project_id,
            "story_text": parsed["story_text"],
            "sections": parsed["sections"],
            "duration": data.duration,
            "estimated_duration": estimated_duration,
            "language": data.language,
            "story_category": data.story_category,
            "preset_style": data.preset_style,
            "provider": "gemini",
            "word_count": parsed["word_count"],
            "generation_time": generation_time,
            "timestamp": datetime.now().isoformat(),
        }

        # Save to disk
        story_data = {
            "project_id": project_id,
            "story_text": parsed["story_text"],
            "sections": parsed["sections"],
            "metadata": {
                "preset_style": data.preset_style,
                "language": data.language,
                "story_category": data.story_category,
                "duration": data.duration,
                "word_count": parsed["word_count"],
                "estimated_duration": estimated_duration,
                "provider": "gemini",
                "generation_time": generation_time,
                "timestamp": response["timestamp"],
            },
            "pipeline_ref": {
                "tts_project_id": None,
                "scenes_project_id": None,
            },
        }

        safe_json_write(
            os.path.join(STORIES_DIR, project_id, "story.json"),
            story_data,
            indent=2,
        )

        logger.success("Generated story -> {} ({} words, {:.1f}s)", project_id, parsed["word_count"], generation_time)
        return jsonify(response)

    except http_requests.Timeout:
        return jsonify({"error": "Story webhook timed out. Check your n8n workflow."}), 504
    except http_requests.RequestException as e:
        logger.error("Story webhook request error: {!r}", e)
        return jsonify({"error": f"Webhook connection error: {e}"}), 502
    except Exception as e:
        logger.exception("Unexpected error in story generation")
        return jsonify({"error": f"Server error: {e}"}), 500


@story_bp.route("/api/story/history")
def list_stories():
    """List all generated stories."""
    items = []
    if not os.path.exists(STORIES_DIR):
        return jsonify(items)
    for entry in os.listdir(STORIES_DIR):
        json_path = os.path.join(STORIES_DIR, entry, "story.json")
        if os.path.isfile(json_path):
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
                meta = data.get("metadata", {})
                items.append({
                    "project_id": data.get("project_id", entry),
                    "story_category": meta.get("story_category", ""),
                    "language": meta.get("language", ""),
                    "preset_style": meta.get("preset_style", ""),
                    "duration": meta.get("duration", 0),
                    "word_count": meta.get("word_count", 0),
                    "timestamp": meta.get("timestamp", ""),
                    "preview": (data.get("story_text") or "")[:100],
                })
            except (json.JSONDecodeError, OSError) as error:
                logger.debug("Skipping unreadable story entry {}: {}", json_path, error)
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return jsonify(items)


@story_bp.route("/api/story/<project_id>")
def get_story(project_id):
    """Get full story data for a project."""
    project_id = os.path.basename(project_id)
    json_path = os.path.join(STORIES_DIR, project_id, "story.json")
    if not os.path.isfile(json_path):
        return jsonify({"error": "Not found"}), 404
    try:
        with open(json_path, encoding="utf-8") as f:
            return jsonify(json.load(f))
    except (json.JSONDecodeError, OSError) as e:
        return jsonify({"error": f"Failed to read story data: {e}"}), 500
