"""Pipeline Module — Orchestrates the full TTS → Timing → Segment → Scenes pipeline.

Provides:
  POST /api/pipeline/run          — start a pipeline job (returns job_id + project_id)
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
    TTS_DIR, ALIGN_DIR, SEGMENTER_DIR, SCENES_DIR, ASSETS_DIR, EXPORT_DIR,
    N8N_WEBHOOK_URL, generate_project_id,
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


def _emit(job_id, event):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job:
        job["queue"].put(event)
        # Track per-step status for history
        step = event.get("step")
        status = event.get("status")
        if step and step != "done" and status in ("running", "done", "skipped", "error"):
            job.setdefault("step_statuses", {})[step] = status


def _cleanup_old_jobs(max_age_s=600):
    now = time.time()
    with _jobs_lock:
        expired = [jid for jid, j in _jobs.items()
                   if now - j.get("created", 0) > max_age_s]
        for jid in expired:
            del _jobs[jid]


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
    project_id = generate_project_id(prefix="pp")
    job_id = uuid.uuid4().hex[:12]

    # Store the server port for internal API calls from background thread
    server_port = request.host.split(":")[-1] if ":" in request.host else "5050"
    os.environ["STS_PORT"] = server_port

    config = {
        "text": data.text.strip(),
        "voice": data.voice,
        "speed": data.speed,
        "style": data.style,
        "segment_config": data.segment_config,
        "webhook_url": data.webhook_url,
        "auto_scenes": data.auto_scenes,
        "stop_after": data.stop_after,
        "project_id": project_id,
        # Asset grabber options
        "provider": data.provider,
        "aspect_ratio": data.aspect_ratio,
        "auto_type": data.auto_type,
        "grok_mode": data.grok_mode,
        "grok_quality": data.grok_quality,
        "grok_duration": data.grok_duration,
    }

    # Compute which steps will run
    all_steps = ["tts", "timing", "segment", "scenes", "assets", "assemble", "export"]
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
            "created": time.time(),
        }

    t = threading.Thread(target=_run_pipeline, args=(job_id,), daemon=True)
    t.start()

    return jsonify({"job_id": job_id, "project_id": project_id}), 202


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
                if status in ("done", "error"):
                    yield f"data: {json.dumps({'step': status, 'status': status})}\n\n"
                    break
                continue
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("step") in ("done", "error"):
                break

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


@pipeline_bp.route("/api/pipeline/jobs")
def list_jobs():
    """List recent pipeline jobs from disk (pp_* folders in scenes dir)."""
    items = []
    if os.path.isdir(SCENES_DIR):
        for entry in os.listdir(SCENES_DIR):
            if not entry.startswith("pp_"):
                continue
            scenes_path = os.path.join(SCENES_DIR, entry, "scenes.json")
            if not os.path.isfile(scenes_path):
                continue
            try:
                mtime = os.path.getmtime(scenes_path)
                with open(scenes_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                scene_count = data.get("scene_count", len(data.get("scenes", [])))
                source = data.get("source_folder", "")
                # extract human-readable part from project ID (pp_EA9W1W_my-cool-project)
                parts = entry.split("_", 2)
                label = parts[2].replace("-", " ") if len(parts) > 2 else entry
                item = {
                    "project_id": entry,
                    "label": label[:40],
                    "scene_count": scene_count,
                    "status": "done",
                    "created": mtime,
                    "timestamp": data.get("timestamp", ""),
                }
                # Look up original text, voice, speed from TTS metadata
                if source:
                    tts_meta = os.path.join(TTS_DIR, source, "tts.json")
                    if os.path.isfile(tts_meta):
                        try:
                            with open(tts_meta, "r", encoding="utf-8") as mf:
                                meta = json.load(mf)
                            item["text"] = meta.get("prompt", "")
                            item["voice"] = meta.get("voice", "af_heart")
                            item["speed"] = meta.get("speed", 1.0)
                        except Exception:
                            pass
                # Get style template ID (stored directly) or fallback to analysis
                item["style"] = data.get("style", "")
                if not item["style"]:
                    analysis = data.get("analysis", {})
                    if analysis:
                        item["style"] = analysis.get("visual_style", "")
                items.append(item)
            except Exception:
                continue
    # Also include in-progress jobs from memory
    with _jobs_lock:
        for jid, j in _jobs.items():
            pid = j.get("project_id", jid)
            items.append({
                "project_id": pid,
                "label": "Running..." if j.get("status") == "running" else pid,
                "scene_count": 0,
                "status": j.get("status", "unknown"),
                "created": j.get("created", 0),
                "step_sequence": j.get("step_sequence", []),
                "step_statuses": j.get("step_statuses", {}),
            })
    items.sort(key=lambda x: x.get("created", 0), reverse=True)
    return jsonify(items)


# ===================================================================
# Pipeline runner (background thread)
# ===================================================================

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
            "assets": results.get("assets"),
            "assemble": results.get("assemble"),
            "export": results.get("export"),
        },
    })
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job:
            job["status"] = "done"


def _run_pipeline(job_id):
    with _jobs_lock:
        job = _jobs[job_id]
        config = job["config"]
    project_id = config["project_id"]
    results = job["results"]

    stop_after = config.get("stop_after")
    step_seq = job.get("step_sequence", [])
    provider = config.get("provider", "grok")

    logger.info("[{}] Pipeline started | steps={} stop_after={} provider={} voice={} speed={} style={}",
                project_id, step_seq, stop_after, provider, config.get("voice"), config.get("speed"), config.get("style"))

    try:
        # ── Step 1: TTS ─────────────────────────────────────────────
        logger.info("[{}] Step 1/7: TTS starting", project_id)
        _emit(job_id, {"step": "tts", "status": "running",
                       "message": f"[{project_id}] Generating audio..."})
        tts_result = _step_tts(config, project_id)
        results["tts"] = tts_result
        logger.success("[{}] Step 1/7: TTS done — {:.1f}s audio, {} words",
                       project_id, tts_result["duration_seconds"], tts_result["words"])
        _emit(job_id, {
            "step": "tts", "status": "done",
            "message": f"[{project_id}] {tts_result['duration_seconds']:.1f}s audio, "
                       f"{tts_result['words']} words",
            "data": {k: v for k, v in tts_result.items() if k != "wav_path"},
        })
        if stop_after == "tts":
            logger.info("[{}] Pipeline stopped after TTS (stop_after=tts)", project_id)
            _emit_done(job_id, project_id, results)
            return

        # ── Step 2: Force Alignment ─────────────────────────────────
        logger.info("[{}] Step 2/7: Timing starting", project_id)
        _emit(job_id, {"step": "timing", "status": "running",
                       "message": f"[{project_id}] Aligning words..."})
        timing_result = _step_timing(tts_result, config, project_id)
        results["timing"] = timing_result
        logger.success("[{}] Step 2/7: Timing done — {} words in {:.2f}s",
                       project_id, timing_result["word_count"], timing_result["inference_time"])
        _emit(job_id, {
            "step": "timing", "status": "done",
            "message": f"[{project_id}] {timing_result['word_count']} words aligned "
                       f"in {timing_result['inference_time']:.2f}s",
        })
        if stop_after == "timing":
            logger.info("[{}] Pipeline stopped after Timing (stop_after=timing)", project_id)
            _emit_done(job_id, project_id, results)
            return

        # ── Step 3: Segmentation ────────────────────────────────────
        logger.info("[{}] Step 3/7: Segment starting", project_id)
        _emit(job_id, {"step": "segment", "status": "running",
                       "message": f"[{project_id}] Splitting into scenes..."})
        segment_result = _step_segment(timing_result, config, project_id)
        results["segment"] = segment_result
        stats = segment_result.get("stats", {})
        logger.success("[{}] Step 3/7: Segment done — {} scenes, avg {:.1f}s",
                       project_id, stats.get("segment_count", 0), stats.get("avg_duration", 0))
        _emit(job_id, {
            "step": "segment", "status": "done",
            "message": f"[{project_id}] {stats.get('segment_count', 0)} scenes, "
                       f"avg {stats.get('avg_duration', 0):.1f}s",
        })
        if stop_after == "segment":
            logger.info("[{}] Pipeline stopped after Segment (stop_after=segment)", project_id)
            _emit_done(job_id, project_id, results)
            return

        # ── Step 4: Scene Generation (webhook) — optional ────────────
        if config.get("auto_scenes", True):
            logger.info("[{}] Step 4/7: Scenes starting (webhook)", project_id)
            _emit(job_id, {"step": "scenes", "status": "running",
                           "message": f"[{project_id}] Generating scene scripts..."})
            scenes_result = _step_scenes(segment_result, config, project_id, job_id)
            results["scenes"] = scenes_result
            scene_count = len(scenes_result.get("scenes", []))
            logger.success("[{}] Step 4/7: Scenes done — {} scenes generated",
                           project_id, scene_count)
            _emit(job_id, {
                "step": "scenes", "status": "done",
                "message": f"[{project_id}] {scene_count} scenes generated",
                "data": scenes_result,
            })
        else:
            logger.info("[{}] Step 4/7: Scenes skipped (auto_scenes=false)", project_id)
            _emit(job_id, {
                "step": "scenes", "status": "skipped",
                "message": f"[{project_id}] Scene generation skipped",
            })

        if stop_after == "scenes":
            logger.info("[{}] Pipeline stopped after Scenes (stop_after=scenes)", project_id)
            _emit_done(job_id, project_id, results)
            return

        # ── Step 5: Asset Grabber ─────────────────────────────────
        provider_urls = {
            "grok": "https://grok.com/imagine",
            "midjourney": "https://www.midjourney.com/imagine",
            "meta-ai": "https://www.meta.ai/",
        }
        logger.info("[{}] Step 5/7: Assets starting | provider={}", project_id, provider)
        _emit(job_id, {
            "step": "assets", "status": "running",
            "message": f"[{project_id}] Starting asset grabber ({provider})...",
            "open_url": provider_urls.get(provider, ""),
        })
        assets_result = _step_assets(results.get("scenes", {}), config, project_id, job_id)
        results["assets"] = assets_result
        logger.success("[{}] Step 5/7: Assets done — {}/{} ready, {} errors",
                       project_id, assets_result.get("ready", 0),
                       assets_result.get("total", 0), assets_result.get("errors", 0))
        _emit(job_id, {
            "step": "assets", "status": "done",
            "message": f"[{project_id}] {assets_result.get('ready', 0)}/{assets_result.get('total', 0)} assets ready",
        })
        if stop_after == "assets":
            logger.info("[{}] Pipeline stopped after Assets (stop_after=assets)", project_id)
            _emit_done(job_id, project_id, results)
            return

        # ── Step 6: Assemble Project ──────────────────────────────
        logger.info("[{}] Step 6/7: Assemble starting", project_id)
        _emit(job_id, {"step": "assemble", "status": "running",
                       "message": f"[{project_id}] Assembling project..."})
        assemble_result = _step_assemble(project_id)
        results["assemble"] = assemble_result
        logger.success("[{}] Step 6/7: Assemble done — {} scenes, {:.1f}s, audio={}, captions={}",
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
            _emit_done(job_id, project_id, results)
            return

        # ── Step 7: Export Video ──────────────────────────────────
        logger.info("[{}] Step 7/7: Export starting", project_id)
        _emit(job_id, {"step": "export", "status": "running",
                       "message": f"[{project_id}] Exporting video..."})
        export_result = _step_export(assemble_result, project_id, job_id)
        results["export"] = export_result
        logger.success("[{}] Step 7/7: Export done — {} ({})",
                       project_id, export_result.get("filename", "?"),
                       export_result.get("resolution", "?"))
        _emit(job_id, {
            "step": "export", "status": "done",
            "message": f"[{project_id}] Exported {export_result.get('filename', 'video')}",
        })

        # ── Done ────────────────────────────────────────────────────
        logger.success("[{}] Pipeline COMPLETE — all {} steps finished", project_id, len(step_seq))
        _emit_done(job_id, project_id, results)

        with _jobs_lock:
            job["status"] = "done"

    except Exception as e:
        logger.error("[{}] Pipeline FAILED at step '{}': {}", project_id,
                     job.get("step_statuses", {}).keys() or "unknown", e)
        logger.exception("Pipeline traceback")
        _emit(job_id, {"step": "error", "status": "error",
                       "message": f"[{project_id}] {e}"})
        with _jobs_lock:
            job["status"] = "error"


# ===================================================================
# Step implementations
# ===================================================================

def _step_tts(config, project_id):
    """Generate TTS audio and return metadata dict (includes wav_path)."""
    from studio.tts.routes import (
        load_model, _voice_to_lang, _phonemize_with_misaki,
        generation_inference_lock, _tts_job_dir,
    )
    from studio.tts.normalize import clean_for_tts, tts_breathing_blocks
    from studio.tts.audio import pad_audio, concatenate_chunks, run_loudnorm

    text = config["text"]
    voice = config["voice"]
    speed = config["speed"]

    kokoro = load_model()
    lang = _voice_to_lang(voice)

    tts_prompt = clean_for_tts(text)
    blocks = tts_breathing_blocks(tts_prompt)

    audio_chunks = []
    total_inference = 0.0

    for block in blocks:
        phonemes, is_ph = _phonemize_with_misaki(block, lang)
        start = time.perf_counter()
        with generation_inference_lock:
            chunk_audio, _sr = kokoro.create(
                text=phonemes, voice=voice, speed=speed,
                lang=lang, is_phonemes=is_ph,
            )
        total_inference += time.perf_counter() - start
        audio_chunks.append(chunk_audio)

    if len(audio_chunks) > 1:
        audio = concatenate_chunks(audio_chunks, sample_rate=24000,
                                   gap_ms=80, crossfade_ms=20)
    else:
        audio = audio_chunks[0]
    audio = pad_audio(audio, sample_rate=24000)

    job_dir = _tts_job_dir(project_id)
    os.makedirs(job_dir, exist_ok=True)
    wav_path = os.path.join(job_dir, "voice.wav")
    sf.write(wav_path, audio, 24000)

    run_loudnorm(wav_path)

    info = sf.info(wav_path)
    duration = info.duration
    rtf = total_inference / duration if duration > 0 else 0
    clean_prompt = re.sub(r'[\[\]]', '', text).strip()

    metadata = {
        "filename": "voice.wav",
        "folder": project_id,
        "prompt": clean_prompt,
        "model": "kokoro-v1.0",
        "model_id": "kokoro",
        "voice": voice,
        "project_id": project_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "inference_time": round(total_inference, 3),
        "rtf": round(rtf, 4),
        "duration_seconds": round(duration, 2),
        "sample_rate": 24000,
        "speed": speed,
        "words": len(clean_prompt.split()),
        "approx_tokens": int(len(clean_prompt.split()) * 1.3),
        "wav_path": wav_path,
    }

    safe_json_write(
        os.path.join(job_dir, "tts.json"),
        {k: v for k, v in metadata.items() if k != "wav_path"},
        indent=2,
    )

    logger.success("Pipeline TTS: {:.1f}s audio in {:.2f}s",
                   duration, total_inference)
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

    logger.success("Pipeline Timing: {} words in {:.2f}s",
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


def _step_scenes(segment_result, config, project_id, job_id=None):
    """Generate scene scripts via webhook (with chapter support)."""
    from studio.scenes.chapters import (
        should_use_chapters,
    )
    from studio.scenes.prompts import SCENE_GENERATOR_PROMPT
    from studio.scenes.routes import (
        _call_webhook, generate_with_chapters_chunked,
        _apply_segmenter_timing, _normalize_webhook_response,
    )

    all_segments = segment_result.get("segments", [])
    segments = [
        {"index": s["index"], "words": s["words"]}
        for s in all_segments if not s.get("is_filler")
    ]

    if not segments:
        raise RuntimeError("No non-filler segments to generate scenes for")

    webhook_url = config.get("webhook_url") or N8N_WEBHOOK_URL
    script = config.get("text", "")
    style_id = config.get("style", "cinematic")
    style_prompt = config.get("style_prompt", "")

    # Resolve style_prompt from template if not provided
    if not style_prompt:
        from studio.scenes.templates import SCENE_STYLE_TEMPLATES
        tmpl = next((t for t in SCENE_STYLE_TEMPLATES if t["id"] == style_id), None)
        if tmpl:
            style_prompt = tmpl.get("style_prompt", "")

    # ── Chapter-based or single request ──
    if should_use_chapters(all_segments):
        def _progress(msg):
            if job_id:
                _emit(job_id, {"step": "scenes", "status": "running", "message": msg})

        result = generate_with_chapters_chunked(
            script=script,
            style_id=style_id,
            style_prompt=style_prompt,
            full_segments=all_segments,
            webhook_url=webhook_url,
            progress_cb=_progress if job_id else None,
        )
    else:
        # Single request (small script)
        system_prompt = SCENE_GENERATOR_PROMPT
        if style_prompt:
            system_prompt += f"\n\n## STYLE INSTRUCTIONS\n{style_prompt}"
        payload = {
            "script": script, "style": style_id,
            "system_prompt": system_prompt, "segments": segments,
        }
        result = _call_webhook(webhook_url, payload)

    # Apply segmenter timing — single source of truth for scene placement
    result = _normalize_webhook_response(result)
    speech_segments = [s for s in all_segments if not s.get("is_filler")]
    _apply_segmenter_timing(result, speech_segments, all_segments)

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


def _step_assets(scenes_result, config, project_id, job_id):
    """Step 5: Start asset grabber and poll until all scenes are ready."""
    from studio.assets.routes import grabber_start, _get_job, _set_job
    from studio.assets.schemas import GrabberStartRequest

    scenes = scenes_result.get("scenes", [])
    if not scenes:
        raise RuntimeError("No scenes to grab assets for")

    # Build grabber payload
    provider = config.get("provider", "grok")
    aspect_ratio = config.get("aspect_ratio", "9:16")
    auto_type = config.get("auto_type", True)

    payload = {
        "project_id": project_id,
        "provider": provider,
        "arguments": config.get("arguments", ""),
        "aspect_ratio": aspect_ratio,
        "auto_type": auto_type,
        "scenes": [
            {"prompt": s.get("image_prompt", ""), "scene": i}
            for i, s in enumerate(scenes)
        ],
    }
    # Add provider-specific options
    if provider == "grok":
        payload["grok_mode"] = config.get("grok_mode", "video")
        payload["grok_quality"] = config.get("grok_quality", "480p")
        payload["grok_duration"] = config.get("grok_duration", "6s")

    # Start grabber via internal API call
    base_url = f"http://127.0.0.1:{os.environ.get('STS_PORT', '5050')}"
    resp = http_requests.post(f"{base_url}/api/assets/grabber/start",
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

    # Poll until all scenes are ready (timeout 30 min)
    max_wait = 30 * 60  # 30 minutes
    poll_interval = 10  # seconds
    start_time = time.time()

    while time.time() - start_time < max_wait:
        time.sleep(poll_interval)
        try:
            status_resp = http_requests.get(
                f"{base_url}/api/assets/grabber/status/{project_id}", timeout=10)
            if status_resp.status_code != 200:
                continue
            status_data = status_resp.json()

            scene_statuses = status_data.get("scene_statuses", {})
            total = len(scene_statuses)
            ready = sum(1 for s in scene_statuses.values() if s.get("status") == "ready")
            errors = sum(1 for s in scene_statuses.values() if s.get("status") == "error")
            pending = total - ready - errors

            _emit(job_id, {
                "step": "assets", "status": "running",
                "message": f"Waiting for assets ({project_id})... {ready}/{total} ready"
                           + (f", {errors} errors" if errors else ""),
            })

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


def _step_export(assemble_result, project_id, job_id):
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

    export_payload = {
        "project_id": project_id,
        "scenes": export_scenes,
        "output": {
            "resolution": {"width": res["width"], "height": res["height"]},
            "fps": 30,
            "quality": "high",
        },
        "captions": assembled.get("captions") if captions_enabled else None,
        "audio": assembled.get("audio") or (
            {"path": assembled["audio_tracks"][0].get("url", ""),
             "volume": assembled["audio_tracks"][0].get("volume", 1.0)}
            if assembled.get("audio_tracks") else None
        ),
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

    # Poll export progress
    max_wait = 15 * 60  # 15 minutes
    start_time = time.time()

    while time.time() - start_time < max_wait:
        time.sleep(3)
        try:
            status_resp = http_requests.get(
                f"{base_url}/api/export/{export_job_id}/status", timeout=10)
            if status_resp.status_code != 200:
                continue
            status = status_resp.json()

            progress = status.get("progress", 0)
            message = status.get("message", "")
            _emit(job_id, {
                "step": "export", "status": "running",
                "message": f"[{project_id}] Exporting... {progress}% — {message}",
            })

            if status.get("status") == "done":
                return {
                    "filename": status.get("output_filename", ""),
                    "profile": profile,
                    "resolution": f"{res['width']}x{res['height']}",
                }
            if status.get("status") == "failed":
                raise RuntimeError(status.get("error", "Export failed"))
        except http_requests.RequestException as e:
            logger.debug("Pipeline Export poll error: {}", e)

    raise RuntimeError("Export timed out")
