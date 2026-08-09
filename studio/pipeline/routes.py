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
from datetime import datetime, timezone
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
from studio.pipeline import services as _pipeline_services
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


PipelineStopped = _pipeline_services.PipelineStopped


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


def _provider_open_url(domain: str, provider: str) -> str | None:
    """The URL a provider asks the operator to open, from its manifest (§20.1).

    Resolves aliases, so a legacy `gemini` / `webhook` value works as well as a
    canonical ID. Returns `None` when the provider declares no URL.
    """
    if not provider:
        return None
    from studio.shared.providers_common.hub import hub

    instance = hub.get(domain, provider)
    return instance.manifest.open_url if instance is not None else None


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
        # Flat keys for any provider that consumes them; unknown keys are ignored.
        "grok_mode": body.get("grok_mode") or config.get("grok_mode", "video"),
        "grok_quality": body.get("grok_quality") or config.get("grok_quality", "480p"),
        "grok_duration": body.get("grok_duration") or config.get("grok_duration", "6s"),
    }

    try:
        resp = http_requests.post(f"{base_url}/api/animator/grabber/start",
                                  json=payload, timeout=30)
        resp.raise_for_status()
        grab_data = resp.json()
        logger.info("Regenerate assets started for {}", project_id)

        # open_url lives on the provider manifest (§20.1), not a route literal.
        open_url = ""
        resolved = grab_data.get("provider") or provider
        try:
            from studio.shared.providers_common.hub import hub
            instance = hub.get("animator", resolved)
            if instance is not None and getattr(instance, "manifest", None):
                open_url = getattr(instance.manifest, "open_url", "") or ""
        except Exception:
            open_url = ""
        return jsonify({
            "status": "started",
            "project_id": project_id,
            "provider": resolved,
            "scene_count": len(scenes),
            "open_url": open_url,
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
    provider = config.get("provider", "grok")
    storyboard_provider = (
        config.get("storyboard_provider_override")
        or config.get("storyboard_provider")
        or ""
    )

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
            # The URL a provider wants opened is its manifest's `open_url`
            # (§20.1), not a literal keyed on one provider ID (step 14.2).
            open_url = _provider_open_url("storyboard", storyboard_provider)
            if open_url:
                storyboard_emit["open_url"] = open_url
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
# Step service wrappers
# ===================================================================

def _step_tts(config, project_id):
    return _pipeline_services._step_tts(config, project_id)


def _step_tts_inworld_pipeline(config, project_id, text, voice, speed, job_dir, wav_path,
                               provider_id, provider_version, provider_kind, provider_settings):
    return _pipeline_services._step_tts_inworld_pipeline(
        config, project_id, text, voice, speed, job_dir, wav_path,
        provider_id, provider_version, provider_kind, provider_settings,
    )


def _step_tts_kokoro_pipeline(config, project_id, text, voice, speed, job_dir, wav_path,
                              provider_id, provider_version, provider_kind, provider_settings):
    return _pipeline_services._step_tts_kokoro_pipeline(
        config, project_id, text, voice, speed, job_dir, wav_path,
        provider_id, provider_version, provider_kind, provider_settings,
    )


def _step_timing(tts_result, config, project_id):
    return _pipeline_services._step_timing(tts_result, config, project_id)


def _step_segment(timing_result, config, project_id):
    return _pipeline_services._step_segment(timing_result, config, project_id)


def _step_scenes(segment_result, config, project_id, job_id=None):
    return _pipeline_services._step_scenes(segment_result, config, project_id, job_id)


def _step_storyboard(scenes_result, config, project_id, job_id):
    return _pipeline_services._step_storyboard(scenes_result, config, project_id, job_id)


def _step_assets(scenes_result, config, project_id, job_id):
    return _pipeline_services._step_assets(scenes_result, config, project_id, job_id)


def _step_assemble(project_id):
    return _pipeline_services._step_assemble(project_id)


def _step_export(assemble_result, project_id, job_id, *, story_tone=None):
    return _pipeline_services._step_export(
        assemble_result, project_id, job_id, story_tone=story_tone,
    )


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
