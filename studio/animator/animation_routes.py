"""Animator Module — Grabber-based Video/Image Generation & Management Routes"""

import json
import os
import platform
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory
from loguru import logger

from config import ANIMATOR_DIR, PROJECTS_DIR, SCENES_DIR, THUMBNAILS_DIR, KIE_AI_MODEL, BIN_DIR
from studio.ffmpeg_utils import find_ffmpeg
from studio.io_utils import safe_json_write, now_iso, JobStore
from studio.security import is_loopback_remote, sanitize_project_id
from studio.validation import validate_json
from .schemas import GrabberStartRequest
from .organizer import organize_grabber_assets, save_base64_assets, reconcile_project
from .providers.kie_ai import generate_image as kie_ai_generate
from studio.shared.providers_common import settings_manager

VIDEO_EXTS = (".mp4", ".webm", ".mov")


def _job_requires_video_assets(job) -> bool:
    """Return True when the grabber job is expected to produce videos only."""
    if not isinstance(job, dict):
        return False
    payload = job.get("payload", {}) or {}
    return str(payload.get("grok_mode", "")).lower() == "video"


def _looks_like_video_asset(value: str) -> bool:
    """Best-effort check for video URLs / filenames coming back from Automa."""
    clean = str(value or "").split("?", 1)[0].lower()
    return clean.endswith(VIDEO_EXTS) or "/generated_video" in clean


def _filter_video_urls(urls):
    """Keep only video asset URLs."""
    return [url for url in (urls or []) if _looks_like_video_asset(url)]


def _filter_video_images(images):
    """Keep only base64 upload entries that point to video assets."""
    filtered = []
    for image in images or []:
        ext = str(image.get("ext", "")).lower()
        source_url = image.get("source_url", "")
        filename = image.get("filename", "")
        if ext in VIDEO_EXTS or _looks_like_video_asset(source_url) or _looks_like_video_asset(filename):
            filtered.append(image)
    return filtered


def _video_thumbnail(video_path):
    """Extract a thumbnail jpg from a video file. Returns thumbnail path or None."""
    thumb_path = video_path.rsplit(".", 1)[0] + "_thumb.jpg"
    if os.path.isfile(thumb_path):
        return thumb_path
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", video_path, "-map", "0:v:0",
             "-vframes", "1", "-ss", "0.1", "-q:v", "3", thumb_path],
            capture_output=True, timeout=10,
        )
        if os.path.isfile(thumb_path):
            return thumb_path
    except Exception:
        pass
    return None

animation_bp = Blueprint("animation", __name__)

# In-memory grabber job tracking
grabber_jobs = JobStore()


def _get_job(project_id):
    """Get a grabber job by project ID."""
    return grabber_jobs.get(project_id)


def _set_job(project_id, job):
    """Set a grabber job by project ID."""
    grabber_jobs.set(project_id, job)


def _save_job(job):
    """Persist grabber job state to disk."""
    try:
        job["updated_at"] = now_iso()
        safe_json_write(os.path.join(ANIMATOR_DIR, job["project_id"], "grabber_job.json"), job, indent=2)
    except Exception as e:
        logger.error("Failed to persist job {}: {}", job.get("grabber_id", "?"), e)


def _parse_iso_dt(value):
    """Best-effort ISO timestamp parser."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _job_elapsed_seconds(job, *, include_running=False):
    """Return elapsed wall-clock seconds for a grabber job."""
    try:
        existing = float(job.get("generation_time", 0) or 0)
        if existing > 0:
            return round(existing, 3)
    except (TypeError, ValueError):
        pass

    start_dt = _parse_iso_dt(job.get("created_at"))
    if not start_dt:
        return 0

    end_dt = _parse_iso_dt(job.get("completed_at"))
    if end_dt is None and include_running:
        end_dt = datetime.now().astimezone()
    if end_dt is None:
        end_dt = _parse_iso_dt(job.get("updated_at"))
    if end_dt is None:
        return 0

    # Normalize both to naive datetimes to avoid offset-aware vs offset-naive errors
    if start_dt.tzinfo is not None:
        start_dt = start_dt.replace(tzinfo=None)
    if end_dt.tzinfo is not None:
        end_dt = end_dt.replace(tzinfo=None)

    return round(max((end_dt - start_dt).total_seconds(), 0.0), 3)


def _clear_job_completion(job):
    """Clear stale completion fields before a new run or retry begins."""
    job.pop("completed_at", None)
    job.pop("generation_time", None)


def _mark_job_done(job):
    """Stamp completion fields for a finished grabber job."""
    job["status"] = "done"
    job["completed_at"] = now_iso()
    job["generation_time"] = _job_elapsed_seconds(job)


def _load_jobs_from_disk():
    """Load existing grabber jobs from disk on startup."""
    if not os.path.isdir(ANIMATOR_DIR):
        return
    for entry in os.scandir(ANIMATOR_DIR):
        if not entry.is_dir():
            continue
        pid = entry.name
        # Reconcile disk → JSON first (fixes missing scenes in metadata/job)
        reconcile_project(ANIMATOR_DIR, pid)
        # Now load the (possibly updated) job
        job_path = os.path.join(entry.path, "grabber_job.json")
        if not os.path.isfile(job_path):
            continue
        try:
            with open(job_path, "r", encoding="utf-8") as f:
                job = json.load(f)
            grabber_jobs.set(pid, job)
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.warning("Skipped loading job from {}: {}", pid, e)


# Load existing jobs on module import
_load_jobs_from_disk()


# ---------------------------------------------------------------------------
# Grabber Routes
# ---------------------------------------------------------------------------

@animation_bp.route("/api/animator/grabber/start", methods=["POST"])
@validate_json(GrabberStartRequest)
def grabber_start(data: GrabberStartRequest):
    """Initialize a grabber job — prepares prompts for Automa to consume."""
    # Resolve provider: override → settings → default
    from studio.animator.providers import registry as anim_registry
    from studio.shared.providers_common import settings_manager
    
    provider_id = data.provider_id
    
    provider = anim_registry.get(provider_id)
    if provider is None:
        # Fall back to grok_automa
        provider_id = "grok_automa"
        provider = anim_registry.get(provider_id)
        if provider is None:
            return jsonify({"error": f"Provider '{provider_id}' not found"}), 400
    
    logger.info("grabber_start request: {} scenes, provider={}", len(data.scenes), provider_id)

    project_id = sanitize_project_id(data.project_id)
    if not project_id:
        return jsonify({"error": "Invalid project id"}), 400
    
    # Get provider settings
    provider_settings = settings_manager.get_provider_settings("animator", provider_id)
    arguments = data.arguments
    scenes = [s.model_dump() for s in data.scenes]
    consistency = data.consistency

    grabber_id = f"grab_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{project_id}"

    # Build consistency prefix for visual consistency across all scenes
    consistency_prefix = ""
    if consistency:
        parts = []
        if consistency.get("character"):
            parts.append(consistency["character"])
        if consistency.get("setting"):
            parts.append(consistency["setting"])
        if consistency.get("mood"):
            parts.append(consistency["mood"])
        if parts:
            consistency_prefix = ", ".join(parts) + ". "
            logger.info("Applying consistency prefix to {} scene prompts", len(scenes))

    # Build Automa-compatible payload (prepend consistency prefix to each prompt)
    # Include storyboard images as base64 for display in Automa/extension
    import base64 as b64_mod
    from config import STORYBOARD_DIR
    image_exts = (".jpg", ".jpeg", ".png", ".webp")
    scene_list = []
    for s in scenes:
        if not s.get("prompt"):
            continue
        entry = {"prompt": consistency_prefix + s["prompt"], "scene": s["scene"]}
        # Read storyboard image and encode as base64
        scene_img_dir = os.path.join(STORYBOARD_DIR, project_id, str(s["scene"]))
        if os.path.isdir(scene_img_dir):
            for fname in os.listdir(scene_img_dir):
                if fname.startswith("image") and fname.lower().endswith(image_exts):
                    img_path = os.path.join(scene_img_dir, fname)
                    try:
                        with open(img_path, "rb") as img_f:
                            raw = img_f.read()
                        ext = os.path.splitext(fname)[1].lstrip(".")
                        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
                        entry["image"] = f"data:image/{mime};base64,{b64_mod.b64encode(raw).decode()}"
                    except Exception:
                        pass
                    break
        scene_list.append(entry)
    automa_payload = {
        "projectId": project_id,
        "arguments": arguments if provider == "midjourney" else "",
        "aspect_ratio": data.aspect_ratio or "9:16",
        "scenes": scene_list,
    }

    # Pass Grok-specific options for Automa to configure the UI
    if provider_id == "grok_automa":
        request_data = request.get_json(silent=True) or {}
        automa_payload["grok_mode"] = request_data.get("grok_mode", "video")
        automa_payload["grok_quality"] = request_data.get("grok_quality", "480p")
        automa_payload["grok_duration"] = request_data.get("grok_duration", "6s")
        automa_payload["auto_type"] = request_data.get("auto_type", False)

    # Per-scene status tracking — preserve existing statuses for scenes not
    # being resent so that already-completed scenes keep their "ready" state.
    prev_job = grabber_jobs.get(project_id)
    scene_statuses = dict(prev_job["scene_statuses"]) if prev_job else {}
    for s in automa_payload["scenes"]:
        scene_statuses[str(s["scene"])] = {
            "status": "pending",
            "urls": [],
            "local_files": [],
        }

    job = {
        "grabber_id": grabber_id,
        "project_id": project_id,
        "provider": provider_id,  # Use new provider ID
        "arguments": arguments,
        "payload": automa_payload,
        "scene_statuses": scene_statuses,
        "status": "waiting",  # waiting | grabbing | generating | downloading | done | error
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

    # Store Kie AI generation options for the background thread
    if provider_id == "kie_ai":
        job["_kie_ai_options"] = {
            "model": data.model or KIE_AI_MODEL,
            "aspect_ratio": data.aspect_ratio or "9:16",
            "resolution": data.resolution or "1",
            "output_format": data.output_format or "jpg",
        }
        # Merge provider settings
        job["_kie_ai_options"].update(provider_settings)

    grabber_jobs.set(project_id, job)
    _save_job(job)

    logger.info("Grabber job created: {} ({} scenes, provider={})", grabber_id, len(automa_payload["scenes"]), provider)

    # Push to connected WebSocket clients (Automa / STS extension)
    # Payload already contains base64 images from the scene_list build above
    if provider_id == "grok_automa":
        try:
            from .routes import queue_grabber_start
            queue_grabber_start({
                "type": "GRABBER_START",
                "projectId": project_id,
                "scenes": automa_payload["scenes"],
                "aspectRatio": automa_payload.get("aspect_ratio", "9:16"),
                "grokMode": automa_payload.get("grok_mode", "video"),
                "grokDuration": automa_payload.get("grok_duration", "6s"),
                "autoType": automa_payload.get("auto_type", False),
            })
            imgs = sum(1 for s in automa_payload["scenes"] if s.get("image"))
            logger.info("Grabber data queued/pushed for {} ({} scenes, {} with images)",
                        project_id, len(automa_payload["scenes"]), imgs)
        except Exception as e:
            logger.warning("WebSocket push failed: {}", e)

    # Kie AI: fully server-side — spawn background thread to generate + download
    if provider_id == "kie_ai":
        job["status"] = "generating"
        _save_job(job)
        threading.Thread(
            target=_kie_ai_generate_all,
            args=(project_id, job),
            daemon=True,
        ).start()

    return jsonify({
        "grabber_id": grabber_id,
        "project_id": project_id,
        "scene_count": len(automa_payload["scenes"]),
        "provider": provider_id,
    })


def _kie_ai_generate_all(project_id, job):
    """Background thread: generate images via Kie AI for all scenes sequentially."""
    scenes = job["payload"]["scenes"]
    request_data = job.get("_kie_ai_options", {})
    model = request_data.get("model", "google/nano-banana")
    aspect_ratio = request_data.get("aspect_ratio", "9:16")
    resolution = request_data.get("resolution", "1")
    output_format = request_data.get("output_format", "jpg")

    logger.info("Kie AI thread started: {} scenes, model={}, ar={}, res={}, fmt={}",
                len(scenes), model, aspect_ratio, resolution, output_format)

    for scene_entry in scenes:
        scene_num = str(scene_entry["scene"])
        prompt = scene_entry["prompt"]
        logger.info("Kie AI scene {}: generating (prompt: {})", scene_num, prompt[:80])

        if scene_num in job["scene_statuses"]:
            job["scene_statuses"][scene_num]["status"] = "generating"
        _save_job(job)

        try:
            result = kie_ai_generate(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                output_format=output_format,
                model=model,
            )
            image_urls = result.get("all_urls", [result["url"]])
            logger.info("Kie AI scene {} generated: {} URL(s)", scene_num, len(image_urls))

            # Download to disk
            if scene_num in job["scene_statuses"]:
                job["scene_statuses"][scene_num]["status"] = "downloading"
                job["scene_statuses"][scene_num]["urls"] = image_urls
            _save_job(job)

            local_files = organize_grabber_assets(
                project_id=project_id,
                scene_num=scene_num,
                urls=image_urls,
                assets_dir=ANIMATOR_DIR,
            )
            if scene_num in job["scene_statuses"]:
                job["scene_statuses"][scene_num]["status"] = "ready"
                job["scene_statuses"][scene_num]["local_files"] = local_files
            logger.success("Kie AI scene {} ready: {} files", scene_num, len(local_files))

        except Exception as e:
            logger.error("Kie AI scene {} failed: {}", scene_num, e)
            if scene_num in job["scene_statuses"]:
                job["scene_statuses"][scene_num]["status"] = "error"

        _save_job(job)

    all_done = all(
        s["status"] in ("ready", "error")
        for s in job["scene_statuses"].values()
    )
    if all_done:
        _mark_job_done(job)
        _save_job(job)
        logger.success("Kie AI generation complete for {}", project_id)


@animation_bp.route("/api/animator/grabber/pending")
def grabber_pending():
    """Return the most recent pending grabber payload for Automa to consume."""
    if not is_loopback_remote(request.remote_addr):
        return jsonify({"error": "Forbidden"}), 403

    latest = None
    jobs_snapshot = grabber_jobs.values()
    for job in jobs_snapshot:
        if job["status"] == "waiting":
            if not latest or job["created_at"] > latest["created_at"]:
                latest = job

    if not latest:
        return jsonify({"error": "No pending grabber jobs"}), 404

    latest["status"] = "grabbing"
    _save_job(latest)
    return jsonify(latest["payload"])


@animation_bp.route("/api/animator/grabber/results", methods=["POST"])
def grabber_results():
    """Receive scraped image URLs from Automa and download them."""
    if not is_loopback_remote(request.remote_addr):
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # data format: [{ projectId, scenes: [{ scene, url: [...] }] }]
    results = data if isinstance(data, list) else [data]

    for project in results:
        project_id = sanitize_project_id(project.get("projectId", ""))
        if not project_id:
            continue
        job = grabber_jobs.get(project_id)
        if not job:
            logger.warning("Grabber results for unknown project: {}", project_id)
            continue

        _clear_job_completion(job)
        job["status"] = "downloading"
        scenes = project.get("scenes", [])
        logger.info("Received results for {}: {} scenes", project_id, len(scenes))

        # Download images in a background thread
        def _download_all(pid, job_ref, scene_list):
            for scene_entry in scene_list:
                scene_num = str(scene_entry.get("scene", ""))
                raw_urls = scene_entry.get("url", []) or scene_entry.get("urls", [])
                urls = _filter_video_urls(raw_urls) if _job_requires_video_assets(job_ref) else raw_urls
                if not urls:
                    if _job_requires_video_assets(job_ref) and raw_urls:
                        logger.error("Scene {} rejected non-video asset URLs for video job: {}", scene_num, raw_urls)
                        if scene_num in job_ref["scene_statuses"]:
                            job_ref["scene_statuses"][scene_num]["status"] = "error"
                        _save_job(job_ref)
                    else:
                        logger.warning("Scene {} has no URLs, skipping", scene_num)
                    continue

                if len(urls) != len(raw_urls):
                    logger.warning("Scene {} filtered {} non-video URL(s) from grabber payload", scene_num, len(raw_urls) - len(urls))

                if scene_num in job_ref["scene_statuses"]:
                    job_ref["scene_statuses"][scene_num]["status"] = "downloading"
                    job_ref["scene_statuses"][scene_num]["urls"] = urls

                _save_job(job_ref)
                logger.info("Downloading scene {} ({} URLs)...", scene_num, len(urls))

                try:
                    local_files = organize_grabber_assets(
                        project_id=pid,
                        scene_num=scene_num,
                        urls=urls,
                        assets_dir=ANIMATOR_DIR,
                    )
                    if scene_num in job_ref["scene_statuses"]:
                        job_ref["scene_statuses"][scene_num]["status"] = "ready"
                        job_ref["scene_statuses"][scene_num]["local_files"] = local_files
                    logger.success("Scene {} ready: {} files downloaded", scene_num, len(local_files))
                except Exception as e:
                    logger.error("Download failed for scene {}: {}", scene_num, e)
                    if scene_num in job_ref["scene_statuses"]:
                        job_ref["scene_statuses"][scene_num]["status"] = "error"

                _save_job(job_ref)

            # Check if all scenes are done
            all_done = all(
                s["status"] in ("ready", "error")
                for s in job_ref["scene_statuses"].values()
            )
            if all_done:
                _mark_job_done(job_ref)
                _save_job(job_ref)
                logger.success("Grabber job complete for {}", pid)

        threading.Thread(
            target=_download_all,
            args=(project_id, job, scenes),
            daemon=True,
        ).start()

    return jsonify({"status": "downloading", "projects": len(results)})


@animation_bp.route("/api/animator/grabber/upload", methods=["POST"])
def grabber_upload():
    """Receive base64 image data from Automa (for CDN URLs that require auth).

    Expected format:
    {
      "projectId": "pm_XXX",
      "scenes": [
        {
          "scene": 0,
          "images": [
            {"data": "base64...", "source_url": "https://cdn...", "ext": ".png"},
            ...
          ]
        }
      ]
    }
    """
    if not is_loopback_remote(request.remote_addr):
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    project_id = sanitize_project_id(data.get("projectId", ""))
    scenes = data.get("scenes", [])
    if not project_id or not scenes:
        return jsonify({"error": "Missing projectId or scenes"}), 400

    job = grabber_jobs.get(project_id)
    if job:
        _clear_job_completion(job)
        job["status"] = "downloading"

    logger.info("Upload received for {}: {} scenes", project_id, len(scenes))

    def _save_all(pid, job_ref, scene_list):
        for scene_entry in scene_list:
            scene_num = str(scene_entry.get("scene", ""))
            raw_images = scene_entry.get("images", [])
            images = _filter_video_images(raw_images) if _job_requires_video_assets(job_ref) else raw_images
            if not images:
                if _job_requires_video_assets(job_ref) and raw_images:
                    logger.error("Scene {} rejected non-video upload(s) for video job", scene_num)
                    if job_ref and scene_num in job_ref["scene_statuses"]:
                        job_ref["scene_statuses"][scene_num]["status"] = "error"
                        _save_job(job_ref)
                continue

            if len(images) != len(raw_images):
                logger.warning("Scene {} filtered {} non-video upload(s) from Automa", scene_num, len(raw_images) - len(images))

            if job_ref and scene_num in job_ref["scene_statuses"]:
                job_ref["scene_statuses"][scene_num]["status"] = "downloading"
                _save_job(job_ref)

            logger.info("Saving scene {} ({} images)...", scene_num, len(images))
            try:
                local_files = save_base64_assets(
                    project_id=pid,
                    scene_num=scene_num,
                    images=images,
                    assets_dir=ANIMATOR_DIR,
                )
                if job_ref and scene_num in job_ref["scene_statuses"]:
                    job_ref["scene_statuses"][scene_num]["status"] = "ready"
                    job_ref["scene_statuses"][scene_num]["local_files"] = local_files
                    job_ref["scene_statuses"][scene_num]["urls"] = [
                        img.get("source_url", "") for img in images
                    ]
                logger.success("Scene {} saved: {} files", scene_num, len(local_files))
            except Exception as e:
                logger.error("Save failed for scene {}: {}", scene_num, e)
                if job_ref and scene_num in job_ref["scene_statuses"]:
                    job_ref["scene_statuses"][scene_num]["status"] = "error"

            if job_ref:
                _save_job(job_ref)

        if job_ref:
            all_done = all(
                s["status"] in ("ready", "error")
                for s in job_ref["scene_statuses"].values()
            )
            if all_done:
                _mark_job_done(job_ref)
                _save_job(job_ref)
                logger.success("Upload job complete for {}", pid)

    threading.Thread(
        target=_save_all,
        args=(project_id, job, scenes),
        daemon=True,
    ).start()

    return jsonify({"status": "saving", "scenes": len(scenes)})


@animation_bp.route("/api/animator/grabber/status/<project_id>")
def grabber_status(project_id):
    """Poll grabber job status — frontend calls this every 5s."""
    project_id = sanitize_project_id(project_id)
    if not project_id:
        return jsonify({"error": "Invalid project id"}), 400
    job = grabber_jobs.get(project_id)
    if not job:
        return jsonify({"error": "No grabber job found"}), 404

    return jsonify({
        "grabber_id": job["grabber_id"],
        "project_id": project_id,
        "status": job["status"],
        "generation_time": _job_elapsed_seconds(
            job, include_running=job.get("status") not in ("done", "error")
        ),
        "scene_statuses": job["scene_statuses"],
    })


# ---------------------------------------------------------------------------
# Re-download — retry downloading assets for scenes that failed or are pending
# ---------------------------------------------------------------------------

@animation_bp.route("/api/animator/redownload/<project_id>", methods=["POST"])
def redownload_assets(project_id):
    """Re-attempt downloads for scenes with URLs but no local files."""
    project_id = sanitize_project_id(project_id)
    if not project_id:
        return jsonify({"error": "Invalid project id"}), 400
    job = grabber_jobs.get(project_id)
    if not job:
        return jsonify({"error": "No grabber job found"}), 404

    # Also check metadata for URLs
    meta_path = os.path.join(ANIMATOR_DIR, project_id, "metadata.json")
    meta = {}
    if os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

    scenes_to_retry = []
    for scene_num, ss in job["scene_statuses"].items():
        has_local = ss.get("local_files") and len(ss["local_files"]) > 0
        # Check actual files on disk
        scene_dir = os.path.join(ANIMATOR_DIR, project_id, str(scene_num))
        has_files = os.path.isdir(scene_dir) and any(
            f.is_file() for f in Path(scene_dir).iterdir()
        )
        if has_local and has_files:
            continue  # already downloaded

        # Get URLs from job or metadata
        urls = ss.get("urls", [])
        if not urls:
            scene_meta = meta.get("scenes", {}).get(str(scene_num), {})
            urls = scene_meta.get("source_urls", [])
        if urls:
            scenes_to_retry.append({"scene": scene_num, "url": urls})

    if not scenes_to_retry:
        return jsonify({"status": "nothing_to_retry", "message": "All scenes already downloaded"})

    _clear_job_completion(job)
    job["status"] = "downloading"
    _save_job(job)

    def _retry_downloads(pid, job_ref, scene_list):
        for entry in scene_list:
            sn = str(entry["scene"])
            urls = entry["url"]
            if sn in job_ref["scene_statuses"]:
                job_ref["scene_statuses"][sn]["status"] = "downloading"
            _save_job(job_ref)
            logger.info("Re-downloading scene {} ({} URLs)", sn, len(urls))

            try:
                local_files = organize_grabber_assets(
                    project_id=pid, scene_num=sn,
                    urls=urls, assets_dir=ANIMATOR_DIR,
                )
                if sn in job_ref["scene_statuses"]:
                    job_ref["scene_statuses"][sn]["status"] = "ready"
                    job_ref["scene_statuses"][sn]["local_files"] = local_files
                logger.success("Re-download scene {} done: {} files", sn, len(local_files))
            except Exception as e:
                logger.error("Re-download failed for scene {}: {}", sn, e)
                if sn in job_ref["scene_statuses"]:
                    job_ref["scene_statuses"][sn]["status"] = "error"
            _save_job(job_ref)

        all_done = all(
            s["status"] in ("ready", "error")
            for s in job_ref["scene_statuses"].values()
        )
        if all_done:
            _mark_job_done(job_ref)
            _save_job(job_ref)

    threading.Thread(
        target=_retry_downloads,
        args=(project_id, job, scenes_to_retry),
        daemon=True,
    ).start()

    return jsonify({
        "status": "retrying",
        "scenes_retrying": len(scenes_to_retry),
    })


# ---------------------------------------------------------------------------
# History — list all asset projects
# ---------------------------------------------------------------------------

@animation_bp.route("/api/animator/history")
def assets_history():
    """List all asset projects with metadata summary."""
    projects = []
    if not os.path.isdir(ANIMATOR_DIR):
        return jsonify(projects)

    try:
        entries = sorted(os.scandir(ANIMATOR_DIR), key=lambda e: e.stat().st_mtime, reverse=True)
    except OSError:
        return jsonify(projects)

    for entry in entries:
        if not entry.is_dir():
            continue

        project_id = entry.name
        project_info = {
            "project_id": project_id,
            "timestamp": datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
        }

        # Read grabber job for status info
        job_path = os.path.join(entry.path, "grabber_job.json")
        if os.path.isfile(job_path):
            try:
                with open(job_path, "r", encoding="utf-8") as f:
                    job = json.load(f)
                project_info["grabber_id"] = job.get("grabber_id", "")
                project_info["provider"] = job.get("provider", "")
                project_info["status"] = job.get("status", "unknown")
                project_info["created_at"] = job.get("created_at", "")
                project_info["updated_at"] = job.get("updated_at", "")
                project_info["completed_at"] = job.get("completed_at", "")
                project_info["generation_time"] = _job_elapsed_seconds(
                    job, include_running=job.get("status") not in ("done", "error")
                )
                project_info["scene_count"] = len(job.get("scene_statuses", {}))
                # Count ready/pending/error
                statuses = [s["status"] for s in job.get("scene_statuses", {}).values()]
                project_info["ready_count"] = statuses.count("ready")
                project_info["error_count"] = statuses.count("error")
                project_info["pending_count"] = statuses.count("pending")
            except (json.JSONDecodeError, OSError, TypeError, ValueError, KeyError):
                pass

        # Read metadata for file counts
        meta_path = os.path.join(entry.path, "metadata.json")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                total_files = sum(
                    len(s.get("local_files", []))
                    for s in meta.get("scenes", {}).values()
                )
                project_info["total_files"] = total_files
            except (json.JSONDecodeError, OSError):
                pass

        # Count actual files on disk
        total_disk_files = 0
        try:
            for sub in Path(entry.path).iterdir():
                if sub.is_dir() and sub.name not in (".", ".."):
                    try:
                        total_disk_files += sum(1 for f in sub.iterdir() if f.is_file())
                    except OSError:
                        pass
        except OSError:
            pass
        project_info["disk_files"] = total_disk_files

        # Get style from scenes.json
        scenes_json = os.path.join(SCENES_DIR, project_id, "scenes.json")
        if os.path.isfile(scenes_json):
            try:
                with open(scenes_json, "r", encoding="utf-8") as f:
                    sdata = json.load(f)
                project_info["style"] = sdata.get("style", "")
            except Exception:
                pass

        # Get a preview image — prefer generated thumbnails, fall back to assets
        project_info["preview"] = None

        # 1) Check the thumbnails system first (editor cover, then assets/0)
        thumb_base = os.path.join(THUMBNAILS_DIR, project_id)
        editor_cover = os.path.join(thumb_base, "editor", "cover.jpg")
        assets_thumb_0 = os.path.join(thumb_base, "assets", "0.jpg")
        if os.path.isfile(editor_cover):
            project_info["preview"] = f"/api/thumbnails/{project_id}/editor/cover.jpg"
        elif os.path.isfile(assets_thumb_0):
            project_info["preview"] = f"/api/thumbnails/{project_id}/assets/0.jpg"
        else:
            # 2) Fall back to scanning asset scene directories
            try:
                scene_dirs = sorted(os.listdir(entry.path))
            except OSError:
                scene_dirs = []
            for scene_num in scene_dirs:
                scene_path = os.path.join(entry.path, scene_num)
                if not os.path.isdir(scene_path) or scene_num in (".", ".."):
                    continue
                try:
                    scene_files = sorted(os.listdir(scene_path))
                except OSError:
                    continue
                for fname in scene_files:
                    fpath = os.path.join(scene_path, fname)
                    if not os.path.isfile(fpath):
                        continue
                    lower = fname.lower()
                    if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                        project_info["preview"] = f"/output/animator/{project_id}/{scene_num}/{fname}"
                        break
                    if lower.endswith(VIDEO_EXTS):
                        thumb = _video_thumbnail(fpath)
                        if thumb:
                            thumb_name = os.path.basename(thumb)
                            project_info["preview"] = f"/output/animator/{project_id}/{scene_num}/{thumb_name}"
                        # Don't set video URL as preview — <img> can't render it
                        break
                if project_info["preview"]:
                    break

        # Check if a build (initial.json) already exists for this project
        proj_dir = os.path.join(PROJECTS_DIR, project_id)
        project_info["has_build"] = os.path.isfile(os.path.join(proj_dir, "initial.json"))

        projects.append(project_info)

    return jsonify(projects)


@animation_bp.route("/api/animator/reconcile/<project_id>", methods=["POST"])
def reconcile_assets(project_id):
    """Force reconcile disk files with metadata.json + grabber_job.json."""
    project_id = sanitize_project_id(project_id)
    if not project_id:
        return jsonify({"error": "Invalid project id"}), 400
    project_dir = os.path.join(ANIMATOR_DIR, project_id)
    if not os.path.isdir(project_dir):
        return jsonify({"error": "Project not found"}), 404
    updated = reconcile_project(ANIMATOR_DIR, project_id)
    # Reload job into memory if it was updated
    if updated > 0:
        job_path = os.path.join(project_dir, "grabber_job.json")
        if os.path.isfile(job_path):
            with open(job_path, "r", encoding="utf-8") as f:
                grabber_jobs.set(project_id, json.load(f))
    return jsonify({"updated": updated})


@animation_bp.route("/api/animator/project/<project_id>")
def get_asset_project(project_id):
    """Get full asset project details — all scenes with local files."""
    project_id = sanitize_project_id(project_id)
    if not project_id:
        return jsonify({"error": "Invalid project id"}), 400
    project_dir = os.path.join(ANIMATOR_DIR, project_id)
    if not os.path.isdir(project_dir):
        return jsonify({"error": "Project not found"}), 404

    # Auto-reconcile: sync disk → JSON before returning
    reconcile_project(ANIMATOR_DIR, project_id)

    result = {
        "project_id": project_id,
        "scenes": {},
    }

    # Load metadata
    meta_path = os.path.join(project_dir, "metadata.json")
    if os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        result["scenes"] = meta.get("scenes", {})

    # Load job info
    job_path = os.path.join(project_dir, "grabber_job.json")
    if os.path.isfile(job_path):
        with open(job_path, "r", encoding="utf-8") as f:
            job = json.load(f)
        result["grabber_id"] = job.get("grabber_id", "")
        result["provider"] = job.get("provider", "")
        result["status"] = job.get("status", "unknown")
        result["created_at"] = job.get("created_at", "")
        result["updated_at"] = job.get("updated_at", "")
        result["completed_at"] = job.get("completed_at", "")
        result["generation_time"] = _job_elapsed_seconds(
            job, include_running=job.get("status") not in ("done", "error")
        )
        result["scene_statuses"] = job.get("scene_statuses", {})
        result["prompts"] = {
            str(s["scene"]): s["prompt"]
            for s in job.get("payload", {}).get("scenes", [])
        }

    # Scan actual files on disk per scene
    for scene_num_dir in sorted(os.listdir(project_dir)):
        scene_path = os.path.join(project_dir, scene_num_dir)
        if not os.path.isdir(scene_path):
            continue
        try:
            int(scene_num_dir)  # only numeric subdirs are scenes
        except ValueError:
            continue

        files_on_disk = []
        for fname in sorted(os.listdir(scene_path)):
            fpath = os.path.join(scene_path, fname)
            if os.path.isfile(fpath):
                files_on_disk.append({
                    "url": f"/output/animator/{project_id}/{scene_num_dir}/{fname}",
                    "filename": fname,
                    "size": os.path.getsize(fpath),
                })

        if scene_num_dir not in result["scenes"]:
            result["scenes"][scene_num_dir] = {}
        result["scenes"][scene_num_dir]["files_on_disk"] = files_on_disk

    return jsonify(result)


# ---------------------------------------------------------------------------
# Asset serving
# ---------------------------------------------------------------------------

@animation_bp.route("/api/animator/open-folder/<project_id>/<int:scene_index>", methods=["POST"])
def open_asset_scene_folder(project_id, scene_index):
    """Open a specific scene's asset folder in the OS file explorer."""
    if not is_loopback_remote(request.remote_addr):
        return jsonify({"error": "Forbidden"}), 403

    safe_id = "".join(c for c in project_id if c.isalnum() or c in ("_", "-"))
    folder = os.path.join(ANIMATOR_DIR, safe_id, str(scene_index))
    if not os.path.isdir(folder):
        return jsonify({"error": "Folder not found"}), 404
    folder = os.path.abspath(folder)
    try:
        if platform.system() == "Windows":
            subprocess.run(["explorer", folder], check=False)
        elif platform.system() == "Darwin":
            subprocess.run(["open", folder], check=False)
        else:
            subprocess.run(["xdg-open", folder], check=False)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error("Failed to open asset folder: {}", e)
        return jsonify({"error": str(e)}), 500


@animation_bp.route("/api/animator/thumbnails/<project_id>", methods=["POST"])
def generate_video_thumbnails(project_id):
    """Generate _thumb.jpg for all video files in a project that lack one."""
    safe_id = "".join(c for c in project_id if c.isalnum() or c in ("_", "-"))
    project_dir = os.path.join(ANIMATOR_DIR, safe_id)
    if not os.path.isdir(project_dir):
        return jsonify({"error": "Project not found"}), 404

    generated = []
    for scene_dir in sorted(os.listdir(project_dir)):
        scene_path = os.path.join(project_dir, scene_dir)
        if not os.path.isdir(scene_path):
            continue
        for fname in os.listdir(scene_path):
            lower = fname.lower()
            if not lower.endswith(VIDEO_EXTS):
                continue
            fpath = os.path.join(scene_path, fname)
            thumb = _video_thumbnail(fpath)
            if thumb:
                thumb_name = os.path.basename(thumb)
                generated.append({
                    "scene": scene_dir,
                    "thumb_url": f"/output/animator/{safe_id}/{scene_dir}/{thumb_name}",
                    "video_url": f"/output/animator/{safe_id}/{scene_dir}/{fname}",
                })

    return jsonify({"project_id": safe_id, "thumbnails": generated})


# Static file serving for /output/animator/ is handled by routes.py (serve_animator_file)
