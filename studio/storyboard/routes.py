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
import time
from urllib.parse import urlparse

import requests as http_requests
from flask import Blueprint, jsonify, request, send_from_directory
from loguru import logger

from config import STORYBOARD_DIR, THUMBNAILS_DIR, N8N_STORYBOARD_WEBHOOK_URL, WAVESPEED_API_KEY
from studio.ffmpeg_utils import find_ffmpeg
from studio.io_utils import safe_json_write, safe_json_read, now_iso, JobStore
from studio.security import sanitize_project_id
from studio.validation import validate_json
from studio.webhooks import call_webhook
from .schemas import StoryboardGenerateRequest, StoryboardGrabOneRequest

storyboard_bp = Blueprint("storyboard", __name__)

# ---------------------------------------------------------------------------
# In-memory job tracking
# ---------------------------------------------------------------------------
_jobs = JobStore()

MAX_DL_RETRIES = 3
DL_RETRY_DELAY = 2  # seconds

_DL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


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

THUMB_SIZE = "480:-1"
THUMB_QUALITY = "4"


def _thumb_path(project_id, scene_num):
    """Return the thumbnail path: output/thumbnails/{project_id}/storyboard/{scene}.jpg"""
    return os.path.join(THUMBNAILS_DIR, project_id, "storyboard", f"{scene_num}.jpg")


def _generate_thumbnail(src_path, project_id, scene_num):
    """Generate a JPEG thumbnail into the thumbnails directory."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        logger.warning("ffmpeg not found — skipping thumbnail for {}", src_path)
        return None
    dest_path = _thumb_path(project_id, scene_num)
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        import subprocess
        subprocess.run(
            [ffmpeg, "-y", "-i", src_path,
             "-vf", f"scale={THUMB_SIZE}",
             "-q:v", THUMB_QUALITY, dest_path],
            capture_output=True, timeout=15,
        )
        if os.path.isfile(dest_path):
            return f"/api/thumbnails/{project_id}/storyboard/{scene_num}.jpg"
        return None
    except Exception as e:
        logger.debug("Thumbnail generation failed for {}: {}", src_path, e)
        return None


def _version_existing_image(scene_dir):
    """If image.* exists in scene_dir, rename it to image_v{N}.* to keep history."""
    import glob
    for ext in (".jpeg", ".jpg", ".png", ".webp"):
        current = os.path.join(scene_dir, f"image{ext}")
        if not os.path.isfile(current):
            continue
        # Find next version number
        pattern = os.path.join(scene_dir, f"image_v*{ext}")
        existing = glob.glob(pattern)
        next_v = len(existing) + 1
        versioned = os.path.join(scene_dir, f"image_v{next_v}{ext}")
        os.rename(current, versioned)
        logger.info("Versioned {} → {}", current, versioned)


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

def _generate_storyboard(project_id, scenes, aspect_ratio, webhook_url, style=None, image_model=None):
    """Background thread: generate one image per scene.

    Uses direct WaveSpeed API when the style has a non-default model configured
    in assets/image-models.json. Falls back to n8n webhook for default styles.

    Style consistency comes from prompt engineering — the scene blueprint
    generator appends a shared style/palette suffix to every scene prompt.
    """
    from .wavespeed import is_default_model, generate_image

    job = _jobs.get(project_id)
    if not job:
        return

    project_dir = _storyboard_dir(project_id)
    os.makedirs(project_dir, exist_ok=True)
    url = webhook_url or N8N_STORYBOARD_WEBHOOK_URL

    # Decide whether to use direct WaveSpeed API or n8n webhook
    use_direct = image_model or (style and not is_default_model(style))
    if use_direct:
        logger.info("[{}] Using direct WaveSpeed API (style={}, model={})", project_id, style, image_model or "auto")
    else:
        logger.info("[{}] Using n8n webhook for storyboard", project_id)

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
            if use_direct:
                # Direct WaveSpeed API — model selected by style config or override
                logger.info("[{}] Storyboard scene {} — direct WaveSpeed", project_id, scene_num)
                image_url = generate_image(
                    prompt=prompt,
                    style=style or "default",
                    aspect_ratio=aspect_ratio,
                    model_override=image_model,
                )
            else:
                # n8n webhook (original path)
                payload = {
                    "image_prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "wavespeed_api_key": WAVESPEED_API_KEY,
                    "project_id": project_id,
                    "scene": scene_num,
                }

                logger.info("[{}] Storyboard scene {} — calling webhook", project_id, scene_num)
                result = call_webhook(
                    url, payload, timeout=300,
                    label=f"Storyboard scene {scene_num}",
                )

                image_url = result.get("image_url")
                if not image_url:
                    raise RuntimeError(f"Webhook returned no image_url: {result}")

            # Download into scene subfolder
            job["scene_statuses"][scene_key]["status"] = "downloading"
            _save_storyboard_json(project_id, job)

            ext = ".jpeg"
            if image_url.lower().endswith(".png"):
                ext = ".png"
            elif image_url.lower().endswith(".webp"):
                ext = ".webp"
            scene_dir = os.path.join(project_dir, str(scene_num))
            os.makedirs(scene_dir, exist_ok=True)
            _version_existing_image(scene_dir)
            dest = os.path.join(scene_dir, f"image{ext}")

            if _download_image(image_url, dest):
                local_path = f"/output/storyboard/{project_id}/{scene_num}/image{ext}"
                thumb_url = _generate_thumbnail(dest, project_id, scene_num)

                job["scene_statuses"][scene_key] = {
                    "status": "ready",
                    "image_url": image_url,
                    "local_path": local_path,
                    "thumb_path": thumb_url,
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
    job["completed_at"] = now_iso()
    job["ready"] = ready
    job["errors"] = errors
    job["total"] = total
    _save_storyboard_json(project_id, job)
    _jobs.set(project_id, job)
    logger.success("[{}] Storyboard complete — {}/{} ready, {} errors",
                   project_id, ready, total, errors)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@storyboard_bp.route("/api/storyboard/image-models")
def list_image_models():
    """Return the image-models.json config for frontend use."""
    from .wavespeed import _load_image_models
    return jsonify(_load_image_models())


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
        "created_at": now_iso(),
        "completed_at": None,
        "scene_statuses": {
            str(s["scene"]): {"status": "pending", "image_url": None, "local_path": None}
            for s in scenes
        },
    }
    _jobs.set(project_id, job)
    _save_storyboard_json(project_id, job)

    provider = getattr(data, "provider", "webhook") or "webhook"
    logger.info("[{}] Storyboard generate — provider={}, aspect={}, scenes={}",
                project_id, provider, data.aspect_ratio, len(scenes))

    if provider == "gemini":
        # Gemini provider: queue prompts via WebSocket to Chrome extension
        # Job is queued immediately — if extension isn't connected yet, it will
        # receive the job as soon as it connects (tab may still be loading).
        from studio.storyboard.gemini_ws import queue_image_job, is_extension_connected

        job_msg = {
            "type": "IMAGE_JOB",
            "projectId": project_id,
            "aspectRatio": data.aspect_ratio,
            "autoType": getattr(data, "auto_type", True),
            "scenes": [{"scene": s["scene"], "prompt": s["prompt"]} for s in scenes],
        }

        if is_extension_connected():
            queue_image_job(job_msg)
            logger.info("[{}] Gemini storyboard job sent — {} scenes", project_id, len(scenes))
        else:
            queue_image_job(job_msg)
            logger.info("[{}] Gemini storyboard job queued (waiting for extension) — {} scenes",
                        project_id, len(scenes))

        return jsonify({"status": "running", "project_id": project_id, "total": len(scenes), "provider": "gemini"}), 202

    # Default: webhook provider
    t = threading.Thread(
        target=_generate_storyboard,
        args=(project_id, scenes, data.aspect_ratio, data.webhook_url),
        kwargs={"style": data.style, "image_model": data.image_model},
        daemon=True,
    )
    t.start()

    logger.info("[{}] Storyboard generation started — {} scenes", project_id, len(scenes))
    return jsonify({"status": "running", "project_id": project_id, "total": len(scenes)}), 202


@storyboard_bp.route("/api/storyboard/status/<project_id>")
def status(project_id):
    """Poll storyboard generation status."""
    project_id = sanitize_project_id(project_id)

    # Always reload from disk (Gemini WS handler writes to disk, not in-memory)
    json_path = _storyboard_json_path(project_id)
    job = None
    if os.path.isfile(json_path):
        try:
            job = safe_json_read(json_path)
            _jobs.set(project_id, job)
        except Exception:
            pass

    if not job:
        job = _jobs.get(project_id)

    if not job:
        return jsonify({"error": "No storyboard job found for this project"}), 404

    scene_statuses = job.get("scene_statuses", {})
    # Use the stored total (set at creation time), exclude sentinel key "-1" from counts
    total = job.get("total", 0) or sum(1 for k in scene_statuses if k != "-1")
    ready = sum(1 for k, s in scene_statuses.items() if k != "-1" and s.get("status") in ("ready", "done"))
    errors = sum(1 for k, s in scene_statuses.items() if k != "-1" and s.get("status") == "error")

    done = ready >= total and total > 0

    return jsonify({
        "project_id": project_id,
        "status": "done" if done else job.get("status", "unknown"),
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
    image_exts = (".jpg", ".jpeg", ".png", ".webp")
    import re
    for entry in sorted(os.scandir(project_dir), key=lambda e: e.name):
        # New structure: {project_id}/{scene_num}/image.jpeg + image_v1.jpeg etc.
        if entry.is_dir() and entry.name.isdigit():
            scene_dir = entry.path
            scene_num = int(entry.name)
            thumb_file = _thumb_path(project_id, scene_num)
            thumb_url = (f"/api/thumbnails/{project_id}/storyboard/{entry.name}.jpg"
                         if os.path.isfile(thumb_file) else None)
            versions = []
            for f in sorted(os.scandir(scene_dir), key=lambda e: e.name):
                if not f.is_file() or f.name == "thumb.jpg":
                    continue
                if not f.name.lower().endswith(image_exts):
                    continue
                # Determine version: image.ext = current, image_v1.ext = version 1
                m = re.match(r"image_v(\d+)", f.name)
                version = int(m.group(1)) if m else None
                is_current = f.name.startswith("image.") or f.name.startswith("image.")
                versions.append({
                    "filename": f.name,
                    "path": f"/output/storyboard/{project_id}/{entry.name}/{f.name}",
                    "version": version,
                    "is_current": version is None and f.name.startswith("image."),
                    "size_bytes": f.stat().st_size,
                })
            # Sort: current last (newest), versions ascending
            versions.sort(key=lambda v: (v["version"] if v["version"] is not None else 9999))
            images.append({
                "scene": scene_num,
                "path": next((v["path"] for v in versions if v["is_current"]), versions[-1]["path"] if versions else None),
                "thumb_path": thumb_url,
                "versions": versions,
                "version_count": len(versions),
            })
        # Legacy flat structure: {project_id}/{scene_num}.jpg
        elif entry.is_file() and entry.name.lower().endswith(image_exts):
            base = os.path.splitext(entry.name)[0]
            images.append({
                "scene": int(base) if base.isdigit() else None,
                "path": f"/output/storyboard/{project_id}/{entry.name}",
                "thumb_path": None,
                "versions": [{"filename": entry.name, "path": f"/output/storyboard/{project_id}/{entry.name}", "version": None, "is_current": True, "size_bytes": entry.stat().st_size}],
                "version_count": 1,
            })

    images.sort(key=lambda x: x.get("scene") if x.get("scene") is not None else 0)
    return jsonify({"project_id": project_id, "images": images, "count": len(images)})


@storyboard_bp.route("/api/storyboard/images/<project_id>/<path:filename>")
def serve_image(project_id, filename):
    """Serve an individual storyboard image file."""
    project_id = sanitize_project_id(project_id)
    project_dir = _storyboard_dir(project_id)

    if not os.path.isfile(os.path.join(project_dir, filename)):
        return jsonify({"error": "Image not found"}), 404

    return send_from_directory(project_dir, filename)


@storyboard_bp.route("/api/storyboard/remove-watermarks/<project_id>", methods=["POST"])
def remove_watermarks(project_id):
    """Sweep all storyboard images for a project and remove any Gemini watermarks."""
    project_id = sanitize_project_id(project_id)
    from .gemini_ws import _sweep_watermarks
    import threading
    threading.Thread(target=_sweep_watermarks, args=(project_id,), daemon=True).start()
    return jsonify({"status": "started", "project_id": project_id}), 202


@storyboard_bp.route("/api/storyboard/grab", methods=["POST"])
@validate_json(StoryboardGrabOneRequest)
def grab_one(data: StoryboardGrabOneRequest):
    """Grab a single scene's storyboard image — sends to n8n and downloads result.

    Creates or updates the job for this project, generating only the requested scene.
    """
    project_id = sanitize_project_id(data.project_id)
    scene_key = str(data.scene)
    webhook_url = data.webhook_url or N8N_STORYBOARD_WEBHOOK_URL

    # Load or create job
    job = _jobs.get(project_id)
    if not job:
        json_path = _storyboard_json_path(project_id)
        if os.path.isfile(json_path):
            try:
                job = safe_json_read(json_path)
                _jobs.set(project_id, job)
            except Exception:
                pass
    if not job:
        job = {
            "project_id": project_id,
            "status": "running",
            "total": 0,
            "ready": 0,
            "errors": 0,
            "aspect_ratio": data.aspect_ratio,
            "created_at": now_iso(),
            "completed_at": None,
            "scene_statuses": {},
        }

    # Mark this scene as generating
    job["status"] = "running"
    job["scene_statuses"][scene_key] = {"status": "generating", "image_url": None, "local_path": None}
    _jobs.set(project_id, job)
    _save_storyboard_json(project_id, job)

    def _grab_single(pid, sk, prompt, ar, url):
        j = _jobs.get(pid)
        if not j:
            return
        project_dir = _storyboard_dir(pid)
        os.makedirs(project_dir, exist_ok=True)

        try:
            logger.info("[{}] Storyboard grab scene {} — calling webhook", pid, sk)
            result = call_webhook(
                url,
                {"image_prompt": prompt, "aspect_ratio": ar,
                 "wavespeed_api_key": WAVESPEED_API_KEY,
                 "project_id": pid, "scene": int(sk)},
                timeout=300,
                label=f"Storyboard grab scene {sk}",
            )
            image_url = result.get("image_url")
            if not image_url:
                raise RuntimeError(f"Webhook returned no image_url: {result}")

            j["scene_statuses"][sk]["status"] = "downloading"
            _save_storyboard_json(pid, j)

            ext = ".jpeg"
            if image_url.lower().endswith(".png"):
                ext = ".png"
            elif image_url.lower().endswith(".webp"):
                ext = ".webp"
            scene_dir = os.path.join(project_dir, sk)
            os.makedirs(scene_dir, exist_ok=True)
            _version_existing_image(scene_dir)
            dest = os.path.join(scene_dir, f"image{ext}")

            if _download_image(image_url, dest):
                local_path = f"/output/storyboard/{pid}/{sk}/image{ext}"
                thumb_url = _generate_thumbnail(dest, pid, int(sk))

                j["scene_statuses"][sk] = {
                    "status": "ready",
                    "image_url": image_url,
                    "local_path": local_path,
                    "thumb_path": thumb_url,
                }
                logger.success("[{}] Storyboard grab scene {} ready", pid, sk)
            else:
                j["scene_statuses"][sk] = {
                    "status": "error",
                    "image_url": image_url,
                    "local_path": None,
                    "error": "Download failed after retries",
                }
        except Exception as e:
            logger.error("[{}] Storyboard grab scene {} failed: {}", pid, sk, e)
            j["scene_statuses"][sk] = {
                "status": "error",
                "image_url": None,
                "local_path": None,
                "error": str(e),
            }

        # Update totals
        statuses = j["scene_statuses"]
        j["total"] = len(statuses)
        j["ready"] = sum(1 for s in statuses.values() if s.get("status") == "ready")
        j["errors"] = sum(1 for s in statuses.values() if s.get("status") == "error")
        all_done = all(s["status"] in ("ready", "error") for s in statuses.values())
        if all_done:
            j["status"] = "done"
            j["completed_at"] = now_iso()
        _save_storyboard_json(pid, j)
        _jobs.set(pid, j)

    provider = getattr(data, "provider", "webhook") or "webhook"

    if provider == "gemini":
        from studio.storyboard.gemini_ws import queue_image_job

        queue_image_job({
            "type": "IMAGE_JOB",
            "projectId": project_id,
            "aspectRatio": data.aspect_ratio,
            "autoType": getattr(data, "auto_type", True),
            "scenes": [{"scene": data.scene, "prompt": data.prompt}],
        })

        logger.info("[{}] Gemini grab scene {} queued", project_id, scene_key)
        return jsonify({"status": "generating", "project_id": project_id, "scene": data.scene, "provider": "gemini"}), 202

    # Default: webhook
    threading.Thread(
        target=_grab_single,
        args=(project_id, scene_key, data.prompt, data.aspect_ratio, webhook_url),
        daemon=True,
    ).start()

    logger.info("[{}] Storyboard grab started — scene {}", project_id, scene_key)
    return jsonify({"status": "generating", "project_id": project_id, "scene": data.scene}), 202


@storyboard_bp.route("/api/storyboard/webhook-url")
def get_webhook_url():
    """Return the configured storyboard webhook URL (image-generator)."""
    return jsonify({"url": N8N_STORYBOARD_WEBHOOK_URL})


@storyboard_bp.route("/output/storyboard/<path:filename>")
def serve_output(filename):
    """Serve storyboard files via /output/storyboard/ path (consistency with other modules)."""
    return send_from_directory(STORYBOARD_DIR, filename)
