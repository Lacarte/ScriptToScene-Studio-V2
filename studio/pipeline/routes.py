"""Pipeline Module — Orchestrates the full TTS → Alignment → Segment → Scenes → Storyboard → Animator → Build → Export pipeline.

Provides:
  POST /api/pipeline/run           — start a pipeline job (returns job_id + project_id)
  POST /api/pipeline/<job_id>/stop — request a running pipeline to stop
  GET  /api/pipeline/progress/<id> — SSE stream of step-by-step progress
  GET  /api/pipeline/jobs          — list recent pipeline jobs
"""

import json
import os
import re
import shutil
import time
import threading
import uuid
from datetime import datetime
from queue import Queue

import numpy as np
import soundfile as sf
import requests as http_requests
from flask import Blueprint, Response, jsonify, request
from loguru import logger

from config import (
    TTS_DIR, ALIGN_DIR, SEGMENTER_DIR, SCENES_DIR, ANIMATOR_DIR, APP_ASSETS_DIR, EXPORT_DIR,
    PIPELINE_DIR, PROJECTS_DIR, STORYBOARD_DIR, N8N_WEBHOOK_URL, generate_project_id,
)
from studio.io_utils import safe_json_write, safe_json_read
from studio.validation import validate_json
from studio.pipeline.schemas import PipelineRunRequest

pipeline_bp = Blueprint("pipeline", __name__)

# ---------------------------------------------------------------------------
# Active jobs
# ---------------------------------------------------------------------------
_jobs = {}
_jobs_lock = threading.Lock()
ALL_PIPELINE_STEPS = ["tts", "timing", "segment", "scenes", "storyboard", "assets", "assemble", "export"]


def _extract_hook_opening_from_text(text: str) -> tuple[str, str]:
    """Extract a hook + opening pair from raw pipeline text.

    Handles two shapes:
      1. Sectioned story format produced by /story/generate:
         "Hook: ...\n\nBuild: ...\n\nClimax: ...\n\nCTA: ..."
         → hook = the Hook line, opening = first sentence of Build
      2. Plain prose pasted by the user:
         → hook = first sentence, opening = second sentence

    Both fields are best-effort. Empty strings are valid and just mean
    the history entry will be sparse.
    """
    text = (text or "").strip()
    if not text:
        return "", ""

    hook_match = re.search(r"hook\s*:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if hook_match:
        hook = hook_match.group(1).strip()
        build_match = re.search(r"build\s*:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        opening = ""
        if build_match:
            opening = build_match.group(1).strip().split(".")[0].strip()
        return hook, opening

    # Plain prose: split on sentence boundaries.
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    hook = sentences[0] if sentences else ""
    opening = sentences[1] if len(sentences) > 1 else ""
    return hook, opening


def _record_pipeline_history(config: dict) -> None:
    """Append the pipeline's input text to the per-preset story history.

    The pipeline accepts text from three sources:
      1. /story/generate output (already recorded by the story route — this
         call will dedup against the last entry and become a no-op)
      2. User-pasted prose (we record it here so the next Gemini call dodges it)
      3. Resumed projects (skipped — same text was recorded on the original run)

    All failures are swallowed so a history bug never breaks pipeline start.
    """
    try:
        if config.get("resume_from"):
            return  # original run already recorded this story

        hook, opening = _extract_hook_opening_from_text(config.get("text") or "")
        if not hook:
            return  # nothing useful to record

        from studio.story.history import append_history

        append_history(
            preset_style=config.get("style") or config.get("visual_style") or "default",
            category=config.get("category") or "default",
            language=config.get("language") or "english",
            hook=hook,
            opening=opening,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.debug("Could not record pipeline history: {}", e)


class PipelineStopped(RuntimeError):
    """Raised when a running pipeline is stopped by the user."""

    def __init__(self, step_name=None, message="Pipeline stopped by user"):
        super().__init__(message)
        self.step_name = step_name
        self.message = message


def _preflight_provider_check(config: dict, project_id: str) -> None:
    """Validate providers before pipeline runs. Raise if misconfigured.
    
    Phase 8: Validates TTS, storyboard, and animator providers.
    """
    from studio.shared.providers_common import settings_manager
    
    # Validate TTS provider
    tts_override = config.get("tts_provider_override")
    if tts_override:
        from studio.tts.providers import registry as tts_registry
        provider = tts_registry.get(tts_override)
        if provider is None:
            raise ValueError(f"TTS provider '{tts_override}' not found. Available: {tts_registry.list_ids()}")
        
        issues = provider.validate_settings(settings_manager.get_provider_settings("tts", tts_override))
        if any(i.severity == "error" for i in issues):
            errors = [f"{i.field}: {i.message}" for i in issues if i.severity == "error"]
            raise ValueError(f"TTS provider '{tts_override}' misconfigured: {errors}")
    
    # Validate storyboard provider
    sb_override = config.get("storyboard_provider_override")
    if sb_override:
        from studio.storyboard.providers import registry as sb_registry
        provider = sb_registry.get(sb_override)
        if provider is None:
            raise ValueError(f"Storyboard provider '{sb_override}' not found. Available: {sb_registry.list_ids()}")
        
        issues = provider.validate_settings(settings_manager.get_provider_settings("storyboard", sb_override))
        if any(i.severity == "error" for i in issues):
            errors = [f"{i.field}: {i.message}" for i in issues if i.severity == "error"]
            raise ValueError(f"Storyboard provider '{sb_override}' misconfigured: {errors}")
    
    # Validate animator provider
    anim_override = config.get("animator_provider_override")
    if anim_override:
        from studio.animator.providers import registry as anim_registry
        provider = anim_registry.get(anim_override)
        if provider is None:
            raise ValueError(f"Animator provider '{anim_override}' not found. Available: {anim_registry.list_ids()}")
        
        issues = provider.validate_settings(settings_manager.get_provider_settings("animator", anim_override))
        if any(i.severity == "error" for i in issues):
            errors = [f"{i.field}: {i.message}" for i in issues if i.severity == "error"]
            raise ValueError(f"Animator provider '{anim_override}' misconfigured: {errors}")
    
    logger.debug("[{}] Preflight provider check passed", project_id)


def _emit(job_id, event):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job:
        job["queue"].put(event)
        # Track per-step status for history
        step = event.get("step")
        status = event.get("status")
        if step and step not in ("done", "stopped") and status in ("running", "done", "skipped", "error", "stopped"):
            job.setdefault("step_statuses", {})[step] = status


def _stop_extensions():
    """Broadcast STOP_TYPING to both Grok and Gemini extensions via WebSocket."""
    stop_msg = {"type": "STOP_TYPING"}
    try:
        from studio.animator.routes import _broadcast as grok_broadcast
        grok_broadcast(stop_msg)
        logger.info("STOP_TYPING → Grok extension")
    except Exception as e:
        logger.debug("STOP_TYPING to Grok failed: {}", e)
    try:
        from studio.storyboard.gemini_ws import _ws_clients as gemini_clients, _ws_lock as gemini_lock
        import json as _json
        data = _json.dumps(stop_msg)
        with gemini_lock:
            for ws in list(gemini_clients):
                try:
                    ws.send(data)
                except Exception:
                    pass
        logger.info("STOP_TYPING → Gemini extension")
    except Exception as e:
        logger.debug("STOP_TYPING to Gemini failed: {}", e)


def _cleanup_old_jobs(max_age_s=600):
    now = time.time()
    with _jobs_lock:
        expired = [jid for jid, j in _jobs.items()
                   if now - j.get("created", 0) > max_age_s]
        for jid in expired:
            del _jobs[jid]


def _current_running_step(job):
    """Return the currently running step for a job, if any."""
    if not isinstance(job, dict):
        return None
    statuses = job.get("step_statuses", {}) or {}
    for step in job.get("step_sequence", ALL_PIPELINE_STEPS):
        if statuses.get(step) == "running":
            return step
    for step_name, status in statuses.items():
        if status == "running":
            return step_name
    return None


def _resume_step_for_job(job):
    """Return the step a stopped job should resume from."""
    if not isinstance(job, dict):
        return None
    running_step = _current_running_step(job)
    if running_step:
        return running_step

    statuses = job.get("step_statuses", {}) or {}
    for step in job.get("step_sequence", ALL_PIPELINE_STEPS):
        if statuses.get(step) not in ("done", "skipped"):
            return step
    return None


def _stop_requested(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return bool(job and job.get("stop_requested"))


def _raise_if_stop_requested(job_id, *, step_name=None):
    """Raise a PipelineStopped exception when the user has requested a stop."""
    if _stop_requested(job_id):
        raise PipelineStopped(step_name=step_name)


# ===================================================================
# Routes
# ===================================================================

@pipeline_bp.route("/api/pipeline/run", methods=["POST"])
@validate_json(PipelineRunRequest)
def run_pipeline(data: PipelineRunRequest):
    """Start the full pipeline.

    JSON body:
      - text (required): story text
      - voice: TTS voice (default af_heart)
      - speed: TTS speed 0.5–2.0 (default 1.0)
      - style: scene style (default cinematic)
      - segment_config: segmenter overrides
      - webhook_url: override n8n URL
    """
    _cleanup_old_jobs()
    resume_from = data.resume_from
    resume_project_id = data.resume_project_id
    # Reuse existing project ID when resuming, otherwise generate new
    project_id = resume_project_id if (resume_from and resume_project_id) else generate_project_id(prefix="pp")
    job_id = uuid.uuid4().hex[:12]
    stop_after = "timing" if data.stop_after == "alignment" else data.stop_after

    # Store the server port for internal API calls from background thread
    server_port = request.host.split(":")[-1] if ":" in request.host else "5050"
    os.environ["STS_PORT"] = server_port

    config = {
        "text": data.text.strip(),
        "language": data.language,
        "voice": data.voice,
        "speed": data.speed,
        "style": data.style,
        "niche_preset": data.niche_preset,
        "visual_style": data.visual_style,
        "story_tone": data.story_tone,
        "category": data.category,
        "style_prompt": data.custom_style_notes or data.style_prompt,
        "segment_config": data.segment_config,
        "webhook_url": data.webhook_url,
        "auto_scenes": data.auto_scenes,
        "auto_storyboard": data.auto_storyboard,
        "stop_after": stop_after,
        "project_id": project_id,
        "resume_from": resume_from,
        # Generic provider overrides (Phase 8)
        "tts_provider_override": data.tts_provider_override,
        "tts_provider_options": data.tts_provider_options,
        "storyboard_provider_override": data.storyboard_provider_override,
        "storyboard_provider_options": data.storyboard_provider_options,
        "animator_provider_override": data.animator_provider_override,
        "animator_provider_options": data.animator_provider_options,
        # Legacy fields (backward compat)
        "prompt_prefix": data.prompt_prefix,
        "aspect_ratio": data.aspect_ratio,
        "auto_type": data.auto_type,
        "tts_provider": data.tts_provider,
        "tts_voice": data.tts_voice,
        "provider": data.provider,
        "grok_mode": data.grok_mode,
        "grok_quality": data.grok_quality,
        "grok_duration": data.grok_duration,
    }

    from studio.niches.presets import resolve_niche as _resolve_niche
    resolved_niche = _resolve_niche(config)
    config["style"] = resolved_niche["visual_style"]
    config["visual_style"] = resolved_niche["visual_style"]
    config["story_tone"] = resolved_niche["story_tone"]
    config["category"] = resolved_niche["category"]
    config["niche"] = resolved_niche["niche"]
    config["voice"] = resolved_niche["voice"]
    config["speed"] = resolved_niche["speed"]
    # Auto-resolve Inworld voice from niche if not explicitly set
    if config.get("tts_provider") == "inworld" and not config.get("tts_voice"):
        config["tts_voice"] = resolved_niche.get("inworld_voice", "Dennis")

    # Record this story in the per-preset history so the next Gemini call
    # in the same preset combo can dodge its hook/opening. Runs after niche
    # resolution so we use the FINAL style+category, not the raw input.
    # Dedups against the most recent entry, so generate-then-pipeline of the
    # same story produces only one entry.
    _record_pipeline_history(config)

    # Compute which steps will run
    all_steps = ALL_PIPELINE_STEPS
    stop = config.get("stop_after")
    if stop and stop in all_steps:
        step_sequence = all_steps[:all_steps.index(stop) + 1]
    else:
        step_sequence = all_steps

    with _jobs_lock:
        _jobs[job_id] = {
            "queue": Queue(),
            "status": "running",
            "project_id": project_id,
            "config": config,
            "results": {},
            "step_sequence": step_sequence,
            "step_statuses": {},
            "stop_requested": False,
            "created": time.time(),
        }

    t = threading.Thread(target=_run_pipeline, args=(job_id,), daemon=True)
    t.start()

    return jsonify({"job_id": job_id, "project_id": project_id}), 202


@pipeline_bp.route("/api/pipeline/<job_id>/stop", methods=["POST"])
def stop_pipeline(job_id):
    """Request an active pipeline job to stop after the current interruptible point."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return jsonify({"error": "Unknown job ID"}), 404

        status = str(job.get("status") or "")
        if status == "stopped":
            return jsonify({
                "status": "stopped",
                "job_id": job_id,
                "project_id": job.get("project_id"),
                "resume_from": _resume_step_for_job(job),
            }), 200
        if status in ("done", "error"):
            return jsonify({
                "error": f"Cannot stop a pipeline with status '{status}'",
                "status": status,
            }), 409

        job["stop_requested"] = True
        job["stop_requested_at"] = time.time()
        current_step = _current_running_step(job)
        resume_from = _resume_step_for_job(job)
        project_id = job.get("project_id")

    logger.info("[{}] Stop requested for pipeline job {} at step {}",
                project_id, job_id, current_step or resume_from or "?")

    # Broadcast STOP_TYPING to both Grok and Gemini extensions
    _stop_extensions()

    return jsonify({
        "status": "stopping",
        "job_id": job_id,
        "project_id": project_id,
        "current_step": current_step,
        "resume_from": resume_from,
    }), 202


@pipeline_bp.route("/api/pipeline/progress/<job_id>")
def pipeline_progress(job_id):
    """SSE stream of pipeline progress events."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job ID"}), 404

    def stream():
        q = job["queue"]
        while True:
            try:
                event = q.get(timeout=300)
            except Exception:
                with _jobs_lock:
                    status = job.get("status")
                if status in ("done", "error", "stopped"):
                    yield f"data: {json.dumps({'step': status, 'status': status})}\n\n"
                    break
                continue
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("step") in ("done", "error", "stopped"):
                break

    return Response(
        stream(),
        mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


@pipeline_bp.route("/api/pipeline/jobs")
def list_jobs():
    """List recent pipeline jobs — reads from pipeline.json (primary) + scenes.json (fallback)."""
    items = []
    seen_ids = set()

    # ── Primary: read from output/pipeline/{id}/pipeline.json ──
    if os.path.isdir(PIPELINE_DIR):
        for entry in os.listdir(PIPELINE_DIR):
            pj_path = os.path.join(PIPELINE_DIR, entry, "pipeline.json")
            if not os.path.isfile(pj_path):
                continue
            try:
                data = safe_json_read(pj_path)
                cfg = data.get("config", {})
                pid = data.get("project_id", entry)
                seen_ids.add(pid)

                # Count scenes from scenes.json if available
                scene_count = 0
                scenes_path = os.path.join(SCENES_DIR, pid, "scenes.json")
                if os.path.isfile(scenes_path):
                    try:
                        sd = safe_json_read(scenes_path)
                        scene_count = len(sd.get("scenes", []))
                    except Exception:
                        pass

                items.append({
                    "project_id": pid,
                    "label": pid,
                    "status": data.get("status", "done"),
                    "text": cfg.get("text", ""),
                    "voice": cfg.get("voice", "af_heart"),
                    "speed": cfg.get("speed", 1.0),
                    "style": cfg.get("style", ""),
                    "niche_preset": cfg.get("niche_preset", ""),
                    "visual_style": cfg.get("visual_style", ""),
                    "story_tone": cfg.get("story_tone", ""),
                    "category": cfg.get("category", ""),
                    "niche": cfg.get("niche", ""),
                    "provider": cfg.get("provider", "grok"),
                    "stop_after": cfg.get("stop_after") or "",
                    "auto_scenes": cfg.get("auto_scenes", True),
                    "scene_count": scene_count,
                    "timestamp": data.get("timestamp", ""),
                    "created": os.path.getmtime(pj_path),
                    "pipeline_timing": data.get("step_timings", {}),
                    "step_statuses": data.get("step_statuses", {}),
                    "error": data.get("error"),
                    "error_step": data.get("error_step"),
                    "resume_from": data.get("resume_from"),
                    "stopped_step": data.get("stopped_step"),
                })
            except Exception:
                continue

    # ── Fallback: older pp_* projects without pipeline.json ──
    if os.path.isdir(SCENES_DIR):
        for entry in os.listdir(SCENES_DIR):
            if not entry.startswith("pp_") or entry in seen_ids:
                continue
            scenes_path = os.path.join(SCENES_DIR, entry, "scenes.json")
            if not os.path.isfile(scenes_path):
                continue
            try:
                mtime = os.path.getmtime(scenes_path)
                data = safe_json_read(scenes_path)
                scene_count = data.get("scene_count", len(data.get("scenes", [])))
                source = data.get("source_folder", "")
                item = {
                    "project_id": entry,
                    "label": entry,
                    "scene_count": scene_count,
                    "status": "done",
                    "created": mtime,
                    "timestamp": data.get("timestamp", ""),
                    "pipeline_timing": data.get("pipeline_timing", {}),
                    "step_statuses": {},
                    "error": None,
                    "error_step": None,
                    "resume_from": None,
                    "stopped_step": None,
                }
                if source:
                    tts_meta = os.path.join(TTS_DIR, source, "tts.json")
                    if os.path.isfile(tts_meta):
                        try:
                            meta = safe_json_read(tts_meta)
                            item["text"] = meta.get("prompt", "")
                            item["voice"] = meta.get("voice", "af_heart")
                            item["speed"] = meta.get("speed", 1.0)
                        except Exception:
                            pass
                item["style"] = data.get("style", "")
                items.append(item)
            except Exception:
                continue

    # ── In-progress jobs from memory ──
    with _jobs_lock:
        for jid, j in _jobs.items():
            pid = j.get("project_id", jid)
            if pid in seen_ids:
                continue
            cfg = j.get("config", {})
            items.append({
                "project_id": pid,
                "label": "Running..." if j.get("status") == "running" else pid,
                "status": j.get("status", "unknown"),
                "text": cfg.get("text", ""),
                "voice": cfg.get("voice", "af_heart"),
                "speed": cfg.get("speed", 1.0),
                "style": cfg.get("style", ""),
                "niche_preset": cfg.get("niche_preset", ""),
                "visual_style": cfg.get("visual_style", ""),
                "story_tone": cfg.get("story_tone", ""),
                "category": cfg.get("category", ""),
                "niche": cfg.get("niche", ""),
                "provider": cfg.get("provider", "grok"),
                "stop_after": cfg.get("stop_after") or "",
                "auto_scenes": cfg.get("auto_scenes", True),
                "scene_count": 0,
                "created": j.get("created", 0),
                "step_sequence": j.get("step_sequence", []),
                "step_statuses": j.get("step_statuses", {}),
                "error": None,
                "error_step": None,
                "resume_from": _resume_step_for_job(j) if j.get("status") == "stopped" else None,
                "stopped_step": _resume_step_for_job(j) if j.get("status") == "stopped" else None,
            })

    items.sort(key=lambda x: x.get("created", 0), reverse=True)
    return jsonify(items)


# ===================================================================
# Pipeline runner (background thread)
# ===================================================================

@pipeline_bp.route("/api/pipeline/<project_id>/regenerate-assets", methods=["POST"])
def regenerate_assets(project_id):
    """Re-run the asset grabber step for an existing pipeline project.

    Reads scenes.json, starts a new grabber job, and returns immediately.
    The frontend should open the provider tab and poll for status.
    """
    project_id = os.path.basename(project_id)
    scenes_path = os.path.join(SCENES_DIR, project_id, "scenes.json")
    if not os.path.isfile(scenes_path):
        return jsonify({"error": "No scenes found for this project"}), 404

    try:
        scenes_data = safe_json_read(scenes_path)
    except Exception as e:
        return jsonify({"error": f"Failed to read scenes: {e}"}), 500

    scenes = scenes_data.get("scenes", [])
    if not scenes:
        return jsonify({"error": "No scenes in project"}), 400

    # Read config from pipeline.json if available
    pj_path = os.path.join(PIPELINE_DIR, project_id, "pipeline.json")
    config = {}
    if os.path.isfile(pj_path):
        try:
            config = safe_json_read(pj_path).get("config", {})
        except Exception:
            pass

    body = request.get_json(silent=True) or {}
    provider = body.get("provider") or config.get("provider", "grok")
    aspect_ratio = body.get("aspect_ratio") or config.get("aspect_ratio", "9:16")

    # Build grabber payload
    server_port = request.host.split(":")[-1] if ":" in request.host else "5050"
    base_url = f"http://127.0.0.1:{server_port}"

    scenes_with_prompts = [
        {"prompt": s.get("image_prompt", ""), "scene": s.get("index", i)}
        for i, s in enumerate(scenes)
        if s.get("image_prompt")
    ]
    if not scenes_with_prompts:
        return jsonify({"error": "No scenes have image prompts to regenerate"}), 400

    payload = {
        "project_id": project_id,
        "provider": provider,
        "aspect_ratio": aspect_ratio,
        "auto_type": True,
        "scenes": scenes_with_prompts,
    }
    if provider == "grok":
        payload["grok_mode"] = body.get("grok_mode") or config.get("grok_mode", "video")
        payload["grok_quality"] = body.get("grok_quality") or config.get("grok_quality", "480p")
        payload["grok_duration"] = body.get("grok_duration") or config.get("grok_duration", "6s")

    try:
        resp = http_requests.post(f"{base_url}/api/animator/grabber/start",
                                  json=payload, timeout=30)
        resp.raise_for_status()
        grab_data = resp.json()
        logger.info("Regenerate assets started for {}", project_id)

        # Provider URLs for frontend to open
        provider_urls = {
            "grok": "https://grok.com/imagine",
            "midjourney": "https://www.midjourney.com/imagine",
            "meta-ai": "https://www.meta.ai/",
        }
        return jsonify({
            "status": "started",
            "project_id": project_id,
            "provider": provider,
            "scene_count": len(scenes),
            "open_url": provider_urls.get(provider, ""),
            **grab_data,
        })
    except Exception as e:
        logger.error("Failed to start asset regeneration: {}", e)
        return jsonify({"error": f"Failed to start grabber: {e}"}), 500


def _save_pipeline_timing(project_id, step_timings):
    """Persist pipeline_timing into the project's scenes.json."""
    scenes_path = os.path.join(SCENES_DIR, project_id, "scenes.json")
    if os.path.isfile(scenes_path):
        try:
            data = safe_json_read(scenes_path)
            data["pipeline_timing"] = step_timings
            safe_json_write(scenes_path, data, indent=2)
        except Exception as e:
            logger.debug("Could not save pipeline timing: {}", e)


def _pipeline_json_path(project_id):
    return os.path.join(PIPELINE_DIR, project_id, "pipeline.json")


def _save_pipeline_json(project_id, job_id, config, status, step_statuses,
                        step_timings, error_msg=None, error_step=None,
                        resume_from=None, stopped_step=None):
    """Persist full pipeline state to output/pipeline/{project_id}/pipeline.json."""
    data = {
        "project_id": project_id,
        "job_id": job_id,
        "status": status,
        "config": {
            "text": config.get("text", ""),
            "voice": config.get("voice", "af_heart"),
            "speed": config.get("speed", 1.0),
            "style": config.get("style", "cinematic"),
            "niche_preset": config.get("niche_preset"),
            "visual_style": config.get("visual_style"),
            "story_tone": config.get("story_tone"),
            "category": config.get("category"),
            "niche": config.get("niche"),
            "provider": config.get("provider", "grok"),
            "auto_scenes": config.get("auto_scenes", True),
            "auto_storyboard": config.get("auto_storyboard", True),
            "stop_after": config.get("stop_after") or None,
            "aspect_ratio": config.get("aspect_ratio", "9:16"),
            "grok_mode": config.get("grok_mode", "video"),
            "grok_quality": config.get("grok_quality", "480p"),
            "grok_duration": config.get("grok_duration", "6s"),
        },
        "step_statuses": dict(step_statuses),
        "step_timings": dict(step_timings),
        "error": error_msg,
        "error_step": error_step,
        "resume_from": resume_from,
        "resume_project_id": project_id if resume_from else None,
        "stopped_step": stopped_step,
        "timestamp": datetime.now().isoformat(),
    }
    try:
        safe_json_write(_pipeline_json_path(project_id), data, indent=2)
    except Exception as e:
        logger.debug("Could not save pipeline.json: {}", e)


def _emit_done(job_id, project_id, results):
    """Emit the 'done' event and mark the job as complete."""
    _emit(job_id, {
        "step": "done", "status": "done",
        "message": "Pipeline complete",
        "project_id": project_id,
        "summary": {
            "tts": {k: v for k, v in results.get("tts", {}).items() if k != "wav_path"} if "tts" in results else None,
            "timing": {
                "word_count": results["timing"]["word_count"],
                "inference_time": results["timing"]["inference_time"],
                "folder": results["timing"]["folder"],
            } if "timing" in results else None,
            "segment": results.get("segment"),
            "scenes": results.get("scenes"),
            "storyboard": results.get("storyboard"),
            "assets": results.get("assets"),
            "assemble": results.get("assemble"),
            "export": results.get("export"),
            "pipeline_timing": results.get("pipeline_timing"),
        },
    })
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job:
            job["status"] = "done"
            job["stop_requested"] = False


def _emit_stopped(job_id, project_id, config, step_timings, *, resume_from=None, message=None):
    """Persist and emit a stopped pipeline state."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        step_statuses = dict(job.get("step_statuses", {}))
        if resume_from:
            job["step_statuses"][resume_from] = "stopped"
            step_statuses[resume_from] = "stopped"
        job["status"] = "stopped"
        job["stop_requested"] = False

    _save_pipeline_json(
        project_id,
        job_id,
        config,
        "stopped",
        step_statuses,
        step_timings,
        resume_from=resume_from,
        stopped_step=resume_from,
    )
    if resume_from:
        _emit(job_id, {
            "step": resume_from,
            "status": "stopped",
            "message": f"[{project_id}] Paused before {resume_from}.",
            "project_id": project_id,
        })
    _emit(job_id, {
        "step": "stopped",
        "status": "stopped",
        "message": message or f"[{project_id}] Pipeline stopped",
        "project_id": project_id,
        "resume_from": resume_from,
        "stopped_step": resume_from,
    })


def _load_prior_results(project_id, up_to_step):
    """Load saved step results from disk for pipeline resume.

    Returns a dict of {step_name: result_data} for all steps before `up_to_step`.
    """
    all_steps = ALL_PIPELINE_STEPS
    idx = all_steps.index(up_to_step) if up_to_step in all_steps else 0
    steps_to_load = all_steps[:idx]
    loaded = {}

    for step in steps_to_load:
        if step == "tts":
            tts_path = os.path.join(TTS_DIR, project_id, "tts.json")
            if os.path.isfile(tts_path):
                data = safe_json_read(tts_path)
                wav_path = os.path.join(TTS_DIR, project_id, data.get("filename", "voice.wav"))
                data["wav_path"] = wav_path
                loaded["tts"] = data
        elif step == "timing":
            align_path = os.path.join(ALIGN_DIR, project_id, "alignment.json")
            if os.path.isfile(align_path):
                loaded["timing"] = safe_json_read(align_path)
        elif step == "segment":
            seg_path = os.path.join(SEGMENTER_DIR, project_id, "segmented.json")
            if os.path.isfile(seg_path):
                loaded["segment"] = safe_json_read(seg_path)
        elif step == "scenes":
            scenes_path = os.path.join(SCENES_DIR, project_id, "scenes.json")
            if os.path.isfile(scenes_path):
                loaded["scenes"] = safe_json_read(scenes_path)
        elif step == "storyboard":
            sb_path = os.path.join(STORYBOARD_DIR, project_id, "storyboard.json")
            if os.path.isfile(sb_path):
                loaded["storyboard"] = safe_json_read(sb_path)
        elif step == "assemble":
            project_dir = os.path.join(PROJECTS_DIR, project_id)
            project_candidates = (
                os.path.join(project_dir, "work@in@progress.json"),
                os.path.join(project_dir, "initial.json"),
            )
            for project_path in project_candidates:
                if not os.path.isfile(project_path):
                    continue
                data = safe_json_read(project_path)
                captions = data.get("captions") or {}
                caption_entries = captions.get("entries")
                if not isinstance(caption_entries, list):
                    caption_entries = captions.get("captions", [])
                loaded["assemble"] = {
                    "scene_count": data.get("scene_count", len(data.get("scenes", []))),
                    "total_duration": data.get("total_duration", 0),
                    "has_audio": bool(data.get("audio_tracks")),
                    "has_captions": bool(caption_entries),
                    "assembled_data": data,
                }
                break

    return loaded


def _run_pipeline(job_id):
    with _jobs_lock:
        job = _jobs[job_id]
        config = job["config"]
    project_id = config["project_id"]
    results = job["results"]
    step_timings = {}  # {step_name: duration_seconds}
    pipeline_start = time.perf_counter()

    stop_after = config.get("stop_after")
    step_seq = job.get("step_sequence", [])
    resume_from = config.get("resume_from")
    
    # Phase 8: Validate providers at preflight
    _preflight_provider_check(config, project_id)

    all_steps = ALL_PIPELINE_STEPS
    resume_idx = all_steps.index(resume_from) if resume_from in all_steps else 0

    # Load prior results from disk when resuming
    if resume_from and resume_idx > 0:
        logger.info("[{}] Resuming from step '{}' — loading prior results from disk",
                    project_id, resume_from)
        prior = _load_prior_results(project_id, resume_from)

        # Validate that required prior steps were loaded
        required_chain = {
            "timing": ["tts"],
            "segment": ["tts", "timing"],
            "scenes": ["tts", "timing", "segment"],
            "storyboard": ["tts", "timing", "segment", "scenes"],
            "assets": ["tts", "timing", "segment", "scenes"],
            "assemble": ["tts", "timing", "segment", "scenes"],
            "export": ["tts", "timing", "segment", "scenes", "assemble"],
        }
        missing = [s for s in required_chain.get(resume_from, []) if s not in prior]
        if missing:
            error_msg = (
                f"Cannot resume from '{resume_from}': missing prior data for "
                f"{', '.join(missing)}. Run the full pipeline first."
            )
            logger.error("[{}] {}", project_id, error_msg)
            _save_pipeline_json(project_id, job_id, config, "error",
                                {}, step_timings, error_msg=error_msg,
                                error_step=resume_from)
            _emit(job_id, {"step": "error", "status": "error",
                           "message": f"[{project_id}] {error_msg}",
                           "error_step": resume_from})
            with _jobs_lock:
                job["status"] = "error"
            return

        results.update(prior)
        # Emit skipped status for prior steps
        for step_name in all_steps[:resume_idx]:
            if step_name in prior:
                _emit(job_id, {"step": step_name, "status": "done",
                               "message": f"[{project_id}] (reused from previous run)"})
            else:
                _emit(job_id, {"step": step_name, "status": "skipped",
                               "message": f"[{project_id}] (no prior data found)"})

    def _should_skip(step_name):
        """Return True if this step should be skipped during resume."""
        if not resume_from:
            return False
        return all_steps.index(step_name) < resume_idx

    logger.info("[{}] Pipeline started | steps={} stop_after={} resume_from={} provider={} voice={} speed={} style={}",
                project_id, step_seq, stop_after, resume_from or 'none', provider,
                config.get("voice"), config.get("speed"), config.get("style"))

    try:
        # ── Step 1: TTS ─────────────────────────────────────────────
        _raise_if_stop_requested(job_id, step_name="tts")
        if _should_skip("tts"):
            tts_result = results.get("tts", {})
        else:
            logger.info("[{}] Step 1/8: TTS starting", project_id)
            _emit(job_id, {"step": "tts", "status": "running",
                           "message": f"[{project_id}] Generating audio..."})
            _t0 = time.perf_counter()
            tts_result = _step_tts(config, project_id)
            step_timings["tts"] = round(time.perf_counter() - _t0, 2)
            results["tts"] = tts_result
            logger.success("[{}] Step 1/8: TTS done — {:.1f}s audio, {} words",
                           project_id, tts_result["duration_seconds"], tts_result["words"])
            _emit(job_id, {
                "step": "tts", "status": "done",
                "message": f"[{project_id}] {tts_result['duration_seconds']:.1f}s audio, "
                           f"{tts_result['words']} words",
                "data": {k: v for k, v in tts_result.items() if k != "wav_path"},
            })
        if stop_after == "tts":
            logger.info("[{}] Pipeline stopped after TTS (stop_after=tts)", project_id)
            step_timings["total"] = round(time.perf_counter() - pipeline_start, 2)
            _save_pipeline_json(project_id, job_id, config, "done",
                                job.get("step_statuses", {}), step_timings)
            _emit_done(job_id, project_id, results)
            return

        # ── Step 2: Force Alignment ─────────────────────────────────
        _raise_if_stop_requested(job_id, step_name="timing")
        if _should_skip("timing"):
            timing_result = results.get("timing", {})
        else:
            logger.info("[{}] Step 2/8: Alignment starting", project_id)
            _emit(job_id, {"step": "timing", "status": "running",
                           "message": f"[{project_id}] Aligning words..."})
            _t0 = time.perf_counter()
            timing_result = _step_timing(tts_result, config, project_id)
            step_timings["timing"] = round(time.perf_counter() - _t0, 2)
            results["timing"] = timing_result
            logger.success("[{}] Step 2/8: Alignment done — {} words in {:.2f}s",
                           project_id, timing_result["word_count"], timing_result["inference_time"])
            _emit(job_id, {
                "step": "timing", "status": "done",
                "message": f"[{project_id}] {timing_result['word_count']} words aligned "
                           f"in {timing_result['inference_time']:.2f}s",
            })
        if stop_after == "timing":
            logger.info("[{}] Pipeline stopped after Alignment (stop_after=timing)", project_id)
            step_timings["total"] = round(time.perf_counter() - pipeline_start, 2)
            _save_pipeline_json(project_id, job_id, config, "done",
                                job.get("step_statuses", {}), step_timings)
            _emit_done(job_id, project_id, results)
            return

        # ── Step 3: Segmentation ────────────────────────────────────
        _raise_if_stop_requested(job_id, step_name="segment")
        if _should_skip("segment"):
            segment_result = results.get("segment", {})
        else:
            logger.info("[{}] Step 3/8: Segment starting", project_id)
            _emit(job_id, {"step": "segment", "status": "running",
                           "message": f"[{project_id}] Splitting into scenes..."})
            _t0 = time.perf_counter()
            segment_result = _step_segment(timing_result, config, project_id)
            step_timings["segment"] = round(time.perf_counter() - _t0, 2)
            results["segment"] = segment_result
            stats = segment_result.get("stats", {})
            logger.success("[{}] Step 3/8: Segment done — {} scenes, avg {:.1f}s",
                           project_id, stats.get("segment_count", 0), stats.get("avg_duration", 0))
            _emit(job_id, {
                "step": "segment", "status": "done",
                "message": f"[{project_id}] {stats.get('segment_count', 0)} scenes, "
                           f"avg {stats.get('avg_duration', 0):.1f}s",
            })
        if stop_after == "segment":
            logger.info("[{}] Pipeline stopped after Segment (stop_after=segment)", project_id)
            step_timings["total"] = round(time.perf_counter() - pipeline_start, 2)
            _save_pipeline_json(project_id, job_id, config, "done",
                                job.get("step_statuses", {}), step_timings)
            _emit_done(job_id, project_id, results)
            return

        # ── Step 4: Scene Generation (webhook) — optional ────────────
        _raise_if_stop_requested(job_id, step_name="scenes")
        if _should_skip("scenes"):
            scenes_result = results.get("scenes", {})
        elif config.get("auto_scenes", True):
            logger.info("[{}] Step 4/8: Scenes starting (webhook)", project_id)
            _emit(job_id, {"step": "scenes", "status": "running",
                           "message": f"[{project_id}] Generating scene scripts..."})
            _t0 = time.perf_counter()
            scenes_result = _step_scenes(segment_result, config, project_id, job_id)
            step_timings["scenes"] = round(time.perf_counter() - _t0, 2)
            results["scenes"] = scenes_result
            scene_count = len(scenes_result.get("scenes", []))
            logger.success("[{}] Step 4/8: Scenes done — {} scenes generated",
                           project_id, scene_count)
            _emit(job_id, {
                "step": "scenes", "status": "done",
                "message": f"[{project_id}] {scene_count} scenes generated",
                "data": scenes_result,
            })
        else:
            logger.info("[{}] Step 4/8: Scenes skipped (auto_scenes=false)", project_id)
            _emit(job_id, {
                "step": "scenes", "status": "skipped",
                "message": f"[{project_id}] Scene generation skipped",
            })

        if stop_after == "scenes":
            logger.info("[{}] Pipeline stopped after Scenes (stop_after=scenes)", project_id)
            step_timings["total"] = round(time.perf_counter() - pipeline_start, 2)
            _save_pipeline_json(project_id, job_id, config, "done",
                                job.get("step_statuses", {}), step_timings)
            _emit_done(job_id, project_id, results)
            return

        # ── Step 5: Storyboard (reference images) ─────────────────
        _raise_if_stop_requested(job_id, step_name="storyboard")
        if _should_skip("storyboard"):
            storyboard_result = results.get("storyboard", {})
        elif config.get("auto_storyboard", True):
            logger.info("[{}] Step 5/8: Storyboard starting | provider={}", project_id, storyboard_provider)
            storyboard_emit = {
                "step": "storyboard", "status": "running",
                "message": f"[{project_id}] Generating reference images...",
            }
            if storyboard_provider == "gemini":
                storyboard_emit["open_url"] = "https://gemini.google.com/app"
            _emit(job_id, storyboard_emit)
            _t0 = time.perf_counter()
            storyboard_result = _step_storyboard(results.get("scenes", {}), config, project_id, job_id)
            step_timings["storyboard"] = round(time.perf_counter() - _t0, 2)
            results["storyboard"] = storyboard_result
            logger.success("[{}] Step 5/8: Storyboard done — {}/{} images",
                           project_id, storyboard_result.get("ready", 0),
                           storyboard_result.get("total", 0))
            _emit(job_id, {
                "step": "storyboard", "status": "done",
                "message": f"[{project_id}] {storyboard_result.get('ready', 0)}/{storyboard_result.get('total', 0)} reference images ready",
            })
        else:
            logger.info("[{}] Step 5/8: Storyboard skipped (auto_storyboard=false)", project_id)
            _emit(job_id, {
                "step": "storyboard", "status": "skipped",
                "message": f"[{project_id}] Storyboard generation skipped",
            })

        if stop_after == "storyboard":
            logger.info("[{}] Pipeline stopped after Storyboard (stop_after=storyboard)", project_id)
            step_timings["total"] = round(time.perf_counter() - pipeline_start, 2)
            _save_pipeline_json(project_id, job_id, config, "done",
                                job.get("step_statuses", {}), step_timings)
            _emit_done(job_id, project_id, results)
            return

        # ── Step 6: Asset Grabber (Grok videos) ──────────────────
        _raise_if_stop_requested(job_id, step_name="assets")
        if _should_skip("assets"):
            assets_result = results.get("assets", {})
        else:
            provider_urls = {
                "grok": "https://grok.com/imagine",
                "midjourney": "https://www.midjourney.com/imagine",
                "meta-ai": "https://www.meta.ai/",
            }
            logger.info("[{}] Step 6/8: Assets starting | provider={}", project_id, provider)
            _emit(job_id, {
                "step": "assets", "status": "running",
                "message": f"[{project_id}] Starting asset grabber ({provider})...",
                "open_url": provider_urls.get(provider, ""),
            })
            _t0 = time.perf_counter()
            assets_result = _step_assets(results.get("scenes", {}), config, project_id, job_id)
            step_timings["assets"] = round(time.perf_counter() - _t0, 2)
            results["assets"] = assets_result
            logger.success("[{}] Step 6/8: Assets done — {}/{} ready, {} errors",
                           project_id, assets_result.get("ready", 0),
                           assets_result.get("total", 0), assets_result.get("errors", 0))
            _emit(job_id, {
                "step": "assets", "status": "done",
                "message": f"[{project_id}] {assets_result.get('ready', 0)}/{assets_result.get('total', 0)} assets ready",
            })
        if stop_after == "assets":
            logger.info("[{}] Pipeline stopped after Assets (stop_after=assets)", project_id)
            step_timings["total"] = round(time.perf_counter() - pipeline_start, 2)
            _save_pipeline_json(project_id, job_id, config, "done",
                                job.get("step_statuses", {}), step_timings)
            _emit_done(job_id, project_id, results)
            return

        # ── Step 6: Assemble Project ──────────────────────────────
        _raise_if_stop_requested(job_id, step_name="assemble")
        if _should_skip("assemble"):
            assemble_result = results.get("assemble", {})
        else:
            logger.info("[{}] Step 7/8: Assemble starting", project_id)
            _emit(job_id, {"step": "assemble", "status": "running",
                           "message": f"[{project_id}] Assembling project..."})
            _t0 = time.perf_counter()
            assemble_result = _step_assemble(project_id)
            step_timings["assemble"] = round(time.perf_counter() - _t0, 2)
            results["assemble"] = assemble_result
            logger.success("[{}] Step 7/8: Assemble done — {} scenes, {:.1f}s, audio={}, captions={}",
                           project_id, assemble_result.get("scene_count", 0),
                           assemble_result.get("total_duration", 0),
                           assemble_result.get("has_audio", False),
                           assemble_result.get("has_captions", False))
            _emit(job_id, {
                "step": "assemble", "status": "done",
                "message": f"[{project_id}] {assemble_result.get('scene_count', 0)} scenes assembled",
            })
        if stop_after == "assemble":
            logger.info("[{}] Pipeline stopped after Assemble (stop_after=assemble)", project_id)
            step_timings["total"] = round(time.perf_counter() - pipeline_start, 2)
            _save_pipeline_json(project_id, job_id, config, "done",
                                job.get("step_statuses", {}), step_timings)
            _emit_done(job_id, project_id, results)
            return

        # ── Step 7: Export Video ──────────────────────────────────
        _raise_if_stop_requested(job_id, step_name="export")
        logger.info("[{}] Step 8/8: Export starting", project_id)
        _emit(job_id, {"step": "export", "status": "running",
                       "message": f"[{project_id}] Exporting video..."})
        _t0 = time.perf_counter()
        export_result = _step_export(assemble_result, project_id, job_id,
                                            story_tone=config.get("story_tone"))
        step_timings["export"] = round(time.perf_counter() - _t0, 2)
        results["export"] = export_result
        logger.success("[{}] Step 8/8: Export done — {} ({})",
                       project_id, export_result.get("filename", "?"),
                       export_result.get("resolution", "?"))
        _emit(job_id, {
            "step": "export", "status": "done",
            "message": f"[{project_id}] Exported {export_result.get('filename', 'video')}",
        })

        # ── Auto-sync to folder ──────────────────────────────────────
        try:
            _auto_sync_export(project_id, export_result, job_id)
        except Exception as e:
            logger.warning("[{}] Auto-sync failed: {}", project_id, e)

        # ── Done ────────────────────────────────────────────────────
        step_timings["total"] = round(time.perf_counter() - pipeline_start, 2)
        results["pipeline_timing"] = step_timings

        # Persist timing to scenes.json sidecar
        _save_pipeline_timing(project_id, step_timings)

        # Persist pipeline.json
        _save_pipeline_json(project_id, job_id, config, "done",
                            job.get("step_statuses", {}), step_timings)

        logger.success("[{}] Pipeline COMPLETE — all {} steps finished in {:.1f}s",
                       project_id, len(step_seq), step_timings["total"])
        _emit_done(job_id, project_id, results)

        with _jobs_lock:
            job["status"] = "done"

    except PipelineStopped as e:
        resume_step = e.step_name or _resume_step_for_job(job)
        step_timings["total"] = round(time.perf_counter() - pipeline_start, 2)
        results["pipeline_timing"] = step_timings
        _save_pipeline_timing(project_id, step_timings)
        logger.info("[{}] Pipeline STOPPED by user{}", project_id,
                    f" at step '{resume_step}'" if resume_step else "")
        _emit_stopped(
            job_id,
            project_id,
            config,
            step_timings,
            resume_from=resume_step,
            message=(
                f"[{project_id}] Pipeline stopped. "
                + (f"Resume from {resume_step} when ready." if resume_step else "Ready to resume.")
            ),
        )

    except Exception as e:
        # Find which step failed (the one still marked "running")
        error_step = None
        step_statuses = job.get("step_statuses", {})
        for sname, sval in step_statuses.items():
            if sval == "running":
                error_step = sname
                break
        # Update the failed step status to "error" before saving
        if error_step:
            step_statuses[error_step] = "error"

        logger.error("[{}] Pipeline FAILED at step '{}': {}", project_id,
                     error_step or "unknown", e)
        logger.exception("Pipeline traceback")

        # Persist pipeline.json with error state
        _save_pipeline_json(project_id, job_id, config, "error",
                            step_statuses, step_timings,
                            error_msg=str(e), error_step=error_step)
        _emit(job_id, {"step": "error", "status": "error",
                       "message": f"[{project_id}] {e}",
                       "error_step": error_step})
        with _jobs_lock:
            job["status"] = "error"
            job["stop_requested"] = False


# ===================================================================
# Step implementations
# ===================================================================

def _step_tts(config, project_id):
    """Generate TTS audio and return metadata dict (includes wav_path).

    Uses provider registry to resolve provider, load settings, and dispatch.
    Resolution order:
      1. config.provider_override if set
      2. settings.json → domains.tts.selected_provider
      3. default: kokoro
    """
    from studio.tts.routes import _tts_job_dir
    from studio.tts.normalize import clean_for_tts
    from studio.tts.audio import run_loudnorm
    from studio.tts.providers import registry as tts_registry
    from studio.shared.providers_common import settings_manager, redact_settings

    text = config["text"]
    voice = config.get("voice") or "af_bella"
    speed = float(config.get("speed", 1.0))
    
    provider_override = config.get("tts_provider_override")
    if provider_override:
        provider_id = provider_override
    else:
        tts_domain = settings_manager.get_domain_settings("tts")
        provider_id = tts_domain.get("selected_provider", "kokoro")

    provider = tts_registry.get(provider_id)
    if provider is None:
        raise ValueError(f"TTS provider '{provider_id}' not found. Available: {tts_registry.list_ids()}")

    provider_settings = settings_manager.get_provider_settings("tts", provider_id)
    merged_settings = {**provider_settings, **config.get("tts_provider_options", {})}

    job_dir = _tts_job_dir(project_id)
    os.makedirs(job_dir, exist_ok=True)
    wav_path = os.path.join(job_dir, "voice.wav")

    if provider_id == "inworld":
        return _step_tts_inworld_pipeline(
            config, project_id, text, voice, speed, job_dir, wav_path,
            provider_id, provider_version=provider.version, provider_settings=merged_settings
        )

    return _step_tts_kokoro_pipeline(
        config, project_id, text, voice, speed, job_dir, wav_path,
        provider_id, provider_version=provider.version, provider_settings=merged_settings
    )


def _step_tts_inworld_pipeline(config, project_id, text, voice, speed, job_dir, wav_path,
                               provider_id, provider_version, provider_settings):
    """Pipeline TTS via Inworld cloud API."""
    from studio.tts.inworld import synthesize_to_wav
    from studio.tts.normalize import clean_for_tts
    from studio.tts.audio import run_loudnorm
    from studio.shared.providers_common import settings_manager

    tts_prompt = clean_for_tts(text)

    result = synthesize_to_wav(
        text=tts_prompt,
        wav_path=wav_path,
        voice_id=voice,
        speed=speed,
    )
    run_loudnorm(wav_path)

    clean_prompt = re.sub(r'[\[\]]', '', text).strip()
    metadata = {
        "filename": "voice.wav",
        "folder": project_id,
        "prompt": clean_prompt,
        "model": result["model_id"],
        "model_id": provider_id,
        "provider": provider_id,
        "voice": voice,
        "project_id": project_id,
        "visual_style": config.get("visual_style"),
        "story_tone": config.get("story_tone"),
        "category": config.get("category"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "inference_time": result["inference_time"],
        "rtf": round(result["inference_time"] / result["duration_seconds"], 4) if result["duration_seconds"] > 0 else 0,
        "duration_seconds": result["duration_seconds"],
        "sample_rate": result["sample_rate"],
        "speed": speed,
        "words": len(clean_prompt.split()),
        "approx_tokens": int(len(clean_prompt.split()) * 1.3),
        "wav_path": wav_path,
        "cache_hit": False,
        "characters_billed": result["characters"],
    }

    settings = settings_manager.load_settings()
    metadata["job_meta"] = {
        "provider_id": provider_id,
        "provider_version": provider_version,
        "provider_kind": provider.kind if provider else "unknown",
        "resolved_settings_redacted": settings_manager.redact_settings(provider_settings),
        "provider_options": config.get("tts_provider_options", {}),
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "settings_version": settings.get("version", 1),
    }

    safe_json_write(
        os.path.join(job_dir, "tts.json"),
        {k: v for k, v in metadata.items() if k != "wav_path"},
        indent=2,
    )
    return metadata


def _step_tts_kokoro_pipeline(config, project_id, text, voice, speed, job_dir, wav_path,
                              provider_id, provider_version, provider_settings):
    """Pipeline TTS via local Kokoro ONNX with caching."""
    from studio.tts.routes import (
        load_model, _voice_to_lang, _phonemize_with_misaki,
        generation_inference_lock,
        _cache_key, _cache_path,
    )
    from studio.tts.normalize import clean_for_tts
    from studio.tts.audio import pad_audio, run_loudnorm
    from studio.shared.providers_common import settings_manager
    import shutil

    cache_hit = False
    cache_key = _cache_key(text, voice, speed)
    cached_wav = _cache_path(cache_key)

    if os.path.isfile(cached_wav):
        try:
            info = sf.info(cached_wav)
            if info.duration >= 0.5:
                shutil.copy2(cached_wav, wav_path)
                run_loudnorm(wav_path)
                cache_hit = True
                logger.success(
                    "Pipeline TTS: cache hit ({}) — {:.1f}s audio, 0s inference",
                    cache_key, info.duration,
                )
        except Exception:
            logger.opt(exception=True).debug("Cache read failed, regenerating")

    total_inference = 0.0
    if not cache_hit:
        kokoro = load_model()
        lang = _voice_to_lang(voice)
        tts_prompt = clean_for_tts(text)
        phonemes, is_ph = _phonemize_with_misaki(tts_prompt, lang)

        start = time.perf_counter()
        with generation_inference_lock:
            audio, _sr = kokoro.create(
                text=phonemes, voice=voice, speed=speed,
                lang=lang, is_phonemes=is_ph,
            )
        total_inference = time.perf_counter() - start
        audio = pad_audio(audio, sample_rate=24000)
        sf.write(wav_path, audio, 24000)
        run_loudnorm(wav_path)

        try:
            shutil.copy2(wav_path, cached_wav)
            logger.debug("Cached pipeline TTS → {}", cache_key)
        except Exception:
            pass

        logger.success("Pipeline TTS: {:.1f}s audio in {:.2f}s",
                       sf.info(wav_path).duration, total_inference)

    info = sf.info(wav_path)
    duration = info.duration
    rtf = total_inference / duration if duration > 0 else 0
    clean_prompt = re.sub(r'[\[\]]', '', text).strip()

    metadata = {
        "filename": "voice.wav",
        "folder": project_id,
        "prompt": clean_prompt,
        "model": "kokoro-v1.0",
        "model_id": provider_id,
        "provider": provider_id,
        "voice": voice,
        "project_id": project_id,
        "visual_style": config.get("visual_style"),
        "story_tone": config.get("story_tone"),
        "category": config.get("category"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "inference_time": round(total_inference, 3),
        "rtf": round(rtf, 4),
        "duration_seconds": round(duration, 2),
        "sample_rate": 24000,
        "speed": speed,
        "words": len(clean_prompt.split()),
        "approx_tokens": int(len(clean_prompt.split()) * 1.3),
        "wav_path": wav_path,
        "cache_hit": cache_hit,
    }

    settings = settings_manager.load_settings()
    metadata["job_meta"] = {
        "provider_id": provider_id,
        "provider_version": provider_version,
        "provider_kind": provider.kind if provider else "unknown",
        "resolved_settings_redacted": settings_manager.redact_settings(provider_settings),
        "provider_options": config.get("tts_provider_options", {}),
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "settings_version": settings.get("version", 1),
    }

    safe_json_write(
        os.path.join(job_dir, "tts.json"),
        {k: v for k, v in metadata.items() if k != "wav_path"},
        indent=2,
    )

    return metadata


def _step_timing(tts_result, config, project_id):
    """Run force alignment on TTS output."""
    from studio.timing.routes import _run_alignment

    wav_path = tts_result["wav_path"]
    clean_text = re.sub(r'[\[\]*_#`~]', '', config["text"]).strip()
    clean_text = re.sub(r'\s+', ' ', clean_text)

    start = time.perf_counter()
    alignment = _run_alignment(wav_path, clean_text)
    elapsed = time.perf_counter() - start

    if not alignment:
        raise RuntimeError("Alignment produced no results")

    # Save to alignment directory
    folder_name = tts_result["folder"]
    align_dir = os.path.join(ALIGN_DIR, folder_name)
    os.makedirs(align_dir, exist_ok=True)

    dest_audio = os.path.join(align_dir, tts_result["filename"])
    if not os.path.exists(dest_audio):
        shutil.copy2(wav_path, dest_audio)

    result_data = {
        "project_id": project_id,
        "source_file": tts_result["filename"],
        "folder": folder_name,
        "transcript": clean_text,
        "alignment": alignment,
        "word_count": len(alignment),
        "inference_time": round(elapsed, 3),
        "timestamp": datetime.now().isoformat(),
    }

    safe_json_write(os.path.join(align_dir, "alignment.json"), result_data, indent=2)

    logger.success("Pipeline Alignment: {} words in {:.2f}s",
                   len(alignment), elapsed)
    return result_data


def _step_segment(timing_result, config, project_id):
    """Run segmentation on alignment data."""
    from studio.timing.segmenter import run_segmenter, save_output

    metadata = {
        "project_id": project_id,
        "source_folder": timing_result.get("folder", ""),
        "style": config.get("style", ""),
        "transcript": timing_result.get("transcript", ""),
    }

    seg_config = config.get("segment_config")

    result = run_segmenter(
        timing_result["alignment"],
        seg_config,
        metadata,
    )

    folder = project_id or f"{timing_result.get('folder', 'pipeline')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_path = os.path.join(SEGMENTER_DIR, folder, "segmented.json")
    save_output(result, out_path)
    result["output_folder"] = folder
    result["output_path"] = out_path

    logger.success("Pipeline Segment: {} scenes",
                   result["stats"]["segment_count"])
    return result


# ── Hook animation tone subgroups (mirrors frontend TONE_HOOK_GROUP) ──
_TONE_HOOK_GROUP = {
    "suspenseful":   ["tension_flicker", "shadow_pulse", "creep_reveal"],
    "dramatic":      ["dramatic_slam", "power_drop", "storm_shake", "force_expand"],
    "epic":          ["movie_title", "epic_rise", "legend_zoom"],
    "comedic":       ["bouncy_pop", "cartoon_slide", "gag_drop"],
    "inspirational": ["uplift_rise", "dawn_glow", "horizon_fade"],
    "educational":   ["teach_type", "chalk_slide", "focus_pop"],
    "horror":        ["dread_shake", "nightmare_glitch", "void_fade"],
    "wholesome":     ["warm_glow", "gentle_wave", "dawn_glow"],
    "romantic":      ["heart_rise", "warm_glow", "gentle_wave"],
    "nostalgic":     ["memory_drift", "echo_blur", "wistful_fade"],
    "melancholic":   ["wistful_fade", "memory_drift", "echo_blur"],
    "meditative":    ["zen_breathe", "gentle_wave", "thought_fade"],
    "philosophical": ["thought_fade", "stoic_reveal", "horizon_fade"],
    "stoic":         ["stoic_reveal", "thought_fade", "force_expand"],
    "motivational":  ["neon_pulse", "rally_slam", "uplift_rise"],
    "urgent":        ["rush_slide", "alarm_flicker", "shadow_pulse"],
    "dark":          ["dark_glitch", "nightmare_glitch", "void_fade"],
    "mysterious":    ["cipher_blur", "creep_reveal", "echo_blur"],
    "cinematic":     ["story_reveal", "movie_title", "epic_rise"],
}
_ALL_HOOKS = ["dramatic_slam", "movie_title", "uplift_rise", "bouncy_pop", "teach_type"]


def _assign_hook_animations(result, story_tone):
    """Assign a random hook animation to each text scene from the tone's subgroup."""
    import random
    scenes = result.get("scenes", [])
    text_scenes = [s for s in scenes if str(s.get("type_of_scene", "")).lower() == "text"]
    if not text_scenes:
        return

    pool = list(_TONE_HOOK_GROUP.get(story_tone, _ALL_HOOKS))
    if not pool:
        pool = list(_ALL_HOOKS)

    random.shuffle(pool)
    for i, scene in enumerate(text_scenes):
        hook = pool[i % len(pool)]
        scene["text_hook_animation"] = hook
        logger.debug("Assigned hook animation '{}' to text scene {}", hook, scene.get("index", i))


def _step_scenes(segment_result, config, project_id, job_id=None):
    """Generate scene scripts via webhook (with chapter support)."""
    from studio.build_scene_blueprints.chapters import (
        should_use_chapters,
    )
    from studio.build_scene_blueprints.prompts import build_scene_system_prompt
    from studio.build_scene_blueprints.style_compiler import resolve_template_bundle
    from studio.build_scene_blueprints.planner import (
        build_scene_blueprints,
        build_visual_bible,
        summarize_blueprints,
    )
    from studio.build_scene_blueprints.validators import ensure_analysis_payload, finalize_scene_result
    from studio.build_scene_blueprints.routes import (
        _call_webhook, generate_with_chapters_chunked,
        _apply_segmenter_timing, _normalize_webhook_response,
    )
    from studio.build_scene_blueprints.templates import TEMPLATES_BY_ID

    all_segments = segment_result.get("segments", [])
    segments = [
        {"index": i, "words": s["words"]}
        for i, s in enumerate(s for s in all_segments if not s.get("is_filler"))
    ]

    if not segments:
        raise RuntimeError("No non-filler segments to generate scenes for")

    webhook_url = config.get("webhook_url") or N8N_WEBHOOK_URL
    script = config.get("text", "")
    custom_style_notes = config.get("style_prompt", "") or ""
    # Resolve visual_style via niche system (falls back to legacy "style" field)
    from studio.niches.presets import resolve_niche as _resolve_niche
    _resolved = _resolve_niche(config)
    style_id = _resolved["visual_style"]
    bundle = resolve_template_bundle(style_id, TEMPLATES_BY_ID, custom_style_notes)
    planning_segments = [
        {**s, "index": i}
        for i, s in enumerate(s for s in all_segments if not s.get("is_filler"))
    ]
    visual_bible = build_visual_bible(script, planning_segments, bundle["style_spec"])
    scene_blueprints = build_scene_blueprints(
        planning_segments,
        visual_bible,
        bundle["style_spec"],
    )
    plan_summary = summarize_blueprints(scene_blueprints)

    # ── Chapter-based or single request ──
    if should_use_chapters(all_segments):
        def _progress(msg):
            if job_id:
                _emit(job_id, {"step": "scenes", "status": "running", "message": msg})

        result = generate_with_chapters_chunked(
            script=script,
            style_id=style_id,
            style_spec=bundle["style_spec"],
            style_prompt=bundle["style_prompt"],
            visual_bible=visual_bible,
            scene_blueprints=scene_blueprints,
            plan_summary=plan_summary,
            full_segments=all_segments,
            webhook_url=webhook_url,
            progress_cb=_progress if job_id else None,
            custom_style_notes=custom_style_notes,
        )
    else:
        # Single request (small script)
        system_prompt = build_scene_system_prompt(
            bundle["style_spec"],
            visual_bible,
            scene_blueprints,
            plan_summary=plan_summary,
            custom_style_notes=custom_style_notes,
        )
        payload = {
            "script": script,
            "style": style_id,
            "style_prompt": bundle["style_prompt"],
            "system_prompt": system_prompt,
            "segments": segments,
            "style_spec": bundle["style_spec"],
            "visual_bible": visual_bible,
            "scene_blueprints": scene_blueprints,
            "plan_summary": plan_summary,
        }
        result = _call_webhook(webhook_url, payload)

    # Apply segmenter timing — single source of truth for scene placement
    result = _normalize_webhook_response(result)
    speech_segments = [
        {**s, "index": i}
        for i, s in enumerate(s for s in all_segments if not s.get("is_filler"))
    ]
    _apply_segmenter_timing(result, speech_segments, all_segments)
    ensure_analysis_payload(result, visual_bible, bundle["style_spec"], bundle["template"])
    result["style_spec"] = bundle["style_spec"]
    result["style_prompt"] = bundle["style_prompt"]
    result["scene_blueprints"] = scene_blueprints
    if custom_style_notes:
        result["custom_style_notes"] = custom_style_notes
    finalize_scene_result(result, scene_blueprints, visual_bible)

    # Assign hook animations to text scenes based on story tone
    _assign_hook_animations(result, config.get("story_tone", ""))

    # Save result
    result["project_id"] = project_id
    result["timestamp"] = datetime.now().isoformat()
    result["source_folder"] = segment_result.get(
        "metadata", {}).get("source_folder", "")
    result["style"] = style_id

    safe_json_write(os.path.join(SCENES_DIR, project_id, "scenes.json"), result, indent=2)

    logger.success("Pipeline Scenes: {} scenes",
                   len(result.get("scenes", [])))
    return result


def _step_storyboard(scenes_result, config, project_id, job_id):
    """Step 5: Generate one reference image per scene via n8n webhook."""
    scenes = scenes_result.get("scenes", [])
    if not scenes:
        raise RuntimeError("No scenes to generate storyboard images for")

    scenes_payload = [
        {"scene": s.get("index", i), "prompt": s.get("image_prompt", "")}
        for i, s in enumerate(scenes)
        if s.get("image_prompt")
    ]
    if not scenes_payload:
        raise RuntimeError("No scenes have image prompts for storyboard")

    aspect_ratio = config.get("aspect_ratio", "9:16")

    # Start storyboard generation via internal API
    base_url = f"http://127.0.0.1:{os.environ.get('STS_PORT', '5050')}"
    if _stop_requested(job_id):
        raise PipelineStopped(step_name="storyboard")

    # Resolve provider: override → settings → default
    sb_override = config.get("storyboard_provider_override")
    sb_options = config.get("storyboard_provider_options", {})
    
    # Map new IDs to legacy names for backward compat
    id_to_legacy = {"gemini_ws": "gemini", "wavespeed_webhook": "webhook", "wavespeed_direct": "direct"}
    sb_provider = id_to_legacy.get(sb_override) if sb_override else config.get("storyboard_provider", "webhook")
    prompt_prefix = config.get("prompt_prefix", "") if sb_provider == "gemini" else ""
    if prompt_prefix:
        for sp in scenes_payload:
            sp["prompt"] = prompt_prefix + sp["prompt"]

    payload = {
        "project_id": project_id,
        "scenes": scenes_payload,
        "aspect_ratio": aspect_ratio,
        "style": config.get("style"),
        "image_model": config.get("image_model"),
        "provider": sb_provider,
        "auto_type": config.get("auto_type", True),
    }
    resp = http_requests.post(f"{base_url}/api/storyboard/generate",
                              json=payload, timeout=30)
    resp.raise_for_status()
    logger.info("Pipeline Storyboard: generation started for {}", project_id)

    # Poll until all scenes are ready (timeout 30 minutes)
    max_wait = 30 * 60
    poll_interval = 10
    start_time = time.time()
    prev_ready = 0  # Track ready count to detect new completions

    while time.time() - start_time < max_wait:
        if _stop_requested(job_id):
            raise PipelineStopped(step_name="storyboard")
        time.sleep(poll_interval)
        if _stop_requested(job_id):
            raise PipelineStopped(step_name="storyboard")
        try:
            status_resp = http_requests.get(
                f"{base_url}/api/storyboard/status/{project_id}", timeout=10)
            if status_resp.status_code != 200:
                continue
            status_data = status_resp.json()

            total = status_data.get("total", 0)
            ready = status_data.get("ready", 0)
            errors = status_data.get("errors", 0)
            pending = total - ready - errors

            # Include scene-level status details from extension
            scene_statuses = status_data.get("scene_statuses", {})
            scene_details = []
            for sk, sv in sorted(scene_statuses.items()):
                if sk == "-1":
                    continue
                ss = sv.get("status", "pending")
                if ss not in ("ready", "done"):
                    scene_details.append(f"s{sk}:{ss}")
            detail_str = f" [{', '.join(scene_details)}]" if scene_details else ""

            _emit(job_id, {
                "step": "storyboard", "status": "running",
                "message": f"Generating storyboard ({project_id})... {ready}/{total} images ready"
                           + (f", {errors} errors" if errors else "")
                           + detail_str,
                "scene_ready": ready,
                "scene_total": total,
                "scene_new": ready > prev_ready,
            })
            prev_ready = ready

            if status_data.get("status") == "done" or pending == 0:
                logger.success("Pipeline Storyboard: {}/{} ready, {} errors",
                               ready, total, errors)
                return {
                    "total": total, "ready": ready, "errors": errors,
                    "scene_statuses": status_data.get("scene_statuses", {}),
                }
        except Exception as e:
            logger.debug("Pipeline Storyboard poll error: {}", e)

    raise RuntimeError(f"Storyboard generation timed out after {max_wait // 60} minutes")


def _step_assets(scenes_result, config, project_id, job_id):
    """Step 6: Start asset grabber and poll until all scenes are ready."""
    from studio.animator.animation_routes import grabber_start, _get_job, _set_job
    from studio.animator.schemas import GrabberStartRequest

    scenes = scenes_result.get("scenes", [])
    if not scenes:
        raise RuntimeError("No scenes to grab assets for")

    # Resolve provider: override → settings → default
    anim_override = config.get("animator_provider_override")
    anim_options = config.get("animator_provider_options", {})
    
    # Map new IDs to legacy names for backward compat
    id_to_legacy = {"grok_automa": "grok", "kie_ai": "kie-ai"}
    provider = id_to_legacy.get(anim_override) if anim_override else config.get("provider", "grok")
    
    aspect_ratio = config.get("aspect_ratio", "9:16")
    auto_type = config.get("auto_type", True)

    payload = {
        "project_id": project_id,
        "provider_override": anim_override,
        "provider_options": anim_options,
        "arguments": config.get("arguments", ""),
        "aspect_ratio": aspect_ratio,
        "auto_type": auto_type,
        "scenes": [
            {"prompt": s.get("image_prompt", ""), "scene": s.get("index", i)}
            for i, s in enumerate(scenes)
            if s.get("image_prompt")
        ],
    }
    # Add provider-specific options from new format or legacy
    if anim_override == "grok_automa" or provider == "grok":
        payload["grok_mode"] = anim_options.get("mode", config.get("grok_mode", "video"))
        payload["grok_quality"] = anim_options.get("quality", config.get("grok_quality", "480p"))
        payload["grok_duration"] = anim_options.get("duration", config.get("grok_duration", "6s"))

    # Start grabber via internal API call
    base_url = f"http://127.0.0.1:{os.environ.get('STS_PORT', '5050')}"
    if _stop_requested(job_id):
        raise PipelineStopped(step_name="assets")
    resp = http_requests.post(f"{base_url}/api/animator/grabber/start",
                              json=payload, timeout=30)
    resp.raise_for_status()
    grab_data = resp.json()
    logger.info("Pipeline Assets: grabber started for {}", project_id)

    # Open provider URL
    provider_urls = {
        "grok": "https://grok.com/imagine",
        "midjourney": "https://www.midjourney.com/imagine",
        "meta-ai": "https://www.meta.ai/",
    }

    # Poll until all scenes are ready (timeout 2 hours)
    max_wait = 2 * 60 * 60  # 2 hours
    poll_interval = 10  # seconds
    start_time = time.time()
    prev_ready = 0  # Track ready count to detect new completions

    while time.time() - start_time < max_wait:
        if _stop_requested(job_id):
            raise PipelineStopped(step_name="assets")
        time.sleep(poll_interval)
        if _stop_requested(job_id):
            raise PipelineStopped(step_name="assets")
        try:
            status_resp = http_requests.get(
                f"{base_url}/api/animator/grabber/status/{project_id}", timeout=10)
            if status_resp.status_code != 200:
                continue
            status_data = status_resp.json()

            scene_statuses = status_data.get("scene_statuses", {})
            total = len(scene_statuses)
            ready = sum(1 for s in scene_statuses.values() if s.get("status") == "ready")
            errors = sum(1 for s in scene_statuses.values() if s.get("status") == "error")
            pending = total - ready - errors

            # Emit with scene_ready/scene_total so frontend can play per-video sounds
            _emit(job_id, {
                "step": "assets", "status": "running",
                "message": f"Waiting for assets ({project_id})... {ready}/{total} ready"
                           + (f", {errors} errors" if errors else ""),
                "scene_ready": ready,
                "scene_total": total,
                "scene_new": ready > prev_ready,
            })
            prev_ready = ready

            if status_data.get("status") in ("done", "completed") or pending == 0:
                logger.success("Pipeline Assets: {}/{} ready, {} errors",
                               ready, total, errors)
                return {
                    "total": total, "ready": ready, "errors": errors,
                    "provider": provider,
                    "provider_url": provider_urls.get(provider, ""),
                }
        except Exception as e:
            logger.debug("Pipeline Assets poll error: {}", e)

    raise RuntimeError(f"Asset grabber timed out after {max_wait // 60} minutes")


def _step_assemble(project_id):
    """Step 6: Assemble project for the editor."""
    base_url = f"http://127.0.0.1:{os.environ.get('STS_PORT', '5050')}"
    resp = http_requests.post(
        f"{base_url}/api/projects/{project_id}/assemble?force=1",
        timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    logger.success("Pipeline Assemble: {} scenes, {}s duration",
                   data.get("scene_count", 0),
                   data.get("total_duration", 0))
    return {
        "scene_count": data.get("scene_count", 0),
        "total_duration": data.get("total_duration", 0),
        "has_audio": bool(data.get("audio_tracks")),
        "has_captions": bool((data.get("captions") or {}).get("captions")),
        "assembled_data": data,
    }


def _normalize_export_audio(assembled):
    """Normalize assembled editor audio data into export audio config."""
    audio = assembled.get("audio")
    if isinstance(audio, dict):
        audio_path = audio.get("path") or audio.get("url") or ""
        if audio_path:
            normalized = dict(audio)
            normalized["path"] = audio_path
            return normalized

    disabled_tracks = set(assembled.get("disabled_tracks") or [])
    usable_tracks = []
    for track in assembled.get("audio_tracks") or []:
        if not isinstance(track, dict):
            continue
        if track.get("muted"):
            continue
        track_id = track.get("id")
        if track_id and track_id in disabled_tracks:
            continue

        track_path = track.get("path") or track.get("url") or ""
        if not track_path:
            continue

        usable_tracks.append(track)

    for track in usable_tracks:
        if (track.get("type") or "").lower() != "voice":
            continue
        return {
            "path": track.get("path") or track.get("url") or "",
            "volume": track.get("volume", 1.0),
            "start_offset": track.get("startOffset", track.get("start_offset", 0)),
            "timeline_offset": track.get("timelineOffset", track.get("timeline_offset", 0)),
            "trimmed_duration": track.get("trimmedDuration", track.get("trimmed_duration")),
            "fade_in": track.get("fadeIn", track.get("fade_in", 0)),
            "fade_out": track.get("fadeOut", track.get("fade_out", 0.5)),
        }

    for track in usable_tracks:
        return {
            "path": track.get("path") or track.get("url") or "",
            "volume": track.get("volume", 1.0),
            "start_offset": track.get("startOffset", track.get("start_offset", 0)),
            "timeline_offset": track.get("timelineOffset", track.get("timeline_offset", 0)),
            "trimmed_duration": track.get("trimmedDuration", track.get("trimmed_duration")),
            "fade_in": track.get("fadeIn", track.get("fade_in", 0)),
            "fade_out": track.get("fadeOut", track.get("fade_out", 0.5)),
        }

    return None


def _extract_music_track(assembled):
    """Pull the first non-muted/non-disabled music track out of audio_tracks."""
    if not isinstance(assembled, dict):
        return None
    disabled_tracks = set(assembled.get("disabled_tracks") or [])
    for track in assembled.get("audio_tracks") or []:
        if not isinstance(track, dict):
            continue
        if (track.get("type") or "").lower() != "music":
            continue
        if track.get("muted"):
            continue
        if track.get("id") and track.get("id") in disabled_tracks:
            continue
        track_path = track.get("path") or track.get("url") or ""
        if not track_path:
            continue
        return {
            "path": track_path,
            "volume": track.get("volume", 0.15),
            "fade_in": track.get("fadeIn", track.get("fade_in", 2.0)),
            "fade_out": track.get("fadeOut", track.get("fade_out", 3.0)),
            "loop": track.get("loop", True),
            "ducking_enabled": track.get("duckingEnabled", track.get("ducking_enabled", True)),
            "ducking_level": track.get("duckingLevel", track.get("ducking_level", 0.20)),
        }
    return None


def _extract_sfx_track(assembled):
    """Pull the first non-muted/non-disabled SFX track out of audio_tracks.

    Returns a dict shaped like a bgMusic entry (path/volume/loop/fades/ducking)
    so the renderer can mix it as a second auxiliary audio layer. Returns
    None when no usable SFX track exists.
    """
    if not isinstance(assembled, dict):
        return None
    disabled_tracks = set(assembled.get("disabled_tracks") or [])
    for track in assembled.get("audio_tracks") or []:
        if not isinstance(track, dict):
            continue
        if (track.get("type") or "").lower() != "sfx":
            continue
        if track.get("muted"):
            continue
        if track.get("id") and track.get("id") in disabled_tracks:
            continue
        track_path = track.get("path") or track.get("url") or ""
        if not track_path:
            continue
        return {
            "path": track_path,
            "volume": track.get("volume", 0.10),
            "fade_in": track.get("fadeIn", track.get("fade_in", 1.5)),
            "fade_out": track.get("fadeOut", track.get("fade_out", 2.0)),
            "loop": track.get("loop", True),
            "ducking_enabled": track.get("duckingEnabled", track.get("ducking_enabled", True)),
            "ducking_level": track.get("duckingLevel", track.get("ducking_level", 0.20)),
        }
    return None


def _builtin_audio_abs_to_url(bucket: str, abs_path: str) -> str | None:
    """Convert a built-in audio file under APP_ASSETS_DIR into a /assets URL."""
    if bucket not in {"music", "sfx"} or not abs_path:
        return None
    try:
        normalized = os.path.normpath(abs_path)
        assets_root = os.path.normpath(APP_ASSETS_DIR)
        if os.path.commonpath([normalized, assets_root]) != assets_root:
            return None
    except ValueError:
        return None
    rel = os.path.relpath(normalized, assets_root).replace("\\", "/")
    return f"/assets/{rel}"


def _persist_auto_selected_export_audio(project_id: str, *, bg_music=None, sfx=None) -> None:
    """Persist fallback export picks into project JSON so editor/export stay aligned."""
    if not project_id:
        return

    track_specs = []
    if isinstance(bg_music, dict) and bg_music.get("path"):
        music_path = bg_music.get("path")
        music_url = _builtin_audio_abs_to_url("music", music_path)
        if music_path and music_url:
            track_specs.append({
                "id": "at_music_export",
                "label": "Music",
                "type": "music",
                "file": os.path.basename(music_path),
                "path": music_url,
                "duration": 0,
                "timelineOffset": 0,
                "startOffset": 0,
                "trimmedDuration": None,
                "volume": bg_music.get("volume", 0.15),
                "loop": bg_music.get("loop", True),
                "muted": False,
                "duckingEnabled": bg_music.get("ducking_enabled", True),
                "duckingLevel": bg_music.get("ducking_level", 0.20),
                "fadeIn": bg_music.get("fade_in", 2.0),
                "fadeOut": bg_music.get("fade_out", 3.0),
            })

    if isinstance(sfx, dict) and sfx.get("path"):
        sfx_path = sfx.get("path")
        sfx_url = _builtin_audio_abs_to_url("sfx", sfx_path)
        if sfx_path and sfx_url:
            track_specs.append({
                "id": "at_sfx_export",
                "label": "SFX",
                "type": "sfx",
                "file": os.path.basename(sfx_path),
                "path": sfx_url,
                "duration": 0,
                "timelineOffset": 0,
                "startOffset": 0,
                "trimmedDuration": None,
                "volume": sfx.get("volume", 0.10),
                "loop": sfx.get("loop", True),
                "muted": False,
                "duckingEnabled": sfx.get("ducking_enabled", True),
                "duckingLevel": sfx.get("ducking_level", 0.20),
                "fadeIn": sfx.get("fade_in", 1.5),
                "fadeOut": sfx.get("fade_out", 2.0),
            })

    if not track_specs:
        return

    for filename in ("initial.json", "work@in@progress.json"):
        project_path = os.path.join(PROJECTS_DIR, project_id, filename)
        if not os.path.isfile(project_path):
            continue
        try:
            data = safe_json_read(project_path) or {}
        except Exception as error:
            logger.debug("Could not read {} for export audio persist: {}", project_path, error)
            continue
        if not isinstance(data, dict):
            continue

        existing_tracks = data.get("audio_tracks")
        if not isinstance(existing_tracks, list):
            existing_tracks = []

        kept_tracks = []
        for track in existing_tracks:
            if not isinstance(track, dict):
                kept_tracks.append(track)
                continue
            track_type = str(track.get("type") or "").lower()
            if track_type in {"music", "sfx"}:
                continue
            kept_tracks.append(track)

        data["audio_tracks"] = kept_tracks + [dict(spec) for spec in track_specs]
        safe_json_write(project_path, data, indent=2)


def _normalize_export_captions(assembled):
    """Normalize editor caption payload into export caption payload."""
    captions = assembled.get("captions")
    if not isinstance(captions, dict):
        return None

    entries = captions.get("entries")
    if not isinstance(entries, list):
        entries = captions.get("captions")
    if not isinstance(entries, list) or not entries:
        return None

    normalized = dict(captions)
    normalized["entries"] = entries
    return normalized


def _step_export(assemble_result, project_id, job_id, *, story_tone=None):
    """Step 7: Export video with default profile."""
    # Read export profile from settings
    from config import APP_CONFIG_PATH
    settings = {}
    if os.path.isfile(APP_CONFIG_PATH):
        try:
            settings = safe_json_read(APP_CONFIG_PATH) or {}
        except Exception:
            pass

    profile = settings.get("sts-export-profile", "yt_shorts")
    captions_enabled = settings.get("sts-export-captions", True)
    grain_enabled = settings.get("sts-export-grain", False)

    PROFILES = {
        "yt_shorts": {"width": 1080, "height": 1920, "ratio": "9:16"},
        "tiktok":    {"width": 1080, "height": 1920, "ratio": "9:16"},
        "reels":     {"width": 1080, "height": 1920, "ratio": "9:16"},
        "yt_landscape": {"width": 1920, "height": 1080, "ratio": "16:9"},
        "square":    {"width": 1080, "height": 1080, "ratio": "1:1"},
    }
    res = PROFILES.get(profile, PROFILES["yt_shorts"])

    assembled = assemble_result.get("assembled_data", {})
    raw_scenes = assembled.get("scenes", [])
    if not raw_scenes:
        raise RuntimeError("No scenes to export")

    # Transform assembled scenes to export format (media.path, media.type)
    export_scenes = []
    for s in raw_scenes:
        media_path = s.get("mediaUrl") or s.get("image_url") or ""
        is_video = s.get("isVideo", False) or media_path.endswith((".mp4", ".webm", ".mov"))
        export_scene = {
            "id": s.get("id", s.get("scene_id", 0)),
            "duration": s.get("duration", 3),
            "media": {
                "path": media_path,
                "type": "video" if is_video else "image",
            },
            "effect": s.get("effect", {"type": "none"}),
            "transition": s.get("transition", {"type": "none", "duration": 0}),
            "text_overlay": {
                "content": s.get("text_content") or "",
                "duration": s.get("text_overlay_duration", s.get("duration", 3)),
            } if s.get("text_content") and s.get("type") == "text" else None,
        }
        export_scenes.append(export_scene)
        logger.debug("  Export scene {}: media={} type={}",
                      export_scene["id"], media_path[:60] if media_path else "NONE",
                      export_scene["media"]["type"])

    total_duration = assembled.get("total_duration") or assemble_result.get("total_duration") or sum(
        float(s.get("duration", 0) or 0) for s in raw_scenes
    )
    # Auto-select background music if none was manually chosen.
    # Note: the assemble step already persists this to initial.json
    # audio_tracks; this is just a fallback for runs that bypass assemble
    # (e.g. legacy or partial pipelines).
    music_history = list(assembled.get("music_history") or [])
    sfx_history = list(assembled.get("sfx_history") or [])
    if (not music_history or not sfx_history) and project_id:
        from studio.music.selector import load_project_audio_history
        persisted_audio_history = load_project_audio_history(project_id)
        if not music_history:
            music_history = list(persisted_audio_history.get("music_history") or [])
        if not sfx_history:
            sfx_history = list(persisted_audio_history.get("sfx_history") or [])

    bg_music = assembled.get("bgMusic") or _extract_music_track(assembled)
    used_auto_bg_music = False
    if not bg_music:
        from studio.music.selector import persist_project_audio_history, recall_last_music, select_music
        bg_music = recall_last_music(music_history)
        if not bg_music and story_tone:
            bg_music = select_music(story_tone, history=music_history)
        if bg_music:
            used_auto_bg_music = True
        if bg_music and bg_music.get("history") is not None:
            music_history = list(bg_music.get("history") or music_history)
            persist_project_audio_history(project_id, music_history=music_history)
            bg_music.pop("history", None)
            logger.info("Pipeline Export: auto-selected bgMusic for tone '{}' → '{}'",
                        story_tone, os.path.basename(bg_music["path"]))

    # Extract auto-SFX from the assembled timeline. Same fallback chain as
    # bgMusic: prefer the track persisted in audio_tracks (set by assemble),
    # otherwise pick a fresh one from the SFX library. SFX is optional —
    # if neither path produces a track, it's silently skipped.
    sfx = _extract_sfx_track(assembled)
    used_auto_sfx = False
    if not sfx:
        from studio.music.selector import persist_project_audio_history, recall_last_sfx, select_sfx
        picked = recall_last_sfx(sfx_history)
        if not picked and story_tone:
            picked = select_sfx(story_tone, history=sfx_history)
        if picked:
            used_auto_sfx = True
            sfx = {
                "path": picked["path"],
                "volume": picked.get("volume", 0.10),
                "fade_in": picked.get("fade_in", 1.5),
                "fade_out": picked.get("fade_out", 2.0),
                "loop": picked.get("loop", True),
                "ducking_enabled": picked.get("ducking_enabled", True),
                "ducking_level": picked.get("ducking_level", 0.20),
            }
            if picked.get("history") is not None:
                sfx_history = list(picked.get("history") or sfx_history)
                persist_project_audio_history(project_id, sfx_history=sfx_history)
            logger.info("Pipeline Export: auto-selected SFX for tone '{}' → '{}'",
                        story_tone, os.path.basename(picked["path"]))

    if project_id and (used_auto_bg_music or used_auto_sfx):
        _persist_auto_selected_export_audio(
            project_id,
            bg_music=bg_music if used_auto_bg_music else None,
            sfx=sfx if used_auto_sfx else None,
        )

    export_payload = {
        "project_id": project_id,
        "scenes": export_scenes,
        "output": {
            "resolution": {"width": res["width"], "height": res["height"]},
            "fps": 30,
            "quality": "high",
        },
        "timeline": {"total_duration": total_duration},
        "captions": _normalize_export_captions(assembled) if captions_enabled else None,
        "audio": _normalize_export_audio(assembled),
        "bgMusic": bg_music,
        "sfx": sfx,
        "grain_overlay": assembled.get("grain_overlay") if grain_enabled else None,
    }

    base_url = f"http://127.0.0.1:{os.environ.get('STS_PORT', '5050')}"

    # Start export
    resp = http_requests.post(f"{base_url}/api/export",
                              json=export_payload, timeout=30)
    resp.raise_for_status()
    export_data = resp.json()
    export_job_id = export_data.get("job_id", "")

    if not export_job_id:
        raise RuntimeError("Export did not return a job ID")

    def _cancel_export_job():
        try:
            http_requests.delete(f"{base_url}/api/export/{export_job_id}", timeout=10)
        except Exception as cancel_err:
            logger.debug("Pipeline Export cancel request failed: {}", cancel_err)

    # Poll export progress
    max_wait = 15 * 60  # 15 minutes
    start_time = time.time()

    while time.time() - start_time < max_wait:
        if _stop_requested(job_id):
            _cancel_export_job()
            raise PipelineStopped(step_name="export")
        time.sleep(3)
        if _stop_requested(job_id):
            _cancel_export_job()
            raise PipelineStopped(step_name="export")
        try:
            status_resp = http_requests.get(
                f"{base_url}/api/export/{export_job_id}/status", timeout=10)
            if status_resp.status_code != 200:
                continue
            status = status_resp.json()

            progress = status.get("progress", 0)
            message = status.get("message", "")
            export_status = str(status.get("status", "")).lower()
            _emit(job_id, {
                "step": "export", "status": "running",
                "message": f"[{project_id}] Exporting... {progress}% — {message}",
            })

            if export_status in ("done", "completed"):
                return {
                    "filename": status.get("output_filename", ""),
                    "profile": profile,
                    "resolution": f"{res['width']}x{res['height']}",
                }
            if export_status in ("failed", "error", "cancelled"):
                raise RuntimeError(status.get("error", "Export failed"))
        except http_requests.RequestException as e:
            logger.debug("Pipeline Export poll error: {}", e)

    raise RuntimeError("Export timed out")


def _auto_sync_export(project_id, export_result, job_id):
    """Auto-sync exported video to configured sync folder if enabled."""
    from config import APP_CONFIG_PATH, EXPORT_DIR

    cfg = safe_json_read(APP_CONFIG_PATH) or {}
    defaults = cfg.get("defaults", {})
    user = cfg.get("user", {})

    auto_sync = user.get("sts-auto-sync", defaults.get("sts-auto-sync", False))
    if not auto_sync:
        return

    sync_folder = (user.get("sts-sync-folder") or defaults.get("sts-sync-folder") or "").strip()
    if not sync_folder:
        return

    sync_folder = os.path.normpath(sync_folder)
    if not os.path.isdir(sync_folder):
        logger.warning("[{}] Auto-sync skipped — folder missing: {}", project_id, sync_folder)
        return

    dest_dir = os.path.join(sync_folder, "exports")
    os.makedirs(dest_dir, exist_ok=True)

    filename = export_result.get("filename", "")
    if not filename:
        return

    # Find the exported file in EXPORT_DIR
    src_path = None
    for root, _dirs, files in os.walk(EXPORT_DIR):
        if filename in files:
            src_path = os.path.join(root, filename)
            break

    if not src_path or not os.path.isfile(src_path):
        logger.warning("[{}] Auto-sync skipped — file not found: {}", project_id, filename)
        return

    dest_path = os.path.join(dest_dir, filename)

    # Skip if already exists with same size
    if os.path.isfile(dest_path) and os.path.getsize(dest_path) == os.path.getsize(src_path):
        logger.info("[{}] Auto-sync: {} already up to date", project_id, filename)
        return

    import shutil
    shutil.copy2(src_path, dest_path)
    logger.success("[{}] Auto-synced: {} → {}", project_id, filename, dest_dir)

    _emit(job_id, {
        "step": "export", "status": "done",
        "message": f"[{project_id}] Synced {filename} to folder",
    })
