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
from urllib.parse import urlparse, urlunparse

import requests as http_requests
from flask import Blueprint, jsonify, request
from loguru import logger

from config import STORIES_DIR, N8N_STORY_WEBHOOK_URL, N8N_CLASSIFY_WEBHOOK_URL, generate_project_id
from studio.io_utils import safe_json_write
from studio.security import is_safe_webhook_url, sanitize_project_id
from studio.validation import validate_json
from studio.story.schemas import StoryGenerateRequest
from studio.story.prompts import (
    build_story_system_prompt,
    build_story_user_prompt,
    compute_word_target,
    STORY_CATEGORIES,
    WORDS_PER_SECOND,
)
from studio.story.engine import parse_story_sections
from studio.scenes.templates import SCENE_STYLE_TEMPLATES
from studio.niches.presets import CATEGORIES as NICHE_CATEGORIES

story_bp = Blueprint("story", __name__)

# ---------------------------------------------------------------------------
# Webhook helper — delegate to shared module
# ---------------------------------------------------------------------------

from studio.webhooks import call_webhook  # noqa: E402


def _call_story_webhook(webhook_url, payload, timeout=120):
    return call_webhook(webhook_url, payload, timeout=timeout, label="Story webhook")


def _swap_webhook_suffix(webhook_url, source_suffix, target_suffix):
    """Swap the trailing webhook path segment when the host stays the same."""
    candidate = (webhook_url or "").strip()
    if not candidate:
        return ""

    parsed = urlparse(candidate)
    path = parsed.path or ""
    if not path.endswith(source_suffix):
        return candidate

    swapped = parsed._replace(path=path[: -len(source_suffix)] + target_suffix)
    return urlunparse(swapped)


def _resolve_classify_webhook_url(override_url=""):
    """Resolve the classifier webhook, deriving it from story config when needed."""
    if override_url:
        return _swap_webhook_suffix(
            override_url,
            "/webhook/story-generator",
            "/webhook/classify-style",
        )

    explicit_classify_url = os.environ.get("N8N_CLASSIFY_WEBHOOK_URL", "").strip()
    if explicit_classify_url:
        return explicit_classify_url

    derived_from_story = _swap_webhook_suffix(
        N8N_STORY_WEBHOOK_URL,
        "/webhook/story-generator",
        "/webhook/classify-style",
    )
    if derived_from_story:
        return derived_from_story

    return (N8N_CLASSIFY_WEBHOOK_URL or "").strip()


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
    return jsonify(list(dict.fromkeys([*STORY_CATEGORIES, *NICHE_CATEGORIES])))


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
        story_tone=data.story_tone,
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
        "story_tone": data.story_tone,
        "duration": data.duration,
        "language": data.language,
        "word_target": word_target,
        "structure": ["hook", "build", "climax", "cta"],
    }

    started = time.perf_counter()

    try:
        result = _call_story_webhook(webhook_url, payload)

        # Extract story text — webhook returns {story_text} (preferred) with fallbacks
        raw_text = result.get("story_text", "")
        matched_field = "story_text"
        if not raw_text:
            for field in ("output", "text", "response"):
                raw_text = result.get(field, "")
                if raw_text:
                    matched_field = field
                    logger.info("Story webhook: found text in '{}' field (expected 'story_text')", field)
                    break
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
        estimated_duration = round(parsed["word_count"] / WORDS_PER_SECOND)
        response = {
            "success": True,
            "project_id": project_id,
            "story_text": parsed["story_text"],
            "sections": parsed["sections"],
            "duration": data.duration,
            "estimated_duration": estimated_duration,
            "language": data.language,
            "story_category": data.story_category,
            "story_tone": data.story_tone,
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
                "story_tone": data.story_tone,
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


@story_bp.route("/api/story/classify-style", methods=["POST"])
def classify_style_route():
    """Classify pasted text into the best-matching visual style template via LLM."""
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    # Build concise style list for the LLM
    style_options = [
        {"id": t["id"], "name": t["name"], "description": t["description"]}
        for t in SCENE_STYLE_TEMPLATES
    ]
    style_ids = [s["id"] for s in style_options]

    webhook_url = _resolve_classify_webhook_url(body.get("webhook_url", ""))
    if not webhook_url:
        return jsonify({"error": "N8N_CLASSIFY_WEBHOOK_URL not configured"}), 500
    allow_private = os.environ.get("STS_ALLOW_PRIVATE_WEBHOOKS", "true").lower() == "true"
    if not is_safe_webhook_url(webhook_url, allow_private=allow_private):
        return jsonify({"error": "Unsafe webhook URL"}), 400

    payload = {
        "text": text[:2000],  # limit to avoid huge payloads
        "styles": style_options,
        "system_prompt": (
            "You are a text style classifier. Given a story/script text and a list of visual styles, "
            "pick the single best-matching style for the text's genre, mood, and theme. "
            "Respond with ONLY a JSON object: {\"style_id\": \"<id>\", \"confidence\": <0.0-1.0>, \"reason\": \"<one sentence>\"} "
            "where style_id is one of the provided style IDs. No markdown, no extra text."
        ),
    }

    try:
        resp = http_requests.post(webhook_url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # n8n respondToWebhook returns an array — unwrap if needed
        if isinstance(data, list) and data:
            data = data[0]

        style_id = data.get("style_id", "")
        confidence = data.get("confidence", 0)
        reason = data.get("reason", "")

        # Validate the returned style_id
        if style_id not in style_ids:
            logger.warning("Classify webhook returned unknown style_id: {}", style_id)
            return jsonify({"error": f"Unknown style returned: {style_id}"}), 502

        return jsonify({
            "style_id": style_id,
            "confidence": confidence,
            "reason": reason,
        })
    except http_requests.Timeout:
        return jsonify({"error": "Classification timed out"}), 504
    except http_requests.RequestException as e:
        logger.error("Classify webhook error: {!r}", e)
        return jsonify({"error": f"Classify webhook error: {e}"}), 502
    except (ValueError, KeyError) as e:
        logger.error("Invalid classify response: {!r}", e)
        return jsonify({"error": "Invalid response from classifier"}), 502
