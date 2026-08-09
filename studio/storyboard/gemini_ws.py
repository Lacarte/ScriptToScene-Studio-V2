"""Gemini image generator — the WebSocket transport for the storyboard extension.

Provides:
  WS  /ws/storyboard-gemini-image-grabber  — endpoint for the Gemini extension

Protocol (Extension → Server):
  { type: "EXTENSION_READY", source: "sts-gemini-ext" }
  { type: "IMAGE_UPLOAD", projectId, scene, image: { data, source_url } }
  { type: "STATUS_UPDATE", projectId, scene, status }
  { type: "JOB_RECEIVED", projectId, scenes }
  { type: "JOB_COMPLETE", projectId }

Protocol (Server → Extension):
  { type: "IMAGE_JOB", projectId, scenes: [...], aspectRatio, autoType }
  { type: "PONG" }

Step 14.2 reduced this module to transport. It no longer decides the aspect
ratio, no longer formats the manifest, and no longer decides whether a frame
gets a thumbnail or a watermark pass: it hands each arriving frame to
`studio.storyboard.jobs`, which applies the same treatment whichever provider
produced it. Post-completion behaviour (the watermark sweep and the animator
hand-off) is gated on the provider's declared capabilities rather than on this
being the Gemini code path.
"""

import base64
import json
import os
import threading

from loguru import logger

from studio.storyboard import jobs

PROVIDER_ID = "gemini_ws"

_ws_clients = []
_ws_lock = threading.Lock()
_pending_jobs = []  # Queue of IMAGE_JOB messages (multi-project)
_pending_job_lock = threading.Lock()


def register_runtime(app, sock=None):
    """Register the /ws/storyboard-gemini-image-grabber WebSocket route."""
    if sock is None:
        logger.warning("[gemini_ws] No socket provided, skipping runtime registration")
        return

    @sock.route("/ws/storyboard-gemini-image-grabber")
    def gemini_ws(ws):
        with _ws_lock:
            _ws_clients.append(ws)
            count = len(_ws_clients)
        logger.info("Gemini WS client connected (clients: {})", count)

        # Flush pending jobs to the newly connected client
        _flush_pending_jobs(ws)

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    logger.info("Gemini WS received None — client closed")
                    break
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Gemini WS bad JSON: {}", raw[:120] if raw else "")
                    continue
                logger.debug("Gemini WS ← {}", msg.get("type", "unknown"))
                _handle_message(msg, ws)
        except Exception as e:
            logger.info("Gemini WS closed: {}", e)
        finally:
            with _ws_lock:
                if ws in _ws_clients:
                    _ws_clients.remove(ws)
                count = len(_ws_clients)
            logger.info("Gemini WS client disconnected (clients: {})", count)


def _capability(name: str, default: bool = False) -> bool:
    """Read one declared capability of this provider (§20.4).

    Falls back to `default` when the registry has not been discovered, which is
    the case in unit tests that exercise the transport in isolation.
    """
    from studio.shared.providers_common.hub import hub

    instance = hub.get("storyboard", PROVIDER_ID)
    if instance is None:
        return default
    return bool(instance.capabilities.get(name, default))


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
        alive = _prune_dead_clients()
        logger.info("Gemini WS connection check: {} alive client(s)", len(alive))
        return len(alive) > 0


def queue_image_job(msg):
    """Queue an IMAGE_JOB message. Sends immediately to connected clients."""
    with _pending_job_lock:
        _pending_jobs.append(msg)

    sent = False
    with _ws_lock:
        client_count = len(_ws_clients)
        data = json.dumps(msg)
        for ws in list(_ws_clients):
            try:
                ws.send(data)
                sent = True
            except Exception as e:
                logger.warning("IMAGE_JOB send failed to a client: {}", e)

    pid = msg.get("projectId", "?")
    scenes_count = len(msg.get("scenes", []))
    if sent:
        logger.info(
            "IMAGE_JOB → Gemini extension ({} — {} scenes, clients: {}, awaiting JOB_RECEIVED)",
            pid, scenes_count, client_count,
        )
    else:
        logger.warning("IMAGE_JOB queued — NO connected clients ({} — {} scenes)", pid, scenes_count)


def _flush_pending_jobs(ws):
    """Re-send all pending jobs to a newly connected client (kept until JOB_COMPLETE)."""
    with _pending_job_lock:
        pending = list(_pending_jobs)

    for msg in pending:
        try:
            ws.send(json.dumps(msg))
            logger.info(
                "Flushed pending IMAGE_JOB to new Gemini client ({} — {} scenes)",
                msg.get("projectId", "?"), len(msg.get("scenes", [])),
            )
        except Exception as e:
            logger.warning("Flush IMAGE_JOB failed: {}", e)


def _drop_pending(project_id):
    with _pending_job_lock:
        before = len(_pending_jobs)
        _pending_jobs[:] = [j for j in _pending_jobs if j.get("projectId") != project_id]
        return before - len(_pending_jobs)


def _handle_message(msg, ws):
    """Process a message from the Gemini extension."""
    msg_type = msg.get("type", "")

    if msg_type == "EXTENSION_READY":
        with _pending_job_lock:
            pending = len(_pending_jobs)
        logger.success(
            "Gemini extension HANDSHAKE ← source={}, pending_jobs={}",
            msg.get("source", "unknown"), pending,
        )
        _flush_pending_jobs(ws)

    elif msg_type == "IMAGE_UPLOAD":
        logger.info(
            "Gemini ← IMAGE_UPLOAD {} scene {}",
            msg.get("projectId", "?"), msg.get("scene", "?"),
        )
        _handle_image_upload(msg)

    elif msg_type == "STATUS_UPDATE":
        project_id = msg.get("projectId", "")
        scene = msg.get("scene")
        status = msg.get("status", "")
        logger.info("Gemini ← STATUS_UPDATE {} scene {} → {}", project_id or "?", scene, status)
        if project_id:
            jobs.mark_scene(project_id, scene, status)

    elif msg_type == "JOB_RECEIVED":
        project_id = msg.get("projectId", "")
        removed = _drop_pending(project_id)
        logger.success(
            "Gemini ← JOB_RECEIVED {} ({} scenes, cleared {} pending)",
            project_id, msg.get("scenes", 0), removed,
        )

    elif msg_type == "JOB_COMPLETE":
        project_id = msg.get("projectId", "")
        # Also clean pending in case JOB_RECEIVED was missed
        _drop_pending(project_id)
        logger.success("Gemini ← JOB_COMPLETE {}", project_id)
        _mark_job_done(project_id)

    elif msg_type in ("DIAGNOSE", "DIAGNOSE_REPORT", "FORCE_DISCONNECT"):
        # Relay to all OTHER connected clients (diagnostic bridge)
        data = json.dumps(msg)
        with _ws_lock:
            for client in list(_ws_clients):
                if client is not ws:
                    try:
                        client.send(data)
                    except Exception:
                        pass
            others = len(_ws_clients) - 1
        logger.info("Relayed {} to {} other client(s)", msg_type, others)

    elif msg_type == "PING":
        try:
            ws.send(json.dumps({"type": "PONG"}))
        except Exception:
            pass


def _handle_image_upload(msg):
    """Save a base64 frame from the extension through the shared job store."""
    project_id = msg.get("projectId", "")
    scene_num = msg.get("scene")
    image = msg.get("image", {})
    image_data = image.get("data", "") if isinstance(image, dict) else ""

    if not project_id or scene_num is None or not image_data:
        logger.warning("IMAGE_UPLOAD missing fields")
        return

    logger.info(
        "IMAGE_UPLOAD: {} scene {} (~{} KB)",
        project_id, scene_num, len(image_data) * 3 // 4 // 1024,
    )

    try:
        if "," in image_data:
            header, encoded = image_data.split(",", 1)
            ext = jobs.extension_for(header, default=".png")
            if "jpeg" in header or "jpg" in header:
                ext = ".jpeg"
            elif "webp" in header:
                ext = ".webp"
            elif "png" in header:
                ext = ".png"
        else:
            encoded, ext = image_data, ".jpeg"

        destination = jobs.prepare_scene_file(project_id, scene_num, ext)
        with open(destination, "wb") as handle:
            handle.write(base64.b64decode(encoded))
        logger.success("Saved: {} ({:.0f} KB)", destination, os.path.getsize(destination) / 1024)
    except (OSError, ValueError) as exc:
        logger.error("IMAGE_UPLOAD save failed: {}", exc)
        jobs.record_error(project_id, scene_num, "The uploaded frame could not be saved")
        return

    # Watermark removal and thumbnail generation are both applied by the job
    # store, so an extension frame carries the same per-scene metadata as a
    # downloaded one. Off the WebSocket thread: the remover loads a CV stack
    # and the extension is waiting to send the next frame.
    threading.Thread(
        target=jobs.record_ready,
        args=(project_id, scene_num, destination),
        kwargs={"remove_watermark": _capability("watermark_removal", True)},
        name=f"storyboard-frame-{project_id}-{scene_num}",
        daemon=True,
    ).start()


def activate_tab():
    """Send ACTIVATE_TAB to all connected Gemini extension clients."""
    return _broadcast({"type": "ACTIVATE_TAB"}, label="ACTIVATE_TAB", prune=True)


def focus_studio_tab():
    """Send FOCUS_STUDIO_TAB to all connected Gemini extension clients."""
    return _broadcast({"type": "FOCUS_STUDIO_TAB"}, label="FOCUS_STUDIO_TAB")


def _broadcast(message, *, label, prune=False):
    data = json.dumps(message)
    sent = False
    with _ws_lock:
        if prune:
            logger.info("{} → {} alive client(s)", label, len(_prune_dead_clients()))
        for ws in list(_ws_clients):
            try:
                ws.send(data)
                sent = True
            except Exception as e:
                logger.warning("{} send failed: {}", label, e)
    if sent:
        logger.info("{} delivered to Gemini extension", label)
    else:
        logger.warning("{} failed — no connected Gemini clients", label)
    return sent


def _mark_job_done(project_id):
    """Close the job, then run the provider's declared completion behaviour."""
    jobs.mark_done(project_id)

    if _capability("watermark_removal", True):
        _sweep_watermarks(project_id)
    if _capability("auto_animate", True):
        threading.Thread(
            target=_push_to_grok, args=(project_id,),
            name=f"storyboard-handoff-{project_id}", daemon=True,
        ).start()


def _sweep_watermarks(project_id):
    """Re-run watermark removal across a project's frames."""
    return jobs.sweep_watermarks(project_id)


def _push_to_grok(project_id):
    """Hand the finished frames and their prompts to the animator extension.

    Declared as the `auto_animate` capability. The transport it uses moves into
    the shared callback/extension layer in 14.4; the behaviour is unchanged.
    """
    from studio.io_utils import safe_json_read

    prompts_path = jobs.scene_prompts_path(project_id)
    if not os.path.isfile(prompts_path):
        logger.warning("No scene prompts for {} — cannot hand off to the animator", project_id)
        return

    try:
        scenes = safe_json_read(prompts_path)
    except (OSError, ValueError) as exc:
        logger.error("Failed to read scene prompts: {}", exc)
        return
    if not isinstance(scenes, list):
        return

    handoff = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        index = scene.get("scene")
        prompt = scene.get("prompt", "")
        if index is None or not prompt:
            continue
        entry = {"scene": index, "prompt": prompt}
        frame = jobs.current_image(project_id, index)
        if frame:
            encoded = _encode_frame(frame)
            if encoded:
                entry["image"] = encoded
        handoff.append(entry)

    if not handoff:
        logger.warning("No scenes to hand off to the animator for {}", project_id)
        return

    try:
        from studio.animator.routes import activate_tab as animator_activate, queue_grabber_start

        animator_activate()
        queue_grabber_start({
            "type": "GRABBER_START",
            "projectId": project_id,
            "scenes": handoff,
            "aspectRatio": "9:16",
            "grokMode": "video",
            "grokDuration": "6s",
            "autoType": True,
        })
        logger.success("Handed {} scenes to the animator for {}", len(handoff), project_id)
    except Exception as exc:
        logger.error("Animator hand-off failed: {}", exc)


def _encode_frame(path: str) -> str | None:
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return None
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
    return f"data:image/{mime};base64,{base64.b64encode(raw).decode()}"
