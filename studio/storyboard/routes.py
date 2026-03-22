"""Storyboard Module — Reference Image Generation via n8n Webhook.

Generates one reference image per scene using WaveSpeed AI (via n8n webhook),
downloads them to output/storyboard/{project_id}/, and tracks per-scene status.

Provides:
  POST /api/storyboard/generate                    — start storyboard generation
  GET  /api/storyboard/status/<project_id>          — poll per-scene status
  GET  /api/storyboard/images/<project_id>          — list generated images
  GET  /api/storyboard/images/<project_id>/<scene>  — serve individual image
"""

import os
import threading
import time
from datetime import datetime
from urllib.parse import urlparse

import requests as http_requests
from flask import Blueprint, jsonify, request, send_from_directory
from loguru import logger

from config import STORYBOARD_DIR, N8N_ASSET_WEBHOOK_URL
from studio.io_utils import safe_json_write, safe_json_read
from studio.security import sanitize_project_id
from studio.validation import validate_json
from studio.webhooks import call_webhook
from .schemas import StoryboardGenerateRequest

storyboard_bp = Blueprint("storyboard", __name__)

# ---------------------------------------------------------------------------
# In-memory job tracking
# ---------------------------------------------------------------------------
_jobs = {}
_jobs_lock = threading.Lock()

MAX_DL_RETRIES = 3
DL_RETRY_DELAY = 2  # seconds

_DL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


def _get_job(project_id):
    with _jobs_lock:
        return _jobs.get(project_id)


def _set_job(project_id, job):
    with _jobs_lock:
        _jobs[project_id] = job


def _now_iso():
    return datetime.now().astimezone().isoformat()


def _storyboard_dir(project_id):
    return os.path.join(STORYBOARD_DIR, project_id)


def _storyboard_json_path(project_id):
    return os.path.join(_storyboard_dir(project_id), "storyboard.json")


def _save_storyboard_json(project_id, job):
    """Persist storyboard state to disk."""
    try:
        safe_json_write(_storyboard_json_path(project_id), job, indent=2)
    except Exception as e:
        logger.error("Failed to save storyboard.json for {}: {}", project_id, e)


# ---------------------------------------------------------------------------
# Image download
# ---------------------------------------------------------------------------

def _download_image(url, dest_path):
    """Download an image URL to a local file with retries."""
    parsed = urlparse(url)
    headers = {**_DL_HEADERS, "Referer": f"{parsed.scheme}://{parsed.netloc}/"}

    for attempt in range(1, MAX_DL_RETRIES + 1):
        try:
            resp = http_requests.get(url, headers=headers, timeout=120, stream=True)
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            size_kb = os.path.getsize(dest_path) / 1024
            logger.info("Storyboard image downloaded ({:.0f} KB): {}", size_kb, dest_path)
            return True
        except Exception as e:
            logger.warning("Download attempt {}/{} failed for {}: {}",
                           attempt, MAX_DL_RETRIES, dest_path, e)
            if os.path.isfile(dest_path):
                os.remove(dest_path)
            if attempt < MAX_DL_RETRIES:
                time.sleep(DL_RETRY_DELAY * attempt)
    return False


# ---------------------------------------------------------------------------
# Background generation
# ---------------------------------------------------------------------------

def _generate_storyboard(project_id, scenes, aspect_ratio, webhook_url):
    """Background thread: generate one image per scene sequentially via n8n webhook."""
    job = _get_job(project_id)
    if not job:
        return

    project_dir = _storyboard_dir(project_id)
    os.makedirs(project_dir, exist_ok=True)
    url = webhook_url or N8N_ASSET_WEBHOOK_URL

    total = len(scenes)
    ready = 0
    errors = 0

    for entry in scenes:
        scene_num = entry["scene"]
        prompt = entry["prompt"]
        scene_key = str(scene_num)

        # Update status
        job["scene_statuses"][scene_key] = {"status": "generating", "image_url": None, "local_path": None}
        _save_storyboard_json(project_id, job)

        try:
            logger.info("[{}] Storyboard scene {} — calling webhook", project_id, scene_num)
            result = call_webhook(
                url,
                {"image_prompt": prompt, "aspect_ratio": aspect_ratio},
                timeout=300,
                label=f"Storyboard scene {scene_num}",
            )

            image_url = result.get("image_url")
            if not image_url:
                raise RuntimeError(f"Webhook returned no image_url: {result}")

            # Download
            job["scene_statuses"][scene_key]["status"] = "downloading"
            _save_storyboard_json(project_id, job)

            ext = ".jpg"
            if image_url.lower().endswith(".png"):
                ext = ".png"
            elif image_url.lower().endswith(".webp"):
                ext = ".webp"
            dest = os.path.join(project_dir, f"{scene_num}{ext}")

            if _download_image(image_url, dest):
                local_path = f"/output/storyboard/{project_id}/{scene_num}{ext}"
                job["scene_statuses"][scene_key] = {
                    "status": "ready",
                    "image_url": image_url,
                    "local_path": local_path,
                }
                ready += 1
                logger.success("[{}] Storyboard scene {} ready", project_id, scene_num)
            else:
                job["scene_statuses"][scene_key] = {
                    "status": "error",
                    "image_url": image_url,
                    "local_path": None,
                    "error": "Download failed after retries",
                }
                errors += 1

        except Exception as e:
            logger.error("[{}] Storyboard scene {} failed: {}", project_id, scene_num, e)
            job["scene_statuses"][scene_key] = {
                "status": "error",
                "image_url": None,
                "local_path": None,
                "error": str(e),
            }
            errors += 1

        _save_storyboard_json(project_id, job)

    # Finalize
    job["status"] = "done"
    job["completed_at"] = _now_iso()
    job["ready"] = ready
    job["errors"] = errors
    job["total"] = total
    _save_storyboard_json(project_id, job)
    _set_job(project_id, job)
    logger.success("[{}] Storyboard complete — {}/{} ready, {} errors",
                   project_id, ready, total, errors)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@storyboard_bp.route("/api/storyboard/generate", methods=["POST"])
@validate_json(StoryboardGenerateRequest)
def generate(data: StoryboardGenerateRequest):
    """Start storyboard image generation for a project."""
    project_id = sanitize_project_id(data.project_id)
    scenes = [{"scene": s.scene, "prompt": s.prompt} for s in data.scenes]

    job = {
        "project_id": project_id,
        "status": "running",
        "total": len(scenes),
        "ready": 0,
        "errors": 0,
        "aspect_ratio": data.aspect_ratio,
        "created_at": _now_iso(),
        "completed_at": None,
        "scene_statuses": {
            str(s["scene"]): {"status": "pending", "image_url": None, "local_path": None}
            for s in scenes
        },
    }
    _set_job(project_id, job)
    _save_storyboard_json(project_id, job)

    t = threading.Thread(
        target=_generate_storyboard,
        args=(project_id, scenes, data.aspect_ratio, data.webhook_url),
        daemon=True,
    )
    t.start()

    logger.info("[{}] Storyboard generation started — {} scenes", project_id, len(scenes))
    return jsonify({"status": "running", "project_id": project_id, "total": len(scenes)}), 202


@storyboard_bp.route("/api/storyboard/status/<project_id>")
def status(project_id):
    """Poll storyboard generation status."""
    project_id = sanitize_project_id(project_id)
    job = _get_job(project_id)

    # Fallback: load from disk
    if not job:
        json_path = _storyboard_json_path(project_id)
        if os.path.isfile(json_path):
            try:
                job = safe_json_read(json_path)
                _set_job(project_id, job)
            except Exception:
                pass

    if not job:
        return jsonify({"error": "No storyboard job found for this project"}), 404

    scene_statuses = job.get("scene_statuses", {})
    total = len(scene_statuses)
    ready = sum(1 for s in scene_statuses.values() if s.get("status") == "ready")
    errors = sum(1 for s in scene_statuses.values() if s.get("status") == "error")

    return jsonify({
        "project_id": project_id,
        "status": job.get("status", "unknown"),
        "total": total,
        "ready": ready,
        "errors": errors,
        "scene_statuses": scene_statuses,
        "created_at": job.get("created_at"),
        "completed_at": job.get("completed_at"),
    })


@storyboard_bp.route("/api/storyboard/images/<project_id>")
def list_images(project_id):
    """List generated storyboard images for a project."""
    project_id = sanitize_project_id(project_id)
    project_dir = _storyboard_dir(project_id)

    if not os.path.isdir(project_dir):
        return jsonify({"error": "No storyboard found for this project"}), 404

    images = []
    for entry in sorted(os.scandir(project_dir), key=lambda e: e.name):
        if entry.is_file() and entry.name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            images.append({
                "filename": entry.name,
                "path": f"/output/storyboard/{project_id}/{entry.name}",
                "size_bytes": entry.stat().st_size,
            })

    return jsonify({"project_id": project_id, "images": images, "count": len(images)})


@storyboard_bp.route("/api/storyboard/images/<project_id>/<path:filename>")
def serve_image(project_id, filename):
    """Serve an individual storyboard image file."""
    project_id = sanitize_project_id(project_id)
    project_dir = _storyboard_dir(project_id)

    if not os.path.isfile(os.path.join(project_dir, filename)):
        return jsonify({"error": "Image not found"}), 404

    return send_from_directory(project_dir, filename)


@storyboard_bp.route("/output/storyboard/<path:filename>")
def serve_output(filename):
    """Serve storyboard files via /output/storyboard/ path (consistency with other modules)."""
    return send_from_directory(STORYBOARD_DIR, filename)
