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
    TTS_DIR, ALIGN_DIR, SEGMENTER_DIR, SCENES_DIR,
    N8N_WEBHOOK_URL, generate_project_id,
)
from studio.io_utils import safe_json_write
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

    config = {
        "text": data.text.strip(),
        "voice": data.voice,
        "speed": data.speed,
        "style": data.style,
        "segment_config": data.segment_config,
        "webhook_url": data.webhook_url,
        "auto_scenes": data.auto_scenes,
        "project_id": project_id,
    }

    with _jobs_lock:
        _jobs[job_id] = {
            "queue": Queue(),
            "status": "running",
            "project_id": project_id,
            "config": config,
            "results": {},
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
                    tts_meta = os.path.join(TTS_DIR, source, source + ".json")
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
            if j.get("status") == "running":
                items.append({
                    "project_id": j.get("project_id", jid),
                    "label": "Running...",
                    "scene_count": 0,
                    "status": "running",
                    "created": j.get("created", 0),
                })
    items.sort(key=lambda x: x.get("created", 0), reverse=True)
    return jsonify(items)


# ===================================================================
# Pipeline runner (background thread)
# ===================================================================

def _run_pipeline(job_id):
    with _jobs_lock:
        job = _jobs[job_id]
        config = job["config"]
    project_id = config["project_id"]
    results = job["results"]

    try:
        # ── Step 1: TTS ─────────────────────────────────────────────
        _emit(job_id, {"step": "tts", "status": "running",
                       "message": "Generating audio..."})
        tts_result = _step_tts(config, project_id)
        results["tts"] = tts_result
        _emit(job_id, {
            "step": "tts", "status": "done",
            "message": f"{tts_result['duration_seconds']:.1f}s audio, "
                       f"{tts_result['words']} words",
            "data": {k: v for k, v in tts_result.items() if k != "wav_path"},
        })

        # ── Step 2: Force Alignment ─────────────────────────────────
        _emit(job_id, {"step": "timing", "status": "running",
                       "message": "Aligning words..."})
        timing_result = _step_timing(tts_result, config, project_id)
        results["timing"] = timing_result
        _emit(job_id, {
            "step": "timing", "status": "done",
            "message": f"{timing_result['word_count']} words aligned "
                       f"in {timing_result['inference_time']:.2f}s",
        })

        # ── Step 3: Segmentation ────────────────────────────────────
        _emit(job_id, {"step": "segment", "status": "running",
                       "message": "Splitting into scenes..."})
        segment_result = _step_segment(timing_result, config, project_id)
        results["segment"] = segment_result
        stats = segment_result.get("stats", {})
        _emit(job_id, {
            "step": "segment", "status": "done",
            "message": f"{stats.get('segment_count', 0)} scenes, "
                       f"avg {stats.get('avg_duration', 0):.1f}s",
        })

        # ── Step 4: Scene Generation (webhook) — optional ────────────
        if config.get("auto_scenes", True):
            _emit(job_id, {"step": "scenes", "status": "running",
                           "message": "Generating scene scripts..."})
            scenes_result = _step_scenes(segment_result, config, project_id, job_id)
            results["scenes"] = scenes_result
            scene_count = len(scenes_result.get("scenes", []))
            _emit(job_id, {
                "step": "scenes", "status": "done",
                "message": f"{scene_count} scenes generated",
                "data": scenes_result,
            })
        else:
            _emit(job_id, {
                "step": "scenes", "status": "skipped",
                "message": "Scene generation skipped",
            })

        # ── Done ────────────────────────────────────────────────────
        _emit(job_id, {
            "step": "done", "status": "done",
            "message": "Pipeline complete",
            "project_id": project_id,
            "summary": {
                "tts": {k: v for k, v in results["tts"].items()
                        if k != "wav_path"},
                "timing": {
                    "word_count": results["timing"]["word_count"],
                    "inference_time": results["timing"]["inference_time"],
                    "folder": results["timing"]["folder"],
                },
                "segment": results["segment"],
                "scenes": results.get("scenes"),
            },
        })

        with _jobs_lock:
            job["status"] = "done"

    except Exception as e:
        logger.exception("Pipeline failed")
        _emit(job_id, {"step": "error", "status": "error", "message": str(e)})
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
