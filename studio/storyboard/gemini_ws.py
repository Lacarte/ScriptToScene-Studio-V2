"""
Gemini Image Generator — WebSocket handler for storyboard.

Provides:
  WS  /ws/image-gemini  — WebSocket endpoint for Gemini Chrome extension

Protocol (Extension → Server):
  { type: "EXTENSION_READY", source: "sts-gemini-ext" }
  { type: "IMAGE_UPLOAD", projectId, scene, image: { data, source_url } }
  { type: "STATUS_UPDATE", scene, status }
  { type: "JOB_COMPLETE", projectId }

Protocol (Server → Extension):
  { type: "IMAGE_JOB", projectId, scenes: [...], aspectRatio, autoType }
  { type: "PONG" }
"""

import base64
import json
import os
import threading
from loguru import logger

_ws_clients = []
_ws_lock = threading.Lock()
_pending_jobs = []  # Queue of IMAGE_JOB messages (multi-project)
_pending_job_lock = threading.Lock()


def init_gemini_ws(sock):
    """Register the /ws/image-gemini WebSocket route."""

    @sock.route("/ws/image-gemini")
    def gemini_ws(ws):
        logger.info("Gemini WS client connected")
        with _ws_lock:
            _ws_clients.append(ws)

        # Flush pending job to newly connected client
        _flush_pending_jobs(ws)

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    break
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                _handle_message(msg, ws)
        except Exception as e:
            logger.debug("Gemini WS closed: {}", e)
        finally:
            with _ws_lock:
                if ws in _ws_clients:
                    _ws_clients.remove(ws)
            logger.info("Gemini WS client disconnected")


def _prune_dead_clients():
    """Remove dead WebSocket connections by sending a PING. Must hold _ws_lock."""
    alive = []
    ping = json.dumps({"type": "PING"})
    for ws in _ws_clients:
        try:
            ws.send(ping)
            alive.append(ws)
        except Exception:
            pass
    _ws_clients[:] = alive
    return alive


def is_extension_connected():
    """Check if at least one Gemini extension client is connected."""
    with _ws_lock:
        return len(_prune_dead_clients()) > 0


def queue_image_job(msg):
    """Queue an IMAGE_JOB message. Sends immediately to connected clients."""
    with _pending_job_lock:
        _pending_jobs.append(msg)

    sent = False
    with _ws_lock:
        data = json.dumps(msg)
        for ws in list(_ws_clients):
            try:
                ws.send(data)
                sent = True
            except Exception:
                pass

    pid = msg.get("projectId", "?")
    scenes_count = len(msg.get("scenes", []))
    if sent:
        # Remove from pending since it was delivered
        with _pending_job_lock:
            if msg in _pending_jobs:
                _pending_jobs.remove(msg)
        logger.info("IMAGE_JOB sent to Gemini extension ({} — {} scenes)", pid, scenes_count)
    else:
        logger.info("IMAGE_JOB queued — waiting for Gemini extension ({} — {} scenes)", pid, scenes_count)


def _flush_pending_jobs(ws):
    """Send all queued jobs to a newly connected client."""
    with _pending_job_lock:
        jobs = list(_pending_jobs)
        _pending_jobs.clear()

    for msg in jobs:
        try:
            ws.send(json.dumps(msg))
            pid = msg.get("projectId", "?")
            logger.info("Flushed queued IMAGE_JOB to new Gemini client ({})", pid)
        except Exception:
            pass


def _handle_message(msg, ws):
    """Process a message from the Gemini extension."""
    msg_type = msg.get("type", "")

    if msg_type == "EXTENSION_READY":
        source = msg.get("source", "unknown")
        logger.info("Gemini extension ready (source: {})", source)
        _flush_pending_jobs(ws)

    elif msg_type == "IMAGE_UPLOAD":
        _handle_image_upload(msg)

    elif msg_type == "STATUS_UPDATE":
        project_id = msg.get("projectId", "")
        scene = msg.get("scene")
        status = msg.get("status", "")
        logger.info("Gemini {} scene {} status: {}", project_id or "?", scene, status)
        _update_scene_status(project_id, scene, status)

    elif msg_type == "JOB_COMPLETE":
        project_id = msg.get("projectId", "")
        logger.success("Gemini job complete: {}", project_id)
        _mark_job_done(project_id)

    elif msg_type == "PING":
        try:
            ws.send(json.dumps({"type": "PONG"}))
        except Exception:
            pass


def _handle_image_upload(msg):
    """Save a base64 image from the Gemini extension to the storyboard output."""
    project_id = msg.get("projectId", "")
    scene_num = msg.get("scene")
    image = msg.get("image", {})
    image_data = image.get("data", "") if isinstance(image, dict) else ""

    if not project_id or scene_num is None or not image_data:
        logger.warning("IMAGE_UPLOAD missing fields")
        return

    scene_key = str(scene_num)
    data_size = len(image_data) * 3 // 4 // 1024
    logger.info("IMAGE_UPLOAD: {} scene {} (~{} KB)", project_id, scene_key, data_size)

    from config import STORYBOARD_DIR

    def _save():
        try:
            scene_dir = os.path.join(STORYBOARD_DIR, project_id, scene_key)
            os.makedirs(scene_dir, exist_ok=True)

            # Strip data URI prefix
            if "," in image_data:
                header, b64 = image_data.split(",", 1)
                ext = ".png"
                if "jpeg" in header or "jpg" in header:
                    ext = ".jpeg"
                elif "webp" in header:
                    ext = ".webp"
            else:
                b64 = image_data
                ext = ".jpeg"

            filepath = os.path.join(scene_dir, f"image{ext}")
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(b64))

            size_kb = os.path.getsize(filepath) / 1024
            logger.success("Saved: {} ({:.0f} KB)", filepath, size_kb)

            # Update storyboard job status
            _update_scene_status(project_id, scene_num, "ready",
                                 local_path=f"/output/storyboard/{project_id}/{scene_key}/image{ext}")
        except Exception as e:
            logger.error("IMAGE_UPLOAD save failed: {}", e)
            _update_scene_status(project_id, scene_num, "error")

    threading.Thread(target=_save, daemon=True).start()


def _update_scene_status(project_id, scene_num, status, local_path=None):
    """Update scene status in the storyboard job JSON."""
    if not project_id:
        return
    try:
        from config import STORYBOARD_DIR
        job_path = os.path.join(STORYBOARD_DIR, project_id, "storyboard.json")
        if not os.path.isfile(job_path):
            return

        with open(job_path, "r", encoding="utf-8") as f:
            job = json.load(f)

        scene_key = str(scene_num)
        statuses = job.get("scene_statuses", {})
        if scene_key not in statuses:
            statuses[scene_key] = {}

        statuses[scene_key]["status"] = status
        if local_path:
            statuses[scene_key]["local_path"] = local_path

        job["scene_statuses"] = statuses

        # Update ready count and check if all done
        total = job.get("total", 0)
        ready = sum(1 for k, s in statuses.items() if k != "-1" and s.get("status") in ("ready", "done"))
        job["ready"] = ready
        errors = sum(1 for k, s in statuses.items() if k != "-1" and s.get("status") == "error")
        job["errors"] = errors
        if ready >= total and total > 0:
            job["status"] = "done"
            job["completed_at"] = __import__("datetime").datetime.now().astimezone().isoformat()

        with open(job_path, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2)

    except Exception as e:
        logger.debug("Failed to update storyboard job: {}", e)


def activate_tab():
    """Send ACTIVATE_TAB to all connected Gemini extension clients."""
    msg = json.dumps({"type": "ACTIVATE_TAB"})
    sent = False
    with _ws_lock:
        _prune_dead_clients()
        for ws in list(_ws_clients):
            try:
                ws.send(msg)
                sent = True
            except Exception:
                pass
    if sent:
        logger.info("Sent ACTIVATE_TAB to Gemini extension")
    return sent


def _send_navigate(url):
    """Send NAVIGATE message to all connected extension clients."""
    msg = json.dumps({"type": "NAVIGATE", "url": url})
    with _ws_lock:
        for ws in list(_ws_clients):
            try:
                ws.send(msg)
                logger.info("Sent NAVIGATE to extension: {}", url)
            except Exception:
                pass


def _mark_job_done(project_id):
    """Mark the entire storyboard job as done and tell extension to navigate to Grok."""
    _update_scene_status(project_id, -1, "done")  # Trigger a save
    try:
        from config import STORYBOARD_DIR
        job_path = os.path.join(STORYBOARD_DIR, project_id, "storyboard.json")
        if os.path.isfile(job_path):
            with open(job_path, "r", encoding="utf-8") as f:
                job = json.load(f)
            job["status"] = "done"
            with open(job_path, "w", encoding="utf-8") as f:
                json.dump(job, f, indent=2)
            logger.info("Storyboard job {} marked done", project_id)
    except Exception as e:
        logger.debug("Failed to mark job done: {}", e)

    # Tell the extension to navigate to Grok for the assets step
    _send_navigate("https://grok.com/imagine")
