"""Reusable implementations for the classic pipeline steps.

The functions in this module are extracted from :mod:`studio.pipeline.routes`.
Route-owned job state remains behind the small lazy bridges below so importing
the services does not import Flask routes or create a circular import.
"""

import os
import re
import shutil
import time
from datetime import datetime, timezone

import numpy as np
import requests as http_requests
import soundfile as sf
from loguru import logger

from config import (
    ALIGN_DIR,
    ANIMATOR_DIR,
    APP_ASSETS_DIR,
    EXPORT_DIR,
    N8N_WEBHOOK_URL,
    PROJECTS_DIR,
    SCENES_DIR,
    SEGMENTER_DIR,
)
from studio.io_utils import safe_json_read, safe_json_write


def _emit(job_id, event):
    """Forward progress to the route-owned classic-pipeline job queue."""
    from studio.pipeline.routes import _emit as route_emit

    return route_emit(job_id, event)


def _stop_requested(job_id):
    """Read stop state from the route-owned classic-pipeline job registry."""
    from studio.pipeline.routes import _stop_requested as route_stop_requested

    return route_stop_requested(job_id)


class PipelineStopped(RuntimeError):
    """Raised when a running pipeline is stopped by the user."""

    def __init__(self, step_name=None, message="Pipeline stopped by user"):
        super().__init__(message)
        self.step_name = step_name
        self.message = message


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
    speed = float(config.get("speed", 1.0))

    provider_id = (
        config.get("tts_provider_override")
        or config.get("tts_provider")
        or settings_manager.get_domain_settings("tts").get("selected_provider")
        or "kokoro"
    )

    provider = tts_registry.get(provider_id)
    if provider is None:
        raise ValueError(f"TTS provider '{provider_id}' not found. Available: {tts_registry.list_ids()}")

    # Pick the voice that matches the resolved provider — the frontend sends
    # both `voice` (kokoro) and `tts_voice` (inworld) so the wrong one must be
    # ignored, otherwise Inworld rejects kokoro voice IDs like 'am_fenrir'.
    if provider_id == "inworld":
        voice = config.get("tts_voice") or config.get("voice") or "Carter"
    else:
        voice = config.get("voice") or "af_bella"

    provider_settings = settings_manager.get_provider_settings("tts", provider_id)
    merged_settings = {**provider_settings, **config.get("tts_provider_options", {})}

    job_dir = _tts_job_dir(project_id)
    os.makedirs(job_dir, exist_ok=True)
    wav_path = os.path.join(job_dir, "voice.wav")

    if provider_id == "inworld":
        return _step_tts_inworld_pipeline(
            config, project_id, text, voice, speed, job_dir, wav_path,
            provider_id, provider_version=provider.version, provider_kind=provider.kind,
            provider_settings=merged_settings,
        )

    return _step_tts_kokoro_pipeline(
        config, project_id, text, voice, speed, job_dir, wav_path,
        provider_id, provider_version=provider.version, provider_kind=provider.kind,
        provider_settings=merged_settings,
    )


def _step_tts_inworld_pipeline(config, project_id, text, voice, speed, job_dir, wav_path,
                               provider_id, provider_version, provider_kind, provider_settings):
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
        "provider_kind": provider_kind,
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
                              provider_id, provider_version, provider_kind, provider_settings):
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
        "provider_kind": provider_kind,
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
    """Generate scene scripts via the scene_blueprint provider service.

    Compatibility facade for the fixed pipeline. The workflow adapter and the
    legacy `/api/scenes/generate` route dispatch through the provider hub; this
    step keeps calling the shared service so pipeline progress callbacks still
    work without re-entering the hub (step 13.4).
    """
    from studio.build_scene_blueprints.service import SceneServiceError, generate_scenes

    def _progress(msg):
        if job_id:
            _emit(job_id, {"step": "scenes", "status": "running", "message": msg})

    try:
        result = generate_scenes(
            segment_result,
            config,
            project_id=project_id,
            provider_id=(config or {}).get("provider_id") or "n8n",
            progress_cb=_progress if job_id else None,
        )
    except SceneServiceError as exc:
        raise RuntimeError(str(exc)) from exc
    result.pop("path", None)
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

    # Resolve provider: override → legacy field → the route's own fallback.
    # Step 14.2 deleted the canonical→legacy translation table that used to sit
    # here: the route resolves both spellings through the registry's aliases, so
    # the canonical ID can now be sent as-is. `prompt_prefix` went with it — it
    # is a provider setting, applied by the provider that declares it (§26).
    sb_provider = (
        config.get("storyboard_provider_override")
        or config.get("storyboard_provider")
        or ""
    )

    payload = {
        "project_id": project_id,
        "scenes": scenes_payload,
        "aspect_ratio": aspect_ratio,
        "style": config.get("style"),
        "image_model": config.get("image_model"),
        "provider": sb_provider,
        "provider_options": config.get("storyboard_provider_options") or {},
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
    """Step 6: Start asset grabber and poll until all scenes are ready.

    Provider-ID branching is gone (step 14.3). The route resolves the provider
    generically; this step only packs the request and reads the manifest's
    `open_url` for the frontend to open.
    """
    scenes = scenes_result.get("scenes", [])
    if not scenes:
        raise RuntimeError("No scenes to grab assets for")

    anim_override = config.get("animator_provider_override")
    anim_options = dict(config.get("animator_provider_options") or {})
    # Legacy flat keys still win so an un-migrated pipeline config is unaffected.
    if "mode" not in anim_options and config.get("grok_mode"):
        anim_options["mode"] = config["grok_mode"]
    if "quality" not in anim_options and config.get("grok_quality"):
        anim_options["quality"] = config["grok_quality"]
    if "duration" not in anim_options and config.get("grok_duration"):
        anim_options["duration"] = config["grok_duration"]
    if "auto_type" not in anim_options and "auto_type" in config:
        anim_options["auto_type"] = config["auto_type"]

    # Prefer the canonical override; fall back to the legacy wire spelling.
    selected = anim_override or config.get("provider") or "grok"

    payload = {
        "project_id": project_id,
        "provider_override": anim_override,
        "provider": None if anim_override else config.get("provider"),
        "provider_options": anim_options,
        "aspect_ratio": config.get("aspect_ratio", "9:16"),
        "scenes": [
            {"prompt": s.get("image_prompt", ""), "scene": s.get("index", i)}
            for i, s in enumerate(scenes)
            if s.get("image_prompt")
        ],
    }
    # Flat keys for un-migrated callers of the grabber route.
    if anim_options.get("mode") is not None:
        payload["grok_mode"] = anim_options["mode"]
    if anim_options.get("quality") is not None:
        payload["grok_quality"] = anim_options["quality"]
    if anim_options.get("duration") is not None:
        payload["grok_duration"] = anim_options["duration"]
    if "auto_type" in anim_options:
        payload["auto_type"] = anim_options["auto_type"]

    base_url = f"http://127.0.0.1:{os.environ.get('STS_PORT', '5050')}"
    if _stop_requested(job_id):
        raise PipelineStopped(step_name="assets")
    resp = http_requests.post(
        f"{base_url}/api/animator/grabber/start", json=payload, timeout=30
    )
    resp.raise_for_status()
    grab_data = resp.json()
    provider_id = grab_data.get("provider") or selected
    logger.info("Pipeline Assets: grabber started for {} via {}", project_id, provider_id)

    # open_url lives on the manifest (§20.1) — never a route-side literal.
    open_url = ""
    try:
        from studio.shared.providers_common.hub import hub
        instance = hub.get("animator", provider_id)
        if instance is not None and getattr(instance, "manifest", None):
            open_url = getattr(instance.manifest, "open_url", "") or ""
    except Exception:
        open_url = ""

    max_wait = 2 * 60 * 60  # 2 hours
    poll_interval = 10  # seconds
    start_time = time.time()
    prev_ready = 0

    while time.time() - start_time < max_wait:
        if _stop_requested(job_id):
            raise PipelineStopped(step_name="assets")
        time.sleep(poll_interval)
        if _stop_requested(job_id):
            raise PipelineStopped(step_name="assets")
        try:
            status_resp = http_requests.get(
                f"{base_url}/api/animator/grabber/status/{project_id}", timeout=10
            )
            if status_resp.status_code != 200:
                continue
            status_data = status_resp.json()

            scene_statuses = status_data.get("scene_statuses", {})
            total = len(scene_statuses)
            ready = sum(
                1 for s in scene_statuses.values() if s.get("status") == "ready"
            )
            errors = sum(
                1 for s in scene_statuses.values() if s.get("status") == "error"
            )
            pending = total - ready - errors

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
                logger.success(
                    "Pipeline Assets: {}/{} ready, {} errors", ready, total, errors
                )
                return {
                    "total": total, "ready": ready, "errors": errors,
                    "provider": provider_id,
                    "provider_url": open_url,
                }
        except Exception as e:
            logger.debug("Pipeline Assets poll error: {}", e)

    raise RuntimeError(f"Asset grabber timed out after {max_wait // 60} minutes")


def _step_assemble(project_id):
    """Step 6: Assemble project for the editor."""
    # Direct service invocation: never loop back through Flask over HTTP.
    from studio.editor.routes import assemble_project_for_editor
    data = assemble_project_for_editor(project_id, _direct=True, force=True)
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


