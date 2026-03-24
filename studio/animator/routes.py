"""Animator Module — WebSocket bridge to Chrome extension for Grok automation.

The STS backend sends image+prompt pairs to the Chrome extension via WebSocket.
The extension automates Grok's image-to-video generation and returns video URLs.

Provides:
  WS   /ws/animator-grok-video-grabber      — WebSocket endpoint (via flask-sock)
  POST /api/animator/submit                 — submit animation jobs
  GET  /api/animator/status/<project_id>    — poll job status
  GET  /api/animator/videos/<project_id>    — list generated videos
  GET  /api/animator/videos/<project_id>/<f> — serve individual video
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime

import requests as http_requests
from flask import Blueprint, jsonify, request, send_from_directory
from loguru import logger

import base64 as b64_mod

from config import OUTPUT_DIR, STORYBOARD_DIR, SCENES_DIR, ANIMATOR_DIR
from studio.io_utils import safe_json_write, safe_json_read
from studio.security import sanitize_project_id

animator_bp = Blueprint("animator", __name__)

# ---------------------------------------------------------------------------
# WebSocket state
# ---------------------------------------------------------------------------
_ws_clients = []
_ws_lock = threading.Lock()
_jobs = {}
_jobs_lock = threading.Lock()
_pending_grabber = None  # Queued GRABBER_START message to send on next WS connect
_pending_grabber_lock = threading.Lock()


def _broadcast(msg):
    """Send a JSON message to all connected WebSocket clients."""
    data = json.dumps(msg)
    with _ws_lock:
        dead = []
        for ws in _ws_clients:
            try:
                ws.send(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_clients.remove(ws)


def _send_to_extension(msg):
    """Send a message to the first connected extension client."""
    with _ws_lock:
        if not _ws_clients:
            return False
        try:
            _ws_clients[0].send(json.dumps(msg))
            return True
        except Exception:
            return False


def queue_grabber_start(msg):
    """Queue a GRABBER_START message. Sends immediately AND keeps queued for late-connecting clients."""
    global _pending_grabber
    with _pending_grabber_lock:
        _pending_grabber = msg
    # Try to send immediately to already-connected clients
    sent = False
    with _ws_lock:
        if _ws_clients:
            data = json.dumps(msg)
            for ws in _ws_clients:
                try:
                    ws.send(data)
                    sent = True
                except Exception:
                    pass
    # Don't clear _pending_grabber — keep it for late-connecting clients (e.g. Automa)
    if sent:
        logger.info("GRABBER_START sent to connected client(s), still queued for new connections")
    else:
        logger.info("GRABBER_START queued — waiting for client to connect")


def _flush_pending_grabber(ws):
    """Send any queued GRABBER_START to a newly connected client."""
    global _pending_grabber
    with _pending_grabber_lock:
        msg = _pending_grabber
        if not msg:
            return
        _pending_grabber = None
    try:
        ws.send(json.dumps(msg))
        logger.info("Flushed queued GRABBER_START to new client")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# WebSocket endpoint (initialized from app.py via flask-sock)
# ---------------------------------------------------------------------------

def init_animator_ws(sock):
    """Register the /ws/animator-grok-video-grabber WebSocket route on the flask-sock instance."""

    @sock.route("/ws/animator-grok-video-grabber")
    def animator_ws(ws):
        logger.info("Animator WebSocket client connected")
        with _ws_lock:
            _ws_clients.append(ws)

        # Send current status on connect
        try:
            ws.send(json.dumps({
                "type": "CONNECTED",
                "message": "STS Animator WebSocket connected",
                "pendingJobs": _count_pending_jobs(),
            }))
        except Exception:
            pass

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    break
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue

                _handle_ws_message(msg)
        except Exception as e:
            logger.debug("Animator WS closed: {}", e)
        finally:
            with _ws_lock:
                if ws in _ws_clients:
                    _ws_clients.remove(ws)
            logger.info("Animator WebSocket client disconnected")


def _count_pending_jobs():
    with _jobs_lock:
        count = 0
        for job in _jobs.values():
            for s in job.get("scenes", {}).values():
                if s.get("status") in ("pending", "processing"):
                    count += 1
        return count


def _handle_ws_message(msg):
    """Handle incoming messages from the Chrome extension."""
    msg_type = msg.get("type")

    if msg_type == "ANIMATE_RESULT":
        _handle_result(msg)
    elif msg_type == "ANIMATE_PROGRESS":
        _handle_progress(msg)
    elif msg_type == "EXTENSION_READY":
        logger.info("Extension reported ready (source: {})", msg.get("source", "unknown"))
        # Send any queued grabber data to this client
        with _ws_lock:
            if _ws_clients:
                _flush_pending_grabber(_ws_clients[-1])
    elif msg_type == "ASSET_UPLOAD":
        _handle_asset_upload_ws(msg)
    elif msg_type == "ASSET_UPLOADED":
        _handle_asset_uploaded(msg)
    elif msg_type == "ASSET_RESULT":
        _handle_asset_result(msg)
    elif msg_type == "PONG":
        pass  # heartbeat response
    elif msg_type == "RATE_LIMITED":
        wait_ms = msg.get("waitMs", 0)
        retry_count = msg.get("retryCount", 0)
        mins = int(wait_ms / 60000)
        if retry_count:
            logger.warning("Grok rate limited — retry #{}, waiting {}m", retry_count, mins)
        else:
            logger.warning("Grok rate limited — waiting {}m", mins)
    elif msg_type == "RATE_LIMIT_CLEARED":
        logger.success("Grok rate limit cleared, resuming")
    else:
        logger.warning("Unknown animator WS message type: {}", msg_type)


def _handle_result(msg):
    """Process a completed animation result from the extension."""
    job_id = msg.get("jobId")
    scene_key = str(msg.get("sceneIndex", ""))
    success = msg.get("success", False)
    video_url = msg.get("videoUrl")
    error = msg.get("error")

    if not job_id:
        return

    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return

        scene = job["scenes"].get(scene_key)
        if not scene:
            return

        if success and video_url:
            scene["status"] = "downloading"
            scene["video_url"] = video_url

            # Download in background
            project_id = job["project_id"]
            threading.Thread(
                target=_download_video,
                args=(project_id, job_id, scene_key, video_url),
                daemon=True,
            ).start()
        elif success and not video_url:
            scene["status"] = "ready"
        else:
            scene["status"] = "error"
            scene["error"] = error or "Unknown error"

        _update_job_status(job)
        _save_job_state(job)


def _handle_progress(msg):
    """Update progress for an in-flight animation."""
    job_id = msg.get("jobId")
    scene_key = str(msg.get("sceneIndex", ""))
    percentage = msg.get("percentage", 0)

    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        scene = job["scenes"].get(scene_key)
        if scene:
            scene["status"] = "processing"
            scene["percentage"] = percentage


def _handle_asset_upload_ws(msg):
    """Handle base64 asset data sent via WebSocket — save to disk.

    Message format:
        { type: "ASSET_UPLOAD", projectId, scene, images: [{data, source_url, ext, filename}] }
    """
    project_id = sanitize_project_id(msg.get("projectId", ""))
    scene_num = msg.get("scene")
    images = msg.get("images", [])

    if not project_id or scene_num is None or not images:
        logger.warning("ASSET_UPLOAD missing required fields")
        return

    scene_num = str(scene_num)
    total_kb = sum(len(img.get("data", "")) * 3 // 4 // 1024 for img in images)
    logger.info("ASSET_UPLOAD via WS: {} scene {} — {} file(s), ~{} KB",
                project_id, scene_num, len(images), total_kb)

    from config import ASSETS_DIR
    from studio.assets.organizer import save_base64_assets

    def _save():
        try:
            local_files = save_base64_assets(
                project_id=project_id,
                scene_num=scene_num,
                images=images,
                assets_dir=ASSETS_DIR,
            )
            logger.success("ASSET_UPLOAD: {} scene {} — {} files saved", project_id, scene_num, len(local_files))

            # Update grabber job status
            from studio.assets.routes import _get_job, _save_job, _mark_job_done
            job = _get_job(project_id)
            if job and scene_num in job.get("scene_statuses", {}):
                job["scene_statuses"][scene_num]["status"] = "ready"
                job["scene_statuses"][scene_num]["local_files"] = local_files
                job["scene_statuses"][scene_num]["urls"] = [
                    img.get("source_url", "") for img in images
                ]
                job["updated_at"] = datetime.now().isoformat()
                all_done = all(
                    s.get("status") in ("ready", "error", "downloaded")
                    for s in job["scene_statuses"].values()
                )
                if all_done:
                    _mark_job_done(job)
                _save_job(job)
        except Exception as e:
            logger.error("ASSET_UPLOAD save failed for {} scene {}: {}", project_id, scene_num, e)

    threading.Thread(target=_save, daemon=True).start()


def _handle_asset_uploaded(msg):
    """Handle notification that Automa uploaded assets for a scene."""
    project_id = msg.get("projectId")
    scene = msg.get("scene")
    count = msg.get("count", 0)
    logger.info("Asset upload notification: {} scene {} ({} files)", project_id, scene, count)


def _handle_asset_result(msg):
    """Handle video/image URL results from Automa — download to assets folder.

    Message format:
        { type: "ASSET_RESULT", projectId, scene, urls: ["https://..."] }
    """
    project_id = sanitize_project_id(msg.get("projectId", ""))
    scene_num = msg.get("scene")
    urls = msg.get("urls", [])

    if not project_id or scene_num is None or not urls:
        logger.warning("ASSET_RESULT missing required fields: {}", msg)
        return

    scene_num = str(scene_num)

    # Grok CDN (assets.grok.com) requires auth — server-side download returns 403.
    # Log warning and skip; Automa should use ASSET_UPLOAD with base64 data instead.
    grok_urls = [u for u in urls if "assets.grok.com" in u]
    if grok_urls:
        logger.warning(
            "ASSET_RESULT: {} scene {} — {} Grok CDN URL(s) cannot be downloaded "
            "server-side (403). Client should use ASSET_UPLOAD with base64 data.",
            project_id, scene_num, len(grok_urls),
        )
        # Filter out Grok URLs, only download non-Grok URLs
        urls = [u for u in urls if "assets.grok.com" not in u]
        if not urls:
            return

    logger.info("ASSET_RESULT: downloading {} URL(s) for {} scene {}", len(urls), project_id, scene_num)

    from config import ASSETS_DIR
    from studio.assets.organizer import organize_grabber_assets

    def _download():
        try:
            local_files = organize_grabber_assets(
                project_id=project_id,
                scene_num=scene_num,
                urls=urls,
                assets_dir=ASSETS_DIR,
            )
            logger.success("ASSET_RESULT: {} scene {} — {} files saved", project_id, scene_num, len(local_files))

            # Update grabber job status if one exists
            from studio.assets.routes import _get_job, _save_job, _mark_job_done
            job = _get_job(project_id)
            if job and scene_num in job.get("scene_statuses", {}):
                job["scene_statuses"][scene_num]["status"] = "ready"
                job["scene_statuses"][scene_num]["urls"] = urls
                job["scene_statuses"][scene_num]["local_files"] = local_files
                job["updated_at"] = datetime.now().isoformat()
                # Check if all scenes are now done
                all_done = all(
                    s.get("status") in ("ready", "error", "downloaded")
                    for s in job["scene_statuses"].values()
                )
                if all_done:
                    _mark_job_done(job)
                _save_job(job)
        except Exception as e:
            logger.error("ASSET_RESULT download failed for {} scene {}: {}", project_id, scene_num, e)

    threading.Thread(target=_download, daemon=True).start()


def _download_video(project_id, job_id, scene_key, video_url):
    """Download a video from the given URL to output/animator/{project_id}/{scene_key}/."""
    scene_dir = os.path.join(ANIMATOR_DIR, project_id, scene_key)
    os.makedirs(scene_dir, exist_ok=True)

    ext = "mp4"
    if ".webm" in video_url:
        ext = "webm"
    filename = f"{scene_key}.{ext}"
    filepath = os.path.join(scene_dir, filename)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    for attempt in range(3):
        try:
            resp = http_requests.get(video_url, headers=headers, timeout=120, stream=True)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            with _jobs_lock:
                job = _jobs.get(job_id)
                if job and scene_key in job["scenes"]:
                    job["scenes"][scene_key]["status"] = "ready"
                    job["scenes"][scene_key]["local_path"] = f"{scene_key}/{filename}"
                    _update_job_status(job)
                    _save_job_state(job)

            logger.info("Downloaded animator video: {}/{}", project_id, filename)
            return

        except Exception as e:
            logger.warning("Download attempt {}/3 failed for scene {}: {}", attempt + 1, scene_key, e)
            if attempt < 2:
                time.sleep(2 ** attempt)

    # All retries failed
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job and scene_key in job["scenes"]:
            job["scenes"][scene_key]["status"] = "error"
            job["scenes"][scene_key]["error"] = f"Download failed after 3 attempts"
            _update_job_status(job)
            _save_job_state(job)


def _update_job_status(job):
    """Recompute aggregate job status from scene statuses."""
    scenes = job["scenes"]
    statuses = [s["status"] for s in scenes.values()]

    if all(s == "ready" for s in statuses):
        job["status"] = "done"
        job["completed_at"] = datetime.now().isoformat()
    elif any(s in ("pending", "processing", "downloading") for s in statuses):
        job["status"] = "running"
    elif all(s in ("ready", "error") for s in statuses):
        job["status"] = "done"
        job["completed_at"] = datetime.now().isoformat()

    job["ready"] = sum(1 for s in statuses if s == "ready")
    job["errors"] = sum(1 for s in statuses if s == "error")


def _save_job_state(job):
    """Persist job state to disk."""
    project_dir = os.path.join(ANIMATOR_DIR, job["project_id"])
    os.makedirs(project_dir, exist_ok=True)
    safe_json_write(os.path.join(project_dir, "animator.json"), job)


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------

@animator_bp.route("/api/animator/submit", methods=["POST"])
def submit_jobs():
    """Submit animation jobs — sends image+prompt pairs to the extension."""
    data = request.get_json(silent=True) or {}
    project_id = sanitize_project_id(data.get("project_id", ""))
    scenes = data.get("scenes", [])
    mode = data.get("mode", "imageToVideo")
    duration = data.get("duration", "6s")
    aspect_ratio = data.get("aspect_ratio", "9:16")

    if not project_id or not scenes:
        return jsonify({"error": "project_id and scenes are required"}), 400

    # Check extension is connected
    with _ws_lock:
        if not _ws_clients:
            return jsonify({"error": "No Chrome extension connected"}), 503

    job_id = str(uuid.uuid4())[:8]

    # Build job
    job = {
        "job_id": job_id,
        "project_id": project_id,
        "status": "running",
        "total": len(scenes),
        "ready": 0,
        "errors": 0,
        "mode": mode,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "scenes": {},
    }

    for i, scene in enumerate(scenes):
        key = str(i)
        job["scenes"][key] = {
            "status": "pending",
            "prompt": scene.get("prompt", ""),
            "image_path": scene.get("image_path", ""),
            "image_base64": scene.get("image_base64", ""),
            "video_url": None,
            "local_path": None,
            "error": None,
            "percentage": 0,
        }

    with _jobs_lock:
        _jobs[job_id] = job

    _save_job_state(job)

    # Send jobs to extension
    payloads = []
    for i, scene in enumerate(scenes):
        payload = {
            "type": "ANIMATE_JOB",
            "jobId": job_id,
            "projectId": project_id,
            "sceneIndex": i,
            "prompt": scene.get("prompt", ""),
            "mode": mode,
            "duration": duration,
            "aspectRatio": aspect_ratio,
        }

        # Resolve image: prefer base64, fall back to reading file
        if scene.get("image_base64"):
            payload["image"] = scene["image_base64"]
        elif scene.get("image_path"):
            img_path = scene["image_path"]
            if os.path.isfile(img_path):
                import base64
                with open(img_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                ext = os.path.splitext(img_path)[1].lstrip(".")
                mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
                payload["image"] = f"data:image/{mime};base64,{b64}"

        payloads.append(payload)

    # Send all jobs to extension
    for payload in payloads:
        _send_to_extension(payload)

    logger.info("Submitted {} animator jobs for project {}", len(scenes), project_id)
    return jsonify({"job_id": job_id, "total": len(scenes), "status": "running"})


@animator_bp.route("/api/animator/submit-storyboard", methods=["POST"])
def submit_storyboard():
    """Submit animation jobs using storyboard images as references.

    Reads storyboard images from output/storyboard/{project_id}/{scene}/image.*
    and scene prompts from output/scenes/{project_id}/scenes.json.
    Sends each scene as imageToVideo to the Chrome extension.
    """
    data = request.get_json(silent=True) or {}
    project_id = sanitize_project_id(data.get("project_id", ""))
    mode = data.get("mode", "imageToVideo")
    duration = data.get("duration", "6s")
    aspect_ratio = data.get("aspect_ratio", "9:16")

    if not project_id:
        return jsonify({"error": "project_id is required"}), 400

    with _ws_lock:
        if not _ws_clients:
            return jsonify({"error": "No Chrome extension connected"}), 503

    # Load scene prompts
    scenes_json = os.path.join(SCENES_DIR, project_id, "scenes.json")
    if not os.path.isfile(scenes_json):
        return jsonify({"error": f"No scenes.json found for {project_id}"}), 404

    scenes_data = safe_json_read(scenes_json)
    scene_list = scenes_data.get("scenes", [])
    if not scene_list:
        return jsonify({"error": "No scenes in scenes.json"}), 400

    # Find storyboard images
    sb_dir = os.path.join(STORYBOARD_DIR, project_id)
    image_exts = (".jpeg", ".jpg", ".png", ".webp")

    scenes_payload = []
    for scene in scene_list:
        idx = scene.get("index", 0)
        prompt = scene.get("image_prompt", "")
        scene_img_dir = os.path.join(sb_dir, str(idx))

        # Find image file
        image_path = None
        if os.path.isdir(scene_img_dir):
            for fname in os.listdir(scene_img_dir):
                if fname.startswith("image") and fname.lower().endswith(image_exts) and "_v" not in fname:
                    image_path = os.path.join(scene_img_dir, fname)
                    break

        if not image_path or not os.path.isfile(image_path):
            logger.warning("[{}] No storyboard image for scene {}, skipping", project_id, idx)
            continue

        # Read and encode image
        with open(image_path, "rb") as f:
            raw = f.read()
        ext = os.path.splitext(image_path)[1].lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
        image_b64 = f"data:image/{mime};base64,{b64_mod.b64encode(raw).decode()}"

        scenes_payload.append({
            "prompt": prompt,
            "image_base64": image_b64,
            "scene_index": idx,
        })

    if not scenes_payload:
        return jsonify({"error": "No storyboard images found for any scene"}), 404

    # Build job
    job_id = str(uuid.uuid4())[:8]
    job = {
        "job_id": job_id,
        "project_id": project_id,
        "status": "running",
        "total": len(scenes_payload),
        "ready": 0,
        "errors": 0,
        "mode": mode,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "scenes": {},
    }

    for i, sp in enumerate(scenes_payload):
        key = str(sp["scene_index"])
        job["scenes"][key] = {
            "status": "pending",
            "prompt": sp["prompt"],
            "image_path": "",
            "image_base64": "(storyboard)",
            "video_url": None,
            "local_path": None,
            "error": None,
            "percentage": 0,
        }

    with _jobs_lock:
        _jobs[job_id] = job
    _save_job_state(job)

    # Send jobs to extension
    for sp in scenes_payload:
        _send_to_extension({
            "type": "ANIMATE_JOB",
            "jobId": job_id,
            "projectId": project_id,
            "sceneIndex": sp["scene_index"],
            "prompt": sp["prompt"],
            "image": sp["image_base64"],
            "mode": mode,
            "duration": duration,
            "aspectRatio": aspect_ratio,
        })

    logger.info("Submitted {} storyboard animator jobs for {}", len(scenes_payload), project_id)
    return jsonify({"job_id": job_id, "total": len(scenes_payload), "status": "running"})


@animator_bp.route("/api/animator/status/<project_id>")
def animator_status(project_id):
    """Get animator job status for a project."""
    project_id = sanitize_project_id(project_id)

    # Check in-memory first
    with _jobs_lock:
        for job in _jobs.values():
            if job["project_id"] == project_id:
                return jsonify(job)

    # Fall back to disk
    state_path = os.path.join(ANIMATOR_DIR, project_id, "animator.json")
    if os.path.isfile(state_path):
        return jsonify(safe_json_read(state_path))

    return jsonify({"error": "Not found"}), 404


@animator_bp.route("/api/animator/videos/<project_id>")
def list_videos(project_id):
    """List generated videos for a project."""
    project_id = sanitize_project_id(project_id)
    project_dir = os.path.join(ANIMATOR_DIR, project_id)
    if not os.path.isdir(project_dir):
        return jsonify({"videos": []})

    videos = []
    for scene_name in sorted(os.listdir(project_dir)):
        scene_path = os.path.join(project_dir, scene_name)
        if os.path.isdir(scene_path):
            for f in sorted(os.listdir(scene_path)):
                if f.endswith((".mp4", ".webm")):
                    videos.append(f"{scene_name}/{f}")
    return jsonify({"videos": videos, "project_id": project_id})


@animator_bp.route("/api/animator/videos/<project_id>/<scene>/<filename>")
def serve_video(project_id, scene, filename):
    """Serve an individual generated video."""
    project_id = sanitize_project_id(project_id)
    scene_dir = os.path.join(ANIMATOR_DIR, project_id, scene)
    return send_from_directory(scene_dir, filename)


@animator_bp.route("/output/animator/<path:filepath>")
def serve_animator_file(filepath):
    """Serve animator output files (videos) for the editor/export pipeline."""
    resp = send_from_directory(ANIMATOR_DIR, filepath)
    resp.headers.setdefault("Accept-Ranges", "bytes")
    return resp
