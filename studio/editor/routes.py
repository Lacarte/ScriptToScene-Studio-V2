"""Editor Module — Timeline Editor Static File Serving + Export API"""

import io
import json
import mimetypes
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import threading
import traceback
import zipfile

from flask import Blueprint, send_from_directory, request, jsonify, send_file
from loguru import logger

from config import OUTPUT_DIR, BIN_DIR, APP_ASSETS_DIR, SCENES_DIR, ALIGN_DIR, TTS_DIR, ANIMATOR_DIR, EXPORT_DIR, CAPTIONS_DIR, PROJECTS_DIR, APP_CONFIG_PATH, TRASH_DIR, THUMBNAILS_DIR, PIPELINE_DIR, STORYBOARD_DIR
from studio.security import sanitize_folder_name, sanitize_project_id, safe_join
from studio.fonts import FONT_REGISTRY, get_font_path, get_font_url
from studio.ffmpeg_utils import find_ffprobe
from studio.io_utils import safe_json_write, safe_json_read
from studio.validation import validate_json
from studio.editor.schemas import EditorSaveRequest, ExportRequest
from studio.shared.providers_common import settings_adapter as adapter
from studio.shared.providers_common import settings_manager

editor_bp = Blueprint("editor", __name__)

# ---------------------------------------------------------------------------
# Export job storage & output directory
# ---------------------------------------------------------------------------
_export_jobs = {}
_export_jobs_lock = threading.Lock()
EXPORT_DIR_ABS = os.path.abspath(EXPORT_DIR)
EXPORT_MAX_JOB_AGE = 3600  # evict finished jobs after 1 hour

logger.info("Export output directory: {}", EXPORT_DIR)
logger.info("Projects directory: {}", PROJECTS_DIR)

WIP_FILENAME = "work@in@progress.json"
INITIAL_FILENAME = "initial.json"


def _project_dir(project_id: str) -> str:
    """Return the per-project directory inside PROJECTS_DIR."""
    return os.path.join(PROJECTS_DIR, project_id)


def _wip_path(project_id: str) -> str:
    """Return the path to the work-in-progress save file for a project."""
    return os.path.join(_project_dir(project_id), WIP_FILENAME)


def _initial_path(project_id: str) -> str:
    """Return the path to the initial (pristine) project file."""
    return os.path.join(_project_dir(project_id), INITIAL_FILENAME)


def _load_asset_metadata(project_id: str) -> dict:
    """Read per-scene asset metadata for a project if it exists."""
    meta_path = os.path.join(ANIMATOR_DIR, project_id, "metadata.json")
    try:
        data = safe_json_read(meta_path)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data.get("scenes", {}) if isinstance(data, dict) else {}


def _pick_scene_asset(project_id: str, *scene_keys: str,
                      used_urls: set | None = None) -> tuple[str, str]:
    """Return the best asset URL and resolved type for the given scene keys.

    If *used_urls* is provided, any URL already in the set is skipped and the
    chosen URL is added to the set — preventing the same asset from being
    assigned to multiple scenes.
    """
    video_exts = (".mp4", ".webm", ".mov")
    media_exts = video_exts + (".jpg", ".jpeg", ".png", ".webp")
    metadata = _load_asset_metadata(project_id)
    deduped_keys = tuple(dict.fromkeys(str(key) for key in scene_keys if key is not None))

    for scene_key in deduped_keys:
        meta_scene = metadata.get(scene_key, {}) or {}
        local_files = [
            path for path in meta_scene.get("local_files", [])
            if isinstance(path, str) and path.lower().endswith(media_exts)
        ]
        if local_files:
            # Prefer video files over images (thumbnails)
            video_local = [p for p in local_files if p.lower().endswith(video_exts)]
            media_url = video_local[-1] if video_local else local_files[-1]
            if used_urls is not None and media_url in used_urls:
                continue
            media_type = "video" if media_url.lower().endswith(video_exts) else "image"
            if used_urls is not None:
                used_urls.add(media_url)
            return media_url, media_type

    for scene_key in deduped_keys:
        asset_dir = os.path.join(ANIMATOR_DIR, project_id, scene_key)
        if not os.path.isdir(asset_dir):
            continue

        files = []
        for fname in os.listdir(asset_dir):
            fpath = os.path.join(asset_dir, fname)
            if os.path.isfile(fpath) and fname.lower().endswith(media_exts):
                files.append((os.path.getmtime(fpath), fname))

        if not files:
            continue

        # Prefer video files over images (thumbnails) when both exist
        video_files = [(t, f) for t, f in files if f.lower().endswith(video_exts)]
        pick = max(video_files) if video_files else max(files)
        _, fname = pick
        media_url = f"/output/animator/{project_id}/{scene_key}/{fname}"
        if used_urls is not None and media_url in used_urls:
            continue
        media_type = "video" if fname.lower().endswith(video_exts) else "image"
        if used_urls is not None:
            used_urls.add(media_url)
        return media_url, media_type

    # Fallback: check animator videos (output/animator/{project_id}/{scene_key}/*.mp4)
    for scene_key in deduped_keys:
        animator_scene_dir = os.path.join(ANIMATOR_DIR, project_id, str(scene_key))
        if not os.path.isdir(animator_scene_dir):
            continue
        vid_files = []
        for fname in os.listdir(animator_scene_dir):
            fpath = os.path.join(animator_scene_dir, fname)
            if os.path.isfile(fpath) and fname.lower().endswith(video_exts):
                vid_files.append((os.path.getmtime(fpath), fname))
        if not vid_files:
            continue
        _, fname = max(vid_files)
        media_url = f"/output/animator/{project_id}/{scene_key}/{fname}"
        if used_urls is not None and media_url in used_urls:
            continue
        if used_urls is not None:
            used_urls.add(media_url)
        return media_url, "video"

    return "", ""



def _read_app_config():
    """Read the full app-config.json file."""
    try:
        return safe_json_read(APP_CONFIG_PATH)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"version": 2, "defaults": {}, "localStorage": []}


def _write_app_config(cfg):
    """Write the full app-config.json file."""
    safe_json_write(APP_CONFIG_PATH, cfg, indent=2)



@editor_bp.route("/api/settings", methods=["GET"])
def get_settings():
    """Return user settings from app-config.json['user']."""
    cfg = _read_app_config()
    return jsonify(cfg.get("user", {}))


@editor_bp.route("/api/settings", methods=["PUT"])
def put_settings():
    """Replace all user settings in app-config.json['user']."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Expected JSON object"}), 400
    cfg = _read_app_config()
    cfg["user"] = data
    _write_app_config(cfg)
    return jsonify({"ok": True})


@editor_bp.route("/api/settings", methods=["PATCH"])
def patch_settings():
    """Merge partial updates into app-config.json['user']."""
    patch = request.get_json(silent=True)
    if not isinstance(patch, dict):
        return jsonify({"error": "Expected JSON object"}), 400
    cfg = _read_app_config()
    user = cfg.get("user", {})
    user.update(patch)
    cfg["user"] = user
    _write_app_config(cfg)
    return jsonify({"ok": True})


@editor_bp.route("/api/settings", methods=["DELETE"])
def delete_settings():
    """Reset user settings in app-config.json."""
    cfg = _read_app_config()
    cfg["user"] = {}
    _write_app_config(cfg)
    return jsonify({"ok": True})


@editor_bp.route("/api/settings/v2", methods=["GET"])
def get_settings_v2():
    """Return nested settings from settings/settings.json.
    
    Phase 1: Returns full settings structure with version, general, domains.
    Frontend compatibility via settings_adapter.nested_to_flat() until Phase 9.
    """
    settings = settings_manager.load_settings()
    return jsonify(settings)


@editor_bp.route("/api/settings/v2", methods=["PUT"])
def put_settings_v2():
    """Replace all settings in settings/settings.json."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Expected JSON object"}), 400
    issues = settings_manager.validate_settings(data)
    if issues:
        errors = [i for i in issues if i["severity"] == "error"]
        if errors:
            return jsonify({"error": "Invalid settings", "issues": issues}), 400
    settings_manager.save_settings(data)
    return jsonify({"ok": True, "issues": issues})


@editor_bp.route("/api/providers", methods=["GET"])
def list_providers():
    """Return registered providers by domain.
    
    Returns real registry contents with provider details and selected provider per domain.
    """
    from studio.tts.providers import registry as tts_registry
    from studio.storyboard.providers import registry as storyboard_registry
    from studio.animator.providers import registry as animator_registry
    from studio.shared.providers_common import settings_manager

    tts_settings = settings_manager.get_domain_settings('tts')
    storyboard_settings = settings_manager.get_domain_settings('storyboard')
    animator_settings = settings_manager.get_domain_settings('animator')

    return jsonify({
        "domains": {
            "tts": tts_registry.to_dict(selected_provider=tts_settings.get("selected_provider")),
            "storyboard": storyboard_registry.to_dict(selected_provider=storyboard_settings.get("selected_provider")),
            "animator": animator_registry.to_dict(selected_provider=animator_settings.get("selected_provider")),
        }
    })


@editor_bp.route("/api/providers/<domain>/<provider_id>/validate", methods=["POST"])
def validate_provider_settings(domain, provider_id):
    """Validate provider settings without saving.
    
    Validates the provider's settings and returns validation issues.
    """
    from studio.tts.providers import registry as tts_registry
    from studio.storyboard.providers import registry as storyboard_registry
    from studio.animator.providers import registry as animator_registry
    
    domainRegistries = {
        'tts': tts_registry,
        'storyboard': storyboard_registry,
        'animator': animator_registry,
    }
    
    if domain not in domainRegistries:
        return jsonify({"error": f"Unknown domain: {domain}"}), 400
    
    registry = domainRegistries[domain]
    provider = registry.get(provider_id)
    if provider is None:
        return jsonify({"error": f"Provider '{provider_id}' not found"}), 404
    
    data = request.get_json(silent=True) or {}
    current_settings = settings_manager.get_provider_settings(domain, provider_id)
    merged_settings = {**current_settings, **data}
    
    issues = provider.validate_settings(merged_settings)
    issues_list = [
        {"field": i.field, "severity": i.severity, "message": i.message}
        if hasattr(i, 'field') else i
        for i in issues
    ]
    
    has_errors = any(i.get('severity') == 'error' for i in issues_list)
    
    return jsonify({
        "valid": not has_errors,
        "issues": issues_list,
        "provider_id": provider_id,
        "domain": domain,
    })


@editor_bp.route("/api/providers/<domain>/<provider_id>/test", methods=["POST"])
def test_provider_settings(domain, provider_id):
    """Test provider connection/health.
    
    Runs health_check on the provider's current settings.
    """
    from studio.tts.providers import registry as tts_registry
    from studio.storyboard.providers import registry as storyboard_registry
    from studio.animator.providers import registry as animator_registry
    
    domainRegistries = {
        'tts': tts_registry,
        'storyboard': storyboard_registry,
        'animator': animator_registry,
    }
    
    if domain not in domainRegistries:
        return jsonify({"error": f"Unknown domain: {domain}"}), 400
    
    registry = domainRegistries[domain]
    provider = registry.get(provider_id)
    if provider is None:
        return jsonify({"error": f"Provider '{provider_id}' not found"}), 404
    
    data = request.get_json(silent=True) or {}
    current_settings = settings_manager.get_provider_settings(domain, provider_id)
    merged_settings = {**current_settings, **data}
    
    health = provider.health_check(merged_settings)
    
    return jsonify({
        "provider_id": provider_id,
        "domain": domain,
        "health": health,
    })


@editor_bp.route("/api/providers/<domain>/<provider_id>/settings", methods=["GET"])
def get_provider_settings(domain, provider_id):
    """Get settings for a specific provider.
    
    Returns the provider's settings merged with defaults from schema.
    """
    from studio.tts.providers import registry as tts_registry
    from studio.storyboard.providers import registry as storyboard_registry
    from studio.animator.providers import registry as animator_registry
    
    domainRegistries = {
        'tts': tts_registry,
        'storyboard': storyboard_registry,
        'animator': animator_registry,
    }
    
    if domain not in domainRegistries:
        return jsonify({"error": f"Unknown domain: {domain}"}), 400
    
    registry = domainRegistries[domain]
    provider = registry.get(provider_id)
    if provider is None:
        return jsonify({"error": f"Provider '{provider_id}' not found"}), 404
    
    settings = settings_manager.get_provider_settings(domain, provider_id)
    schema = provider.settings_schema()
    
    return jsonify({
        "provider_id": provider_id,
        "domain": domain,
        "settings": settings,
        "schema": schema,
        "manifest": provider.to_dict(),
    })


@editor_bp.route("/api/providers/<domain>/<provider_id>/settings", methods=["PUT"])
def put_provider_settings(domain, provider_id):
    """Update settings for a specific provider.
    
    Merges provided settings with existing and saves to settings.json.
    """
    from studio.tts.providers import registry as tts_registry
    from studio.storyboard.providers import registry as storyboard_registry
    from studio.animator.providers import registry as animator_registry
    
    domainRegistries = {
        'tts': tts_registry,
        'storyboard': storyboard_registry,
        'animator': animator_registry,
    }
    
    if domain not in domainRegistries:
        return jsonify({"error": f"Unknown domain: {domain}"}), 400
    
    registry = domainRegistries[domain]
    provider = registry.get(provider_id)
    if provider is None:
        return jsonify({"error": f"Provider '{provider_id}' not found"}), 404
    
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Expected JSON object"}), 400
    
    merged = settings_manager.get_provider_settings(domain, provider_id)
    merged.update(data)
    
    issues = provider.validate_settings(merged)
    issues_list = [
        {"field": i.field, "severity": i.severity, "message": i.message}
        if hasattr(i, 'field') else i
        for i in issues
    ]
    
    has_errors = any(i.get('severity') == 'error' for i in issues_list)
    if has_errors:
        return jsonify({"error": "Validation failed", "issues": issues_list}), 400
    
    settings_manager.set_provider_settings(domain, provider_id, merged)
    
    return jsonify({
        "ok": True,
        "issues": issues_list,
        "provider_id": provider_id,
        "domain": domain,
    })


@editor_bp.route("/api/settings/browse-folder", methods=["POST"])
def browse_folder():
    """Open a native folder picker dialog and return the selected path."""
    import tkinter as tk
    from tkinter import filedialog

    data = request.get_json(silent=True) or {}
    initial_dir = data.get("initial", "")

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    folder = filedialog.askdirectory(
        title="Select Sync Folder",
        initialdir=initial_dir if initial_dir and os.path.isdir(initial_dir) else None,
    )
    root.destroy()

    if not folder:
        return jsonify({"cancelled": True})
    return jsonify({"path": folder.replace("\\", "/")})


@editor_bp.route("/api/sfx/library")
def list_sfx():
    """List all sound effects from assets/sounds/sfx, grouped by folder category."""
    from config import APP_ASSETS_DIR
    from studio.ffmpeg_utils import find_ffprobe
    sfx_dir = os.path.join(APP_ASSETS_DIR, "sounds", "sfx")
    ALLOWED = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}

    if not os.path.isdir(sfx_dir):
        return jsonify({"categories": []})

    ffprobe = find_ffprobe()

    def _probe_dur(fpath):
        if not ffprobe:
            return None
        try:
            import subprocess as sp
            r = sp.run([ffprobe, "-v", "quiet", "-print_format", "json",
                        "-show_format", fpath],
                       capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return round(float(json.loads(r.stdout).get("format", {}).get("duration", 0)), 2)
        except Exception:
            pass
        return None

    def _clean_label(fname):
        label = os.path.splitext(fname)[0].replace("-", " ").replace("_", " ")
        return re.sub(r'\s*\d{6,}$', '', label).strip()

    def _scan_folder(folder_path, url_prefix):
        items = []
        if not os.path.isdir(folder_path):
            return items
        for fname in sorted(os.listdir(folder_path)):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ALLOWED or not os.path.isfile(os.path.join(folder_path, fname)):
                continue
            fpath = os.path.join(folder_path, fname)
            items.append({
                "filename": fname,
                "label": _clean_label(fname),
                "path": f"{url_prefix}/{fname}",
                "size_kb": round(os.path.getsize(fpath) / 1024, 1),
                "duration": _probe_dur(fpath),
            })
        return items

    categories = []

    # Root-level files → "General" category
    root_items = _scan_folder(sfx_dir, "/assets/sounds/sfx")
    if root_items:
        categories.append({"name": "General", "files": root_items})

    # Sub-folders → one category each
    for entry in sorted(os.listdir(sfx_dir)):
        sub = os.path.join(sfx_dir, entry)
        if not os.path.isdir(sub):
            continue
        items = _scan_folder(sub, f"/assets/sounds/sfx/{entry}")
        if items:
            cat_name = entry.replace("-", " ").replace("_", " ").title()
            categories.append({"name": cat_name, "files": items})

    return jsonify({"categories": categories})


def _auto_sync_after_export(filename, output_path):
    """Auto-sync exported video to sync folder if enabled in settings."""
    if not filename or not output_path or not os.path.isfile(output_path):
        return

    cfg = safe_json_read(APP_CONFIG_PATH) or {}
    defaults = cfg.get("defaults", {})
    user = cfg.get("user", {})

    if not (user.get("sts-auto-sync", defaults.get("sts-auto-sync", False))):
        return

    sync_folder = (user.get("sts-sync-folder") or defaults.get("sts-sync-folder") or "").strip()
    if not sync_folder:
        return

    sync_folder = os.path.normpath(sync_folder)
    if not os.path.isdir(sync_folder):
        return

    dest_dir = os.path.join(sync_folder, "exports")
    os.makedirs(dest_dir, exist_ok=True)

    dest_path = os.path.join(dest_dir, filename)
    if os.path.isfile(dest_path) and os.path.getsize(dest_path) == os.path.getsize(output_path):
        logger.info("Auto-sync: {} already up to date", filename)
        return

    shutil.copy2(output_path, dest_path)
    logger.success("Auto-synced: {} → {}", filename, dest_dir)


class ExportCancelled(Exception):
    """Raised when an export job is cancelled while processing."""


def _safe_project_id(project_id: str) -> str:
    return sanitize_project_id(project_id)


def _resolve_export_relpath(rel_path: str) -> str:
    """Resolve a path under EXPORT_DIR, rejecting traversal."""
    normalized = (rel_path or "").replace("\\", "/").lstrip("/")
    normalized = os.path.normpath(normalized).replace("\\", "/")
    if normalized.startswith("../") or normalized == "..":
        raise ValueError("Invalid path")
    abs_path = os.path.abspath(os.path.join(EXPORT_DIR_ABS, normalized))
    if os.path.commonpath([EXPORT_DIR_ABS, abs_path]) != EXPORT_DIR_ABS:
        raise ValueError("Invalid path")
    return abs_path


_ffprobe_bin = find_ffprobe()


def _ffprobe_video(abs_path: str) -> dict:
    """Return {duration, width, height} via ffprobe, or empty dict on failure."""
    if not _ffprobe_bin:
        return {}
    try:
        r = subprocess.run(
            [_ffprobe_bin, "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", abs_path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return {}
        data = json.loads(r.stdout)
        dur = float((data.get("format") or {}).get("duration", 0))
        # Find video stream for dimensions
        w, h = 0, 0
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                w = int(s.get("width", 0))
                h = int(s.get("height", 0))
                break
        return {"duration": round(dur, 2), "width": w, "height": h}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as error:
        logger.debug("ffprobe probe failed for {}: {}", abs_path, error)
        return {}


def _cleanup_old_export_jobs():
    """Evict completed/failed jobs older than EXPORT_MAX_JOB_AGE."""
    now = time.time()
    with _export_jobs_lock:
        expired = [
            jid for jid, job in _export_jobs.items()
            if job["status"] in ("completed", "failed", "cancelled")
            and now - job.get("created_at", 0) > EXPORT_MAX_JOB_AGE
        ]
        for jid in expired:
            del _export_jobs[jid]
    if expired:
        logger.debug("Evicted {} old export job(s)", len(expired))


def _cleanup_orphaned_temp_dirs():
    """Remove leftover video_export_* temp dirs older than 2 hours."""
    tmp_root = tempfile.gettempdir()
    cutoff = time.time() - 7200
    cleaned = 0
    try:
        for entry in os.listdir(tmp_root):
            if not entry.startswith("video_export_"):
                continue
            path = os.path.join(tmp_root, entry)
            if not os.path.isdir(path):
                continue
            try:
                mtime = os.path.getmtime(path)
                if mtime < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
                    cleaned += 1
            except OSError as error:
                logger.debug("Skipping temp dir cleanup for {}: {}", path, error)
    except OSError as error:
        logger.debug("Could not scan temp root {}: {}", tmp_root, error)
    if cleaned:
        logger.info("Cleaned up {} orphaned video_export temp dir(s)", cleaned)


# Run orphan cleanup on module load (server start)
_cleanup_orphaned_temp_dirs()


# ---------------------------------------------------------------------------
# Audio / caption resolution helpers
# ---------------------------------------------------------------------------

def _get_source_folder(project_id: str) -> str | None:
    """Look up source_folder from scenes.json for a given project."""
    scenes_path = os.path.join(SCENES_DIR, project_id, "scenes.json")
    try:
        with open(scenes_path, "r", encoding="utf-8") as f:
            return json.load(f).get("source_folder")
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as error:
        logger.debug("Could not read source_folder from {}: {}", scenes_path, error)
        return None


def _get_story_tone(project_id: str) -> str | None:
    """Look up story_tone from pipeline.json for a given project."""
    pipeline_path = os.path.join(PIPELINE_DIR, project_id, "pipeline.json")
    try:
        with open(pipeline_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("story_tone") or (data.get("config") or {}).get("story_tone") or None
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as error:
        logger.debug("Could not read story_tone from {}: {}", pipeline_path, error)
        return None


def _resolve_audio_url(source_folder: str) -> dict | None:
    """Resolve audio file URL from the alignment or TTS folder."""
    # Try alignment folder first (post-timing audio)
    align_path = os.path.join(ALIGN_DIR, source_folder)
    if os.path.isdir(align_path):
        try:
            for f in os.listdir(align_path):
                if f.endswith((".wav", ".mp3")):
                    return {
                        "url": f"/output/alignments/{source_folder}/{f}",
                        "source_file": f,
                    }
        except OSError:
            pass
    # Fall back to TTS folder (pre-timing audio)
    tts_path = os.path.join(TTS_DIR, source_folder)
    if os.path.isdir(tts_path):
        try:
            for f in os.listdir(tts_path):
                if f.endswith((".wav", ".mp3")):
                    return {
                        "url": f"/output/tts/{source_folder}/{f}",
                        "source_file": f,
                    }
        except OSError:
            pass
    return None


def _resolve_project_audio(data: dict, project_id: str):
    """Replace saved voice track with the correct audio for this project."""
    source_folder = _get_source_folder(project_id)
    if not source_folder:
        return
    resolved = _resolve_audio_url(source_folder)
    if not resolved:
        return
    correct_url = resolved["url"]
    # Keep the persisted voice track aligned with the actual resolved source.
    for track in data.get("audio_tracks", []):
        if track.get("type") != "voice":
            continue
        prev_path = track.get("path")
        prev_file = track.get("file")
        if prev_path != correct_url or prev_file != resolved["source_file"]:
            logger.info(
                "Normalizing voice track for {}: path {} -> {}, file {} -> {}",
                project_id,
                prev_path,
                correct_url,
                prev_file,
                resolved["source_file"],
            )
        track["path"] = correct_url
        track["file"] = resolved["source_file"]
        break


def _resolve_project_captions(data: dict, project_id: str):
    """Replace stale captions with the latest matching source_folder captions."""
    captions = data.get("captions")
    source_folder = _get_source_folder(project_id)
    if not source_folder:
        data["captions"] = None
        return

    cap_source = captions.get("source_folder", "") if captions else ""
    if captions and cap_source == source_folder:
        return

    if captions:
        logger.info(
            "Clearing stale captions for {}: cap source={} != project source={}",
            project_id,
            cap_source,
            source_folder,
        )

    latest_match = None
    latest_ts = ""
    if os.path.isdir(CAPTIONS_DIR):
        # Sort entries in reverse so newest (alphabetically highest) is checked first.
        # Since timestamps are ISO-formatted, the first match with the right
        # source_folder is very likely the latest — but we still keep the best.
        entries = sorted(os.listdir(CAPTIONS_DIR), reverse=True)
        for entry in entries:
            cap_json = os.path.join(CAPTIONS_DIR, entry, "captions.json")
            if not os.path.isfile(cap_json):
                continue
            try:
                payload = safe_json_read(cap_json)
            except Exception as error:
                logger.debug("Skipping captions payload {}: {}", cap_json, error)
                continue
            if payload.get("source_folder") != source_folder:
                continue
            ts = payload.get("timestamp", "")
            if ts >= latest_ts:
                latest_ts = ts
                latest_match = payload
                # First matching entry in reverse-sorted order is almost
                # certainly the newest; stop scanning the rest.
                break

    data["captions"] = latest_match
    if latest_match:
        logger.info(
            "Resolved captions for {} from source_folder={} -> {}",
            project_id,
            source_folder,
            latest_match.get("project_id", ""),
        )
        return

    # Fallback: build captions from alignment data (grouped with style)
    align_path = os.path.join(ALIGN_DIR, source_folder, "alignment.json")
    if os.path.isfile(align_path):
        try:
            from studio.captions.routes import (
                _get_default_caption_preset_id,
                _group_words_into_captions,
                CAPTION_PRESETS,
            )
            align_data = safe_json_read(align_path)
            alignment = align_data.get("alignment", [])
            if alignment:
                captions_list = _group_words_into_captions(alignment, words_per_group=3)
                if captions_list:
                    preset_id = _get_default_caption_preset_id()
                    cap_style = dict(CAPTION_PRESETS.get(preset_id, CAPTION_PRESETS.get("bold_popup", {})))
                    cap_style["preset"] = preset_id
                    data["captions"] = {
                        "project_id": project_id,
                        "source_folder": source_folder,
                        "captions": captions_list,
                        "style": cap_style,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    }
                    logger.info("Built {} captions from alignment for {}", len(captions_list), project_id)
        except Exception as e:
            logger.debug("Failed to build captions from alignment: {}", e)


_AUDIO_HISTORY_LIMIT = 10


def _normalize_audio_history(history) -> list[str]:
    """Keep a bounded list of valid persisted audio history paths."""
    if not isinstance(history, list):
        return []
    return [path for path in history if isinstance(path, str) and path.strip()][-_AUDIO_HISTORY_LIMIT:]


def _append_audio_history(history: list[str], path: str | None) -> list[str]:
    """Append a path to bounded recent history, de-duping earlier occurrences."""
    if not isinstance(path, str) or not path.strip():
        return _normalize_audio_history(history)
    normalized = [item for item in _normalize_audio_history(history) if item != path]
    normalized.append(path)
    return normalized[-_AUDIO_HISTORY_LIMIT:]


# ---------------------------------------------------------------------------
# Per-scene SFX placement (vocabulary-driven, see resources/sfx-vocabulary.json)
# ---------------------------------------------------------------------------

def _list_sfx_files_in_folder(folder: str) -> list[str]:
    """List all audio files in resources/sounds/sfx/<folder>/. Returns absolute paths."""
    sfx_dir = os.path.join(APP_ASSETS_DIR, "sounds", "sfx", folder)
    if not os.path.isdir(sfx_dir):
        return []
    audio_exts = (".mp3", ".wav", ".ogg", ".m4a", ".flac")
    return [
        os.path.join(sfx_dir, f)
        for f in sorted(os.listdir(sfx_dir))
        if f.lower().endswith(audio_exts)
        and os.path.isfile(os.path.join(sfx_dir, f))
    ]


def _pick_sfx_file_for_hint(entry: dict, history: list[str]) -> str | None:
    """Pick a real file matching a vocabulary entry, with history-deduped randomization.

    Looks at `folder` first, narrowed by `filename_match` regex if present.
    Falls back to `fallback_folder` (also narrowed by the same regex) if the
    primary folder produces nothing.

    Returns the absolute file path, or None if no candidates exist.
    """
    import random
    import re

    folder = entry.get("folder")
    if not folder:
        return None  # silence hint or unmapped entry

    pattern = entry.get("filename_match")
    regex = re.compile(pattern, re.IGNORECASE) if pattern else None

    def _candidates(in_folder: str) -> list[str]:
        all_files = _list_sfx_files_in_folder(in_folder)
        if not regex:
            return all_files
        return [p for p in all_files if regex.search(os.path.basename(p))]

    candidates = _candidates(folder)
    if not candidates:
        fallback = entry.get("fallback_folder")
        if fallback:
            candidates = _candidates(fallback)

    if not candidates:
        return None

    # Prefer files NOT in recent history
    fresh = [p for p in candidates if p not in history]
    pool = fresh if fresh else candidates
    return random.choice(pool)


def _build_per_scene_sfx_tracks(
    editor_scenes: list[dict],
    raw_scenes: list[dict],
    sfx_history: list[str],
) -> tuple[list[dict], list[str]]:
    """Build per-scene SFX tracks from validated sfx_hint fields.

    For each scene that carries a non-null `sfx_hint`, look up the vocabulary
    entry, pick a real file, compute the timeline offset based on the entry's
    placement mode, and produce an audio_tracks-shaped dict.

    Returns (tracks_to_append, updated_sfx_history). The history is grown by
    each successful pick so the next pick within the same project doesn't
    re-roll the same file.

    Placement modes:
      - scene_start    : timelineOffset = scene start time (one-shot, fires on cut into scene)
      - scene_duration : timelineOffset = scene start, trimmedDuration = scene length (looped texture)
      - lead_in        : timelineOffset = scene start - lead_in_seconds (one-shot fires before cut)

    Skipped silently when:
      - sfx_hint is null/empty
      - hint key is not in the loaded vocabulary
      - the entry's folder (and fallback) contain no matching files
      - the hint is `silence` (intentional no-op — the bed track will be ducked)
    """
    from studio.build_scene_blueprints.sfx_validator import load_sfx_vocabulary

    vocab = load_sfx_vocabulary()
    hints_by_id = vocab.get("hints") or {}
    if not hints_by_id:
        return [], sfx_history

    history = list(sfx_history or [])
    tracks: list[dict] = []
    seq = 0  # for unique track ids

    # Build a fast index from scene index/id to its computed timestamp + duration.
    # editor_scenes already has timestamps computed at the cumulative-position step.
    scene_by_id = {es["id"]: es for es in editor_scenes}

    for raw in raw_scenes:
        # Try several keys to find the matching editor scene — raw scenes
        # use `index`, editor scenes use `id` (which is the array position).
        # The assemble loop builds editor_scenes in raw_scenes order, so the
        # raw_scenes index in the loop is the editor scene id.
        try:
            raw_index = int(raw.get("index", -1))
        except (TypeError, ValueError):
            raw_index = -1

        # The editor scene id is the array position from the assemble loop.
        # raw_scenes and editor_scenes are 1:1 ordered, so we use the loop
        # position. But we don't have the loop position here — instead use
        # the raw_index which is what was set as `id` in the loop above.
        # Defensively, fall back to scanning by raw index.
        editor_scene = scene_by_id.get(raw_index)
        if editor_scene is None:
            continue

        hint_id = raw.get("sfx_hint")
        if not hint_id:
            continue

        entry = hints_by_id.get(hint_id)
        if not entry:
            continue  # validator should have caught this, defense in depth

        if hint_id == "silence":
            # Explicit no-op. The audio bed will keep playing — silence is a
            # creative choice to NOT add an accent here, not a request to
            # mute the existing layers.
            continue

        chosen_path = _pick_sfx_file_for_hint(entry, history)
        if not chosen_path:
            logger.debug("SFX hint '{}' has no available files (folder={}, fallback={})",
                         hint_id, entry.get("folder"), entry.get("fallback_folder"))
            continue

        history.append(chosen_path)

        # Compute timeline offset based on placement mode
        scene_start = float(editor_scene.get("timestamp", 0) or 0)
        scene_duration = float(editor_scene.get("duration", 0) or 0)
        placement = entry.get("placement", "scene_start")

        if placement == "lead_in":
            lead = float(entry.get("lead_in_seconds", 0.5) or 0.5)
            timeline_offset = max(0.0, scene_start - lead)
            trimmed_duration = None
        elif placement == "scene_duration":
            timeline_offset = scene_start
            trimmed_duration = scene_duration
        else:  # scene_start (default)
            timeline_offset = scene_start
            trimmed_duration = None

        # Build the asset URL the editor's audio system uses.
        # Files live under resources/sounds/sfx/<folder>/<file>; the editor
        # serves them via /assets/sounds/sfx/<folder>/<file>.
        sfx_file = os.path.basename(chosen_path)
        sfx_folder = os.path.basename(os.path.dirname(chosen_path))
        sfx_url = f"/assets/sounds/sfx/{sfx_folder}/{sfx_file}"

        seq += 1
        tracks.append({
            "id": f"at_sfx_scene{raw_index}_{hint_id}_{seq}",
            "label": entry.get("label", hint_id.upper()),
            "type": "sfx",
            "file": sfx_file,
            "path": sfx_url,
            "duration": 0,
            "timelineOffset": round(timeline_offset, 3),
            "startOffset": 0,
            "trimmedDuration": round(trimmed_duration, 3) if trimmed_duration is not None else None,
            "volume": float(entry.get("volume", 0.15)),
            "loop": bool(entry.get("loop", False)),
            "muted": False,
            "duckingEnabled": True,
            "duckingLevel": 0.20,
            "fadeIn": float(entry.get("fade_in", 0.0)),
            "fadeOut": float(entry.get("fade_out", 0.3)),
            # Provenance — useful for debugging when a hint fires the wrong file
            "sfx_hint": hint_id,
            "scene_index": raw_index,
        })

        logger.info("Per-scene SFX: scene {} -> {} ({}) @ {:.2f}s [{}]",
                    raw_index, hint_id, sfx_file, timeline_offset, placement)

    return tracks, history


def _builtin_audio_url_to_abs(track_type: str, path: str | None) -> str | None:
    """Convert a built-in /assets/sounds/{music|sfx}/... URL back to an absolute path."""
    if not isinstance(path, str) or not path.strip():
        return None
    bucket = "music" if track_type == "music" else "sfx" if track_type == "sfx" else ""
    if not bucket:
        return None
    prefix = f"/assets/sounds/{bucket}/"
    if not path.startswith(prefix):
        return None
    rel = path[len("/assets/"):].replace("/", os.sep)
    return os.path.join(APP_ASSETS_DIR, rel)


def _builtin_audio_abs_to_url(track_type: str, abs_path: str | None) -> str | None:
    """Convert a built-in music/SFX absolute path to the matching /assets/... URL."""
    if not isinstance(abs_path, str) or not abs_path.strip():
        return None
    normalized = os.path.abspath(abs_path)
    try:
        if os.path.commonpath([os.path.abspath(APP_ASSETS_DIR), normalized]) != os.path.abspath(APP_ASSETS_DIR):
            return None
    except ValueError:
        return None
    bucket = "music" if track_type == "music" else "sfx" if track_type == "sfx" else ""
    if not bucket:
        return None
    expected_root = os.path.join(APP_ASSETS_DIR, "sounds", bucket)
    try:
        if os.path.commonpath([os.path.abspath(expected_root), normalized]) != os.path.abspath(expected_root):
            return None
    except ValueError:
        return None
    rel = os.path.relpath(normalized, APP_ASSETS_DIR).replace("\\", "/")
    return f"/assets/{rel}"


def _materialize_history_audio_tracks(data: dict) -> None:
    """Backfill missing music/SFX tracks from persisted history for older projects."""
    if not isinstance(data, dict):
        return

    tracks = data.get("audio_tracks")
    if not isinstance(tracks, list):
        tracks = []
        data["audio_tracks"] = tracks

    existing_types = {
        str(track.get("type") or "").lower()
        for track in tracks
        if isinstance(track, dict)
    }
    music_history = _normalize_audio_history(data.get("music_history"))
    sfx_history = _normalize_audio_history(data.get("sfx_history"))

    from studio.music.selector import recall_last_music, recall_last_sfx

    if "music" not in existing_types:
        restored_music = recall_last_music(music_history)
        if restored_music:
            music_url = _builtin_audio_abs_to_url("music", restored_music.get("path"))
            music_path = restored_music.get("path") or ""
            if music_url and music_path:
                tracks.append({
                    "id": "at_music_history",
                    "label": "Music",
                    "type": "music",
                    "file": os.path.basename(music_path),
                    "path": music_url,
                    "duration": 0,
                    "timelineOffset": 0,
                    "startOffset": 0,
                    "trimmedDuration": None,
                    "volume": restored_music.get("volume", 0.15),
                    "loop": restored_music.get("loop", True),
                    "muted": False,
                    "duckingEnabled": restored_music.get("ducking_enabled", True),
                    "duckingLevel": restored_music.get("ducking_level", 0.20),
                    "fadeIn": restored_music.get("fade_in", 2.0),
                    "fadeOut": restored_music.get("fade_out", 3.0),
                })
                existing_types.add("music")

    if "sfx" not in existing_types:
        restored_sfx = recall_last_sfx(sfx_history)
        if restored_sfx:
            sfx_url = _builtin_audio_abs_to_url("sfx", restored_sfx.get("path"))
            sfx_path = restored_sfx.get("path") or ""
            if sfx_url and sfx_path:
                tracks.append({
                    "id": "at_sfx_history",
                    "label": "SFX",
                    "type": "sfx",
                    "file": os.path.basename(sfx_path),
                    "path": sfx_url,
                    "duration": 0,
                    "timelineOffset": 0,
                    "startOffset": 0,
                    "trimmedDuration": None,
                    "volume": restored_sfx.get("volume", 0.10),
                    "loop": restored_sfx.get("loop", True),
                    "muted": False,
                    "duckingEnabled": restored_sfx.get("ducking_enabled", True),
                    "duckingLevel": restored_sfx.get("ducking_level", 0.20),
                    "fadeIn": restored_sfx.get("fade_in", 1.5),
                    "fadeOut": restored_sfx.get("fade_out", 2.0),
                })


def _merge_project_audio_history(save_data: dict, project_id: str):
    """Keep initial/WIP payloads in sync with current music/SFX history."""
    initial = _initial_path(project_id)
    existing_initial = {}
    if os.path.isfile(initial):
        try:
            existing_initial = safe_json_read(initial)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.debug("Could not read existing initial.json for {}: {}", project_id, e)
            existing_initial = {}
    if not isinstance(existing_initial, dict):
        existing_initial = {}

    music_history = _normalize_audio_history(
        save_data.get("music_history") if "music_history" in save_data else existing_initial.get("music_history")
    )
    sfx_history = _normalize_audio_history(
        save_data.get("sfx_history") if "sfx_history" in save_data else existing_initial.get("sfx_history")
    )

    for track in save_data.get("audio_tracks", []):
        if not isinstance(track, dict):
            continue
        track_type = str(track.get("type") or "").lower()
        abs_path = _builtin_audio_url_to_abs(track_type, track.get("path"))
        if track_type == "music":
            music_history = _append_audio_history(music_history, abs_path)
        elif track_type == "sfx":
            sfx_history = _append_audio_history(sfx_history, abs_path)

    save_data["music_history"] = music_history
    save_data["sfx_history"] = sfx_history


# ---------------------------------------------------------------------------
# Editor project save / load
# ---------------------------------------------------------------------------

@editor_bp.route("/api/editor/save", methods=["POST"])
@validate_json(EditorSaveRequest)
def editor_save_project(data: EditorSaveRequest):
    """Save editor project edits to both the work-in-progress and initial files."""
    safe_id = data.project_id  # already validated: alphanumeric + _ and -

    from datetime import datetime, timezone
    save_data = data.model_dump(exclude_none=True)
    source_folder = _get_source_folder(safe_id)
    if source_folder:
        save_data["source_folder"] = source_folder
        captions = save_data.get("captions")
        if isinstance(captions, dict) and not captions.get("source_folder"):
            captions["source_folder"] = source_folder
    _resolve_project_audio(save_data, safe_id)
    _resolve_project_captions(save_data, safe_id)
    _merge_project_audio_history(save_data, safe_id)
    save_data["saved_at"] = datetime.now(timezone.utc).isoformat()

    os.makedirs(_project_dir(safe_id), exist_ok=True)

    # Always write to the WIP file — initial state stays untouched
    # Mirror the latest saved editor state into both project files.
    initial = _initial_path(safe_id)
    wip = _wip_path(safe_id)
    try:
        safe_json_write(initial, save_data)
        safe_json_write(wip, save_data)
    except OSError as e:
        logger.error("Failed to save editor state for {}: {}", safe_id, e)
        return jsonify({"error": f"Failed to save: {e}"}), 500

    logger.info("Editor state saved to initial + WIP: {} ({} scenes)", safe_id, save_data.get("scene_count", "?"))
    return jsonify({"ok": True, "saved_at": save_data["saved_at"], "wip": True, "initial": True})


@editor_bp.route("/api/editor/load/<project_id>", methods=["GET"])
def editor_load_project(project_id):
    """Load a saved editor project.

    Prefers the work-in-progress file if it exists, otherwise falls back to
    the initial project file.  The response includes a ``source``
    field (``"wip"`` or ``"initial"``) so the frontend knows which was loaded.
    """
    safe_id = "".join(c for c in project_id if c.isalnum() or c in ("_", "-"))

    # Try WIP first, then initial
    wip = _wip_path(safe_id)
    initial = _initial_path(safe_id)
    source = "initial"

    if os.path.isfile(wip):
        path = wip
        source = "wip"
    elif os.path.isfile(initial):
        path = initial
    else:
        return jsonify({"error": "not found"}), 404

    try:
        data = safe_json_read(path)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load editor project {}: {}", safe_id, e)
        return jsonify({"error": f"Corrupted project file: {e}"}), 500

    data["_source"] = source

    # Inject source_folder so the frontend can scope captions/audio
    source_folder = _get_source_folder(safe_id)
    if source_folder:
        data["source_folder"] = source_folder

    # Inject story_tone from pipeline so the editor can auto-select animations
    story_tone = _get_story_tone(safe_id)
    if story_tone:
        data["story_tone"] = story_tone

    # Resolve correct audio from scenes.json source_folder to prevent
    # cross-project audio bleed (saved voice track may belong to another project).
    _resolve_project_audio(data, safe_id)
    _materialize_history_audio_tracks(data)

    # Resolve correct captions from the alignment folder
    _resolve_project_captions(data, safe_id)
    if data.get("captions"):
        if source == "initial":
            data["captionsEnabled"] = True
        elif data.get("captionsEnabled") is False and not data.get("edit_history"):
            data["captionsEnabled"] = True

    return jsonify(data)


@editor_bp.route("/api/editor/projects", methods=["GET"])
def editor_list_projects():
    """List all saved editor projects from per-project subdirectories."""
    seen_ids = set()
    projects = []

    def _collect_from_dir(proj_dir, pid):
        """Read project metadata from an editor subdirectory."""
        if pid in seen_ids:
            return
        wip = os.path.join(proj_dir, WIP_FILENAME)
        initial = os.path.join(proj_dir, INITIAL_FILENAME)
        has_wip = os.path.isfile(wip)
        fpath = wip if has_wip else initial
        if not os.path.isfile(fpath):
            return
        try:
            data = safe_json_read(fpath)
            seen_ids.add(pid)
            # Look up thumbnail preview
            preview = None
            thumb_base = os.path.join(THUMBNAILS_DIR, pid)
            editor_cover = os.path.join(thumb_base, "editor", "cover.jpg")
            assets_thumb_0 = os.path.join(thumb_base, "assets", "0.jpg")
            if os.path.isfile(editor_cover):
                preview = f"/api/thumbnails/{pid}/editor/cover.jpg"
            elif os.path.isfile(assets_thumb_0):
                preview = f"/api/thumbnails/{pid}/assets/0.jpg"
            projects.append({
                "project_id": data.get("project_id", pid),
                "project_name": data.get("project_name", ""),
                "saved_at": data.get("saved_at", ""),
                "scene_count": data.get("scene_count", 0),
                "total_duration": data.get("total_duration", 0),
                "has_wip": has_wip,
                "preview": preview,
            })
        except Exception as error:
            logger.debug("Skipping project manifest {}: {}", fpath, error)

    if os.path.isdir(PROJECTS_DIR):
        for entry in os.listdir(PROJECTS_DIR):
            proj_dir = os.path.join(PROJECTS_DIR, entry)
            if os.path.isdir(proj_dir):
                _collect_from_dir(proj_dir, entry)

    projects.sort(key=lambda p: p.get("saved_at", ""), reverse=True)
    return jsonify(projects)


# ---------------------------------------------------------------------------
# Project Discovery — scans all output dirs for available projects
# ---------------------------------------------------------------------------

def _discover_projects() -> list[dict]:
    """Scan output directories to discover all projects and their status."""
    projects = {}  # project_id → info dict

    # 1. Scan scenes dir (source of truth for generated projects)
    if os.path.isdir(SCENES_DIR):
        for entry in os.listdir(SCENES_DIR):
            scenes_path = os.path.join(SCENES_DIR, entry, "scenes.json")
            if not os.path.isfile(scenes_path):
                continue
            try:
                mtime = os.path.getmtime(scenes_path)
                with open(scenes_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                projects[entry] = {
                    "project_id": entry,
                    "project_name": data.get("project_name", entry),
                    "source_folder": data.get("source_folder", entry),
                    "scene_count": data.get("scene_count", len(data.get("scenes", []))),
                    "total_duration": data.get("total_duration", 0),
                    "style": data.get("style", ""),
                    "created_at": data.get("timestamp", ""),
                    "has_scenes": True,
                    "has_assets": False,
                    "has_audio": False,
                    "has_editor": False,
                    "asset_count": 0,
                }
            except Exception as error:
                logger.debug("Skipping scenes manifest {}: {}", scenes_path, error)
                continue

    # 2. Check assets
    if os.path.isdir(ANIMATOR_DIR):
        for entry in os.listdir(ANIMATOR_DIR):
            asset_dir = os.path.join(ANIMATOR_DIR, entry)
            if not os.path.isdir(asset_dir):
                continue
            if entry not in projects:
                projects[entry] = {
                    "project_id": entry,
                    "project_name": entry,
                    "source_folder": entry,
                    "scene_count": 0,
                    "total_duration": 0,
                    "style": "",
                    "created_at": "",
                    "has_scenes": False,
                    "has_assets": False,
                    "has_audio": False,
                    "has_editor": False,
                    "asset_count": 0,
                }
            # Count asset subdirs (scene folders with media)
            asset_count = sum(
                1 for d in os.listdir(asset_dir)
                if os.path.isdir(os.path.join(asset_dir, d)) and d.isdigit()
            )
            projects[entry]["has_assets"] = asset_count > 0
            projects[entry]["asset_count"] = asset_count

    # 3. Check audio (alignments)
    if os.path.isdir(ALIGN_DIR):
        for entry in os.listdir(ALIGN_DIR):
            align_path = os.path.join(ALIGN_DIR, entry)
            if not os.path.isdir(align_path):
                continue
            has_wav = any(f.endswith((".wav", ".mp3")) for f in os.listdir(align_path))
            if has_wav:
                # Find the project this audio belongs to (source_folder match)
                for pid, info in projects.items():
                    if info.get("source_folder") == entry:
                        info["has_audio"] = True
                        break

    # 4. Check editor saves in output/projects/{id}/
    for pid in list(projects.keys()):
        proj_dir = os.path.join(PROJECTS_DIR, pid)
        if os.path.isdir(proj_dir):
            has_save = os.path.isfile(os.path.join(proj_dir, WIP_FILENAME)) or \
                       os.path.isfile(os.path.join(proj_dir, INITIAL_FILENAME))
            if has_save:
                projects[pid]["has_editor"] = True

    # 5. Enrich with TTS metadata (text, voice, speed)
    if os.path.isdir(TTS_DIR):
        for pid, info in projects.items():
            sf = info.get("source_folder", pid)
            tts_meta = os.path.join(TTS_DIR, sf, "tts.json")
            if os.path.isfile(tts_meta):
                try:
                    with open(tts_meta, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    info["text_preview"] = (meta.get("prompt", "") or "")[:120]
                    info["voice"] = meta.get("voice", "")
                    info["audio_duration"] = meta.get("duration_seconds", 0)
                except Exception as error:
                    logger.debug("Skipping TTS metadata {}: {}", tts_meta, error)

    # 6. Write/update manifests to PROJECTS_DIR (skip if initial.json already exists)
    for pid, info in projects.items():
        manifest_dir = os.path.join(PROJECTS_DIR, pid)
        project_file = os.path.join(manifest_dir, "project.json")
        initial_file = os.path.join(manifest_dir, INITIAL_FILENAME)
        os.makedirs(manifest_dir, exist_ok=True)
        # Don't overwrite if initial.json or a full project.json already exists
        if os.path.isfile(initial_file):
            continue
        if os.path.isfile(project_file):
            try:
                existing = safe_json_read(project_file)
                if existing.get("scenes"):
                    continue  # Already has full project data
            except Exception as error:
                logger.debug("Could not read existing project manifest {}: {}", project_file, error)
        safe_json_write(project_file, info, indent=2)

    result = sorted(projects.values(), key=lambda p: p.get("created_at", ""), reverse=True)
    return result


@editor_bp.route("/api/projects", methods=["GET"])
def list_all_projects():
    """Discover and list all projects across output directories."""
    projects = _discover_projects()
    return jsonify(projects)


@editor_bp.route("/api/projects/<project_id>/assemble", methods=["POST"])
def assemble_project_for_editor(project_id):
    """Assemble a project from scenes + assets into editor-ready format.

    Creates initial.json in the editor directory if it doesn't exist,
    then returns the assembled data ready for the editor to load.
    """
    safe_id = "".join(c for c in project_id if c.isalnum() or c in ("_", "-"))

    force = request.args.get("force", "0") == "1"

    # Check if editor save already exists → return it directly (unless force rebuild)

    wip = _wip_path(safe_id)
    initial = _initial_path(safe_id)

    if not force and (os.path.isfile(wip) or os.path.isfile(initial)):
        try:
            data = safe_json_read(wip if os.path.isfile(wip) else initial)
            _resolve_project_audio(data, safe_id)
            _resolve_project_captions(data, safe_id)
            data["_source"] = "wip" if os.path.isfile(wip) else "initial"
            return jsonify(data)
        except Exception as e:
            logger.warning("Existing editor data corrupt for {}, rebuilding: {}", safe_id, e)

    # Build from scenes.json
    scenes_path = os.path.join(SCENES_DIR, safe_id, "scenes.json")
    if not os.path.isfile(scenes_path):
        return jsonify({"error": "No scenes found for this project"}), 404

    try:
        with open(scenes_path, "r", encoding="utf-8") as f:
            scenes_data = json.load(f)
    except Exception as e:
        return jsonify({"error": f"Failed to read scenes: {e}"}), 500

    source_folder = scenes_data.get("source_folder", safe_id)
    raw_scenes = scenes_data.get("scenes", [])

    # Build editor-format scenes
    editor_scenes = []
    used_asset_urls = set()  # prevent the same asset from being assigned to multiple scenes
    for i, s in enumerate(raw_scenes):
        scene_index = s.get("index", i)
        scene_type = s.get("type_of_scene", s.get("type", "image"))
        duration = s.get("duration", 3)

        # Cap bloated scene durations — if the scene has way more time than its
        # speech segment (e.g., TTS inserted a long paragraph pause), trim it
        seg_dur = s.get("segment_duration")
        if seg_dur and seg_dur > 0 and duration > seg_dur + 2.0:
            duration = round(seg_dur + 1.5, 2)
        media_url, media_type = _pick_scene_asset(safe_id, i, scene_index,
                                                   used_urls=used_asset_urls)
        if scene_type != "text" and media_type:
            scene_type = media_type

        # Find media asset — asset dirs use sequential position (i), not scene_index
        # because the grabber saves files by array position, not by scene.index
        is_video = scene_type == "video" or media_url.endswith((".mp4", ".webm", ".mov"))

        editor_scenes.append({
            "id": i,
            "scene_id": i,
            "type": scene_type,
            "scene_type": s.get("narrative_role", s.get("type_of_scene", scene_type)),
            "duration": duration,
            "visual_fx": s.get("visual_fx", "static"),
            "effect": {"type": "none"},
            "transition": {"type": "none", "duration": 0},
            "image_url": media_url,
            "mediaUrl": media_url,
            "image": "",
            "image_prompt": s.get("image_prompt", ""),
            "prompt": s.get("image_prompt", ""),
            "description": s.get("description", ""),
            "style": s.get("style", ""),
            "text_content": s.get("text_content"),
            "text_x": None,
            "text_y": None,
            "text_timeline_offset": 0,
            "text_overlay_duration": duration,
            "text_background_enabled": s.get("text_content") is not None and scene_type == "text",
            "text_background_color": "#000000",
            "timestamp": 0,
            "status": "done" if media_url else "pending",
            "isVideo": is_video,
            "script": s.get("segment_words", ""),
            "narrative_role": s.get("narrative_role", ""),
            "text_hook_animation": s.get("text_hook_animation"),
            "filler_shift": 0,
            "segment_start": s.get("segment_start"),
            "segment_end": s.get("segment_end"),
            "segment_duration": s.get("segment_duration"),
            "asset_files": [media_url] if media_url else [],
            # SFX hint chosen by the scene planner LLM and validated by sfx_validator.
            # The renderer turns this into an actual per-scene audio track in the
            # _build_per_scene_sfx_tracks step below; we also keep the raw value
            # on the editor scene for debugging and for future editor-UI surfacing.
            "sfx_hint": s.get("sfx_hint"),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        })

    # Compute cumulative timeline positions
    cumulative = 0
    for es in editor_scenes:
        es["timestamp"] = cumulative
        cumulative += es["duration"]

    # Build audio tracks
    audio_tracks = []
    audio_url = _resolve_audio_url(source_folder)
    if audio_url:
        audio_tracks.append({
            "id": "at_1",
            "label": "Voice",
            "type": "voice",
            "file": audio_url["source_file"],
            "path": audio_url["url"],
            "duration": 0,
            "timelineOffset": 0,
            "startOffset": 0,
            "trimmedDuration": None,
            "volume": 1,
            "loop": False,
            "muted": False,
            "duckingEnabled": False,
            "duckingLevel": 0.2,
            "fadeIn": 0,
            "fadeOut": 0,
        })

    music_history = []
    sfx_history = []
    initial_path = _initial_path(safe_id)
    if os.path.isfile(initial_path):
        try:
            existing_initial = safe_json_read(initial_path)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.debug("Could not read existing initial.json for {}: {}", safe_id, e)
            existing_initial = {}
        if isinstance(existing_initial, dict):
            music_history = list(existing_initial.get("music_history") or [])
            sfx_history = list(existing_initial.get("sfx_history") or [])

    # Auto-select background music + ambient SFX based on story tone.
    # Track order is preserved by insertion order: voice → music → sfx.
    story_tone = _get_story_tone(safe_id)
    if story_tone:
        try:
            from studio.music.selector import select_music, select_sfx
            bg_music = select_music(story_tone, history=music_history)
            if bg_music:
                music_history = list(bg_music.get("history") or music_history)
                # Music files live under APP_ASSETS_DIR/sounds/music/<folder>/<file>.
                # Build a Flask-servable /assets/... URL the same way
                # /api/music/auto-select does so the editor + renderer both
                # resolve it. The folder is the immediate parent of the file.
                music_abs = bg_music["path"]
                music_file = os.path.basename(music_abs)
                music_folder = os.path.basename(os.path.dirname(music_abs))
                music_url = f"/assets/sounds/music/{music_folder}/{music_file}" if music_folder else f"/assets/sounds/music/{music_file}"
                audio_tracks.append({
                    "id": "at_music_1",
                    "label": "Music",
                    "type": "music",
                    "file": music_file,
                    "path": music_url,
                    "duration": 0,
                    "timelineOffset": 0,
                    "startOffset": 0,
                    "trimmedDuration": None,
                    "volume": bg_music.get("volume", 0.15),
                    "loop": bg_music.get("loop", True),
                    "muted": False,
                    "duckingEnabled": bg_music.get("ducking_enabled", True),
                    "duckingLevel": bg_music.get("ducking_level", 0.2),
                    "fadeIn": bg_music.get("fade_in", 2.0),
                    "fadeOut": bg_music.get("fade_out", 3.0),
                })
                logger.info("Auto-selected bgMusic for tone '{}' → '{}'",
                            story_tone, music_file)

            sfx = select_sfx(story_tone, history=sfx_history)
            if sfx:
                sfx_history = list(sfx.get("history") or sfx_history)
                # Build a /assets/sounds/sfx/<folder>/<file> URL — keep the
                # folder so the editor can resolve it the same way the SFX
                # library endpoint does.
                sfx_file = os.path.basename(sfx["path"])
                sfx_folder = sfx.get("folder") or os.path.basename(os.path.dirname(sfx["path"]))
                sfx_url = f"/assets/sounds/sfx/{sfx_folder}/{sfx_file}" if sfx_folder else f"/assets/sounds/sfx/{sfx_file}"
                audio_tracks.append({
                    "id": "at_sfx_1",
                    "label": "SFX",
                    "type": "sfx",
                    "file": sfx_file,
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
                logger.info("Auto-selected SFX for tone '{}' → '{}'",
                            story_tone, sfx_file)
        except Exception as e:
            logger.debug("Could not auto-select bgMusic/SFX for {}: {}", safe_id, e)

    # Per-scene SFX placement based on validated sfx_hint fields from the
    # scene planner. Runs AFTER the tone-driven music + SFX bed so the per-scene
    # accents layer ON TOP of the ambient bed without competing with the bed's
    # tone-matching. The bed is the atmosphere layer; these are the punctuation
    # layer. Both can coexist with ducking handling the voice mix.
    try:
        scene_sfx_tracks, sfx_history = _build_per_scene_sfx_tracks(
            editor_scenes, raw_scenes, sfx_history,
        )
        if scene_sfx_tracks:
            audio_tracks.extend(scene_sfx_tracks)
            logger.info("Built {} per-scene SFX track(s) for {}", len(scene_sfx_tracks), safe_id)
    except Exception as e:
        logger.warning("Could not build per-scene SFX tracks for {}: {}", safe_id, e)

    total_duration = sum(s["duration"] for s in editor_scenes)
    editor_data = {
        "project_id": safe_id,
        "project_name": scenes_data.get("project_name", safe_id),
        "source_folder": source_folder,
        "style": scenes_data.get("style", ""),
        "total_duration": total_duration,
        "scene_count": len(editor_scenes),
        "scenes": editor_scenes,
        "audio_tracks": audio_tracks,
        "music_history": music_history,
        "sfx_history": sfx_history,
        "grain_overlay": {
            "enabled": False,
            "opacity": 0.16,
            "start": 0,
            "fade_in": 0,
            "hold": 0,
            "fade_out": 0,
            "noise_strength": 88,
            "threshold": 246,
        },
        "captionsEnabled": False,
        "edit_history": [],
        "history_index": -1,
        "disabled_tracks": [],
    }

    # Resolve captions — auto-generate from alignment if none exist
    _resolve_project_captions(editor_data, safe_id)
    _cap = editor_data.get("captions") or {}
    _has_entries = bool(_cap.get("entries") or _cap.get("captions"))
    if _has_entries:
        editor_data["captionsEnabled"] = True
    if not _has_entries and source_folder:
        try:
            from studio.captions.routes import (
                _get_default_caption_preset_id,
                _group_words_into_captions,
                CAPTION_PRESETS,
            )
            align_path = os.path.join(ALIGN_DIR, source_folder, "alignment.json")
            if os.path.isfile(align_path):
                alignment_raw = safe_json_read(align_path)
                # alignment.json may be a dict with word_alignment key or a plain list
                if isinstance(alignment_raw, dict):
                    alignment = alignment_raw.get("word_alignment") or alignment_raw.get("alignment") or []
                elif isinstance(alignment_raw, list):
                    alignment = alignment_raw
                else:
                    alignment = []
                if alignment:
                    captions = _group_words_into_captions(alignment, words_per_group=3)
                    if captions:
                        preset_id = _get_default_caption_preset_id()
                        style = dict(CAPTION_PRESETS.get(preset_id, CAPTION_PRESETS.get("bold_popup", {})))
                        style["preset"] = preset_id
                        captions_result = {
                            "project_id": safe_id,
                            "source_folder": source_folder,
                            "captions": captions,
                            "style": style,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                        }
                        # Save for future use
                        cap_dir = os.path.join(CAPTIONS_DIR, safe_id)
                        os.makedirs(cap_dir, exist_ok=True)
                        safe_json_write(os.path.join(cap_dir, "captions.json"), captions_result, indent=2)
                        editor_data["captions"] = captions_result
                        editor_data["captionsEnabled"] = True
                        logger.info("Auto-generated {} captions for {}", len(captions), safe_id)
        except Exception as e:
            logger.debug("Could not auto-generate captions for {}: {}", safe_id, e)

    # Save as initial.json in output/projects/{id}/
    editor_data["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    proj_dir = _project_dir(safe_id)
    os.makedirs(proj_dir, exist_ok=True)
    safe_json_write(os.path.join(proj_dir, INITIAL_FILENAME), editor_data, indent=2)

    logger.info("Assembled editor project for {}", safe_id)

    editor_data["_source"] = "initial"
    return jsonify(editor_data)


@editor_bp.route("/api/editor/reset/<project_id>", methods=["POST"])
def editor_reset_to_initial(project_id):
    """Delete the WIP file and fall back to the mirrored initial project file."""
    safe_id = "".join(c for c in project_id if c.isalnum() or c in ("_", "-"))


    initial = _initial_path(safe_id)
    if not os.path.isfile(initial):
        return jsonify({"error": "No initial state found"}), 404

    wip = _wip_path(safe_id)
    deleted = False
    if os.path.isfile(wip):
        os.remove(wip)
        deleted = True
        logger.info("WIP file deleted for project {}", safe_id)

    return jsonify({"ok": True, "deleted_wip": deleted})


# ---------------------------------------------------------------------------
# Project ZIP export
# ---------------------------------------------------------------------------

@editor_bp.route("/api/editor/export-zip/<project_id>", methods=["GET"])
def export_project_zip(project_id):
    """Bundle a complete project into a downloadable ZIP file."""
    from datetime import datetime, timezone

    safe_id = "".join(c for c in project_id if c.isalnum() or c in ("_", "-"))


    # Prefer WIP file, then initial state, then scenes.json
    wip_file = _wip_path(safe_id)
    initial_file = _initial_path(safe_id)
    editor_path = wip_file if os.path.isfile(wip_file) else initial_file
    scenes_path = os.path.join(SCENES_DIR, safe_id, "scenes.json")
    if not os.path.isfile(editor_path) and not os.path.isfile(scenes_path):
        return jsonify({"error": "Project not found"}), 404

    source_folder = _get_source_folder(safe_id)
    manifest = {
        "project_id": safe_id,
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_folder": source_folder or "",
        "files": [],
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        prefix = f"{safe_id}/"

        # 1) Editor save JSON
        if os.path.isfile(editor_path):
            zf.write(editor_path, f"{prefix}project.json")
            manifest["files"].append("project.json")

        # 2) Scenes JSON
        if os.path.isfile(scenes_path):
            zf.write(scenes_path, f"{prefix}scenes.json")
            manifest["files"].append("scenes.json")

        # 3) Assets — all media files under output/animator/{project_id}/
        assets_dir = os.path.join(ANIMATOR_DIR, safe_id)
        if os.path.isdir(assets_dir):
            for root, _dirs, files in os.walk(assets_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    rel = os.path.relpath(fpath, assets_dir).replace("\\", "/")
                    arc_name = f"{prefix}assets/{rel}"
                    zf.write(fpath, arc_name)
                    manifest["files"].append(f"assets/{rel}")

        # 4) Audio — alignment files
        if source_folder:
            align_dir = os.path.join(ALIGN_DIR, source_folder)
            if os.path.isdir(align_dir):
                try:
                    for fname in os.listdir(align_dir):
                        fpath = os.path.join(align_dir, fname)
                        if os.path.isfile(fpath):
                            zf.write(fpath, f"{prefix}audio/{fname}")
                            manifest["files"].append(f"audio/{fname}")
                except OSError:
                    pass

            # 5) TTS files
            tts_dir = os.path.join(TTS_DIR, source_folder)
            if os.path.isdir(tts_dir):
                try:
                    for fname in os.listdir(tts_dir):
                        fpath = os.path.join(tts_dir, fname)
                        if os.path.isfile(fpath):
                            zf.write(fpath, f"{prefix}tts/{fname}")
                            manifest["files"].append(f"tts/{fname}")
                except OSError:
                    pass

        # 6) Manifest
        zf.writestr(f"{prefix}manifest.json", json.dumps(manifest, indent=2))

    buf.seek(0)
    logger.info("Project ZIP exported: {} ({} files, {:.1f} MB)",
                safe_id, len(manifest["files"]), buf.getbuffer().nbytes / 1024 / 1024)

    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{safe_id}.zip",
    )


def _coerce_imported_editor_project(raw_bytes: bytes, project_id: str, renamed_from: str | None = None) -> dict:
    """Validate and normalize imported editor project payload before saving."""
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid project.json payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid project.json payload: expected JSON object")

    payload["project_id"] = project_id
    project_name = str(payload.get("project_name", "") or "").strip()
    if not project_name or (renamed_from and project_name == renamed_from):
        payload["project_name"] = project_id

    EditorSaveRequest.model_validate(payload)
    return payload


@editor_bp.route("/api/editor/import-zip", methods=["POST"])
def import_project_zip():
    """Import a project from an uploaded ZIP file."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    zfile = request.files["file"]
    if not zfile.filename or not zfile.filename.lower().endswith(".zip"):
        return jsonify({"error": "File must be a .zip"}), 400

    try:
        data = zfile.read()
        zio = io.BytesIO(data)
        with zipfile.ZipFile(zio, "r") as zf:
            names = zf.namelist()
            if not names:
                return jsonify({"error": "ZIP is empty"}), 400

            # Detect project_id from manifest or top-level folder
            project_id = None
            manifest = None
            for n in names:
                if n.endswith("manifest.json"):
                    manifest = json.loads(zf.read(n))
                    project_id = manifest.get("project_id")
                    break
            if not project_id:
                # Infer from first path component
                project_id = names[0].split("/")[0]

            safe_id = sanitize_project_id(project_id)
            if not safe_id:
                return jsonify({"error": "Cannot determine project ID from ZIP"}), 400

            # Validate: ZIP must contain at least scenes.json or project.json
            has_scenes = any(n.endswith("scenes.json") for n in names)
            has_project = any(n.endswith("project.json") for n in names)
            if not has_scenes and not has_project:
                return jsonify({"error": "Invalid project ZIP: missing scenes.json and project.json"}), 400

            # Handle duplicate project IDs — append -2, -3, etc.
            original_id = safe_id
            renamed_from = None
            scenes_dir_check = os.path.join(SCENES_DIR, safe_id)
            editor_dir_check = _project_dir(safe_id)
            if os.path.exists(scenes_dir_check) or os.path.isdir(editor_dir_check):
                suffix = 2
                while True:
                    candidate = f"{original_id}-{suffix}"
                    if not os.path.exists(os.path.join(SCENES_DIR, candidate)) and \
                       not os.path.isdir(_project_dir(candidate)):
                        renamed_from = safe_id
                        safe_id = candidate
                        break
                    suffix += 1
                logger.info("Project {} already exists, renamed to {}", original_id, safe_id)

            source_folder = sanitize_folder_name(manifest.get("source_folder", "") if manifest else "")
            prefix = f"{original_id}/"

            # Extract each file to its correct output location
            imported = []
            for name in names:
                if name.endswith("/"):
                    continue  # skip directories

                # Strip the project prefix to get relative path
                rel = name[len(prefix):] if name.startswith(prefix) else name
                raw = zf.read(name)

                if rel == "project.json":
                    proj_dir = _project_dir(safe_id)
                    os.makedirs(proj_dir, exist_ok=True)
                    try:
                        project_payload = _coerce_imported_editor_project(
                            raw,
                            safe_id,
                            renamed_from=renamed_from,
                        )
                    except ValueError as exc:
                        return jsonify({"error": str(exc)}), 400
                    dest = _initial_path(safe_id)
                    safe_json_write(dest, project_payload, indent=2)
                    imported.append(rel)

                elif rel == "scenes.json":
                    dest_dir = os.path.join(SCENES_DIR, safe_id)
                    os.makedirs(dest_dir, exist_ok=True)
                    with open(os.path.join(dest_dir, "scenes.json"), "wb") as f:
                        f.write(raw)
                    imported.append(rel)

                elif rel.startswith("assets/"):
                    sub = rel[len("assets/"):]
                    try:
                        dest = safe_join(os.path.join(ANIMATOR_DIR, safe_id), sub)
                    except ValueError:
                        return jsonify({"error": "Invalid ZIP path in assets"}), 400
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as f:
                        f.write(raw)
                    imported.append(rel)

                elif rel.startswith("audio/") and source_folder:
                    sub = rel[len("audio/"):]
                    try:
                        dest = safe_join(os.path.join(ALIGN_DIR, source_folder), sub)
                    except ValueError:
                        return jsonify({"error": "Invalid ZIP path in audio"}), 400
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as f:
                        f.write(raw)
                    imported.append(rel)

                elif rel.startswith("tts/") and source_folder:
                    sub = rel[len("tts/"):]
                    try:
                        dest = safe_join(os.path.join(TTS_DIR, source_folder), sub)
                    except ValueError:
                        return jsonify({"error": "Invalid ZIP path in tts"}), 400
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as f:
                        f.write(raw)
                    imported.append(rel)

            # If renamed, update project_id inside scenes.json and project.json
            if renamed_from:
                scenes_json_path = os.path.join(SCENES_DIR, safe_id, "scenes.json")
                if os.path.exists(scenes_json_path):
                    try:
                        sdata = safe_json_read(scenes_json_path)
                        sdata["project_id"] = safe_id
                        safe_json_write(scenes_json_path, sdata, indent=2)
                    except Exception as error:
                        logger.debug("Could not update imported scenes.json {}: {}", scenes_json_path, error)
                editor_json_path = _initial_path(safe_id)
                if os.path.exists(editor_json_path):
                    try:
                        edata = safe_json_read(editor_json_path)
                        edata["project_id"] = safe_id
                        project_name = str(edata.get("project_name", "") or "").strip()
                        if not project_name or project_name == renamed_from:
                            edata["project_name"] = safe_id
                        EditorSaveRequest.model_validate(edata)
                        safe_json_write(editor_json_path, edata, indent=2)
                    except Exception as error:
                        logger.debug("Could not update imported editor manifest {}: {}", editor_json_path, error)

            logger.info("Project ZIP imported: {} ({} files){}", safe_id, len(imported),
                        f" (renamed from {renamed_from})" if renamed_from else "")
            result = {
                "project_id": safe_id,
                "imported_files": len(imported),
                "source_folder": source_folder,
            }
            if renamed_from:
                result["renamed_from"] = renamed_from
            return jsonify(result)

    except zipfile.BadZipFile:
        return jsonify({"error": "Invalid ZIP file"}), 400
    except Exception as e:
        logger.error("ZIP import failed: {}", e)
        return jsonify({"error": str(e)}), 500


@editor_bp.route("/api/editor/open-folder/<project_id>", methods=["POST"])
def open_project_folder(project_id):
    """Open the project's assets folder in the OS file explorer."""
    safe_id = "".join(c for c in project_id if c.isalnum() or c in ("_", "-"))

    # Try assets dir first, then editor save dir
    folder = os.path.join(ANIMATOR_DIR, safe_id)
    if not os.path.isdir(folder):
        folder = os.path.join(SCENES_DIR, safe_id)
    if not os.path.isdir(folder):
        return jsonify({"error": "Project folder not found"}), 404

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
        logger.error("Failed to open project folder: {}", e)
        return jsonify({"error": str(e)}), 500


OVERLAYS_DIR = os.path.join(APP_ASSETS_DIR, "overlays")


@editor_bp.route("/api/editor/overlays", methods=["GET"])
def list_overlays():
    """List available overlay PNGs from assets/overlays/."""
    overlays = []
    if os.path.isdir(OVERLAYS_DIR):
        for f in sorted(os.listdir(OVERLAYS_DIR)):
            if f.lower().endswith(".png"):
                name = os.path.splitext(f)[0]
                overlays.append({"name": name, "file": f, "url": f"/assets/overlays/{f}"})
    return jsonify(overlays)


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------

# Legacy route — editor is now inlined in static/ (Phase 1 merge).
# Kept as redirect for any stale bookmarks or cached references.
@editor_bp.route("/timeline-editor/<path:filename>")
def serve_timeline_editor(filename):
    """Redirect old timeline-editor paths to static/."""
    from flask import redirect
    return redirect(f"/static/{filename}", code=301)



# ---------------------------------------------------------------------------
# Font API
# ---------------------------------------------------------------------------

SYSTEM_FONTS = [
    'Arial', 'Helvetica', 'Georgia', 'Times New Roman', 'Verdana',
    'Trebuchet MS', 'Impact', 'Comic Sans MS', 'Courier New',
]


@editor_bp.route("/api/fonts", methods=["GET"])
def list_fonts():
    """Return combined list of custom + system fonts."""
    fonts = []

    # Custom fonts from registry
    for family, entry in sorted(FONT_REGISTRY.items()):
        variants = {}
        for variant, abs_path in entry['variants'].items():
            variants[variant] = get_font_url(abs_path)
        fonts.append({
            'family': family,
            'source': 'custom',
            'variants': variants,
        })

    # System fonts (no variant URLs — browser resolves them)
    for family in SYSTEM_FONTS:
        fonts.append({
            'family': family,
            'source': 'system',
            'variants': {},
        })

    logger.debug("Font API: {} custom + {} system fonts", len(FONT_REGISTRY), len(SYSTEM_FONTS))
    return jsonify(fonts)


# ---------------------------------------------------------------------------
# Frontend log relay — POST /api/log
# ---------------------------------------------------------------------------

@editor_bp.route("/api/log", methods=["POST"])
def frontend_log():
    """Receive log messages from the frontend and emit via loguru."""
    data = request.get_json(silent=True) or {}
    level = (data.get("level") or "info").upper()
    msg = data.get("message", "")
    ctx = data.get("context", "")
    source = data.get("source", "frontend")

    tag = f"[{source}]"
    full = f"{tag} {msg}" + (f" | {ctx}" if ctx else "")

    if level == "ERROR":
        logger.error(full)
    elif level == "WARNING" or level == "WARN":
        logger.warning(full)
    elif level == "DEBUG":
        logger.debug(full)
    else:
        logger.info(full)

    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Export API
# ---------------------------------------------------------------------------

@editor_bp.route("/api/export", methods=["POST"])
@validate_json(ExportRequest)
def start_export(data: ExportRequest):
    """Start a video export job."""
    try:
        export_data = data.model_dump(exclude_none=True)

        job_id = str(uuid.uuid4())
        project_id = data.project_id
        scene_count = len(data.scenes)
        output_filename = f"{project_id}_{job_id[:8]}.mp4"
        output_path = os.path.join(EXPORT_DIR, output_filename)

        logger.info("Export started — job={} project={} scenes={} output={}",
                     job_id[:8], project_id, scene_count, output_filename)

        # Log export settings
        output_cfg = export_data.get("output", {})
        res = output_cfg.get("resolution", {}) if isinstance(output_cfg, dict) else {}
        logger.debug("Export settings: {}x{} {}fps crf={} codec={}",
                      res.get("width", "?"), res.get("height", "?"),
                      output_cfg.get("fps", "?"), output_cfg.get("crf", "?"),
                      output_cfg.get("codec", "?"))

        audio_cfg = export_data.get("audio")
        if audio_cfg and audio_cfg.get("path"):
            logger.debug("Audio: path={} vol={}",
                          audio_cfg.get("path"), audio_cfg.get("volume", 1.0))
        else:
            logger.debug("Audio: none")

        bg_music = export_data.get("bgMusic")
        if bg_music:
            logger.debug("BgMusic: path={} vol={} loop={} ducking={}",
                          bg_music.get("path"), bg_music.get("volume"),
                          bg_music.get("loop"), bg_music.get("ducking_enabled"))

        captions = export_data.get("captions", {})
        cap_entries = captions.get("entries", []) if isinstance(captions, dict) else []
        if cap_entries:
            logger.debug("Captions: {} entries", len(cap_entries))

        # Log scene summary
        for i, sc in enumerate(export_data.get("scenes", [])):
            media = sc.get("media", {}) if isinstance(sc, dict) else {}
            effect = sc.get("effect", {}) if isinstance(sc, dict) else {}
            logger.debug("  Scene {}: type={} dur={}s effect={} path={}",
                          i + 1, media.get("type", "?"), sc.get("duration", "?") if isinstance(sc, dict) else "?",
                          effect.get("type", "static"),
                          (media.get("path") or "n/a")[:60])

        _cleanup_old_export_jobs()

        with _export_jobs_lock:
            _export_jobs[job_id] = {
                "status": "queued",
                "progress": 0,
                "message": "Job queued",
                "step": None,
                "output_path": output_path,
                "output_filename": output_filename,
                "project_id": project_id,
                "scene_count": scene_count,
                "error": None,
                "created_at": time.time(),
                "completed_at": None,
            }

        thread = threading.Thread(
            target=_process_video,
            args=(job_id, export_data, output_path),
            daemon=True,
        )
        thread.start()

        return jsonify({"job_id": job_id, "status": "queued", "message": "Export job started"})

    except Exception as e:
        logger.exception("Export start error")
        return jsonify({"error": str(e)}), 500


def _process_video(job_id, export_data, output_path):
    """Process video in background thread with step-level error tracking."""
    short_id = job_id[:8]
    with _export_jobs_lock:
        job = _export_jobs.get(job_id)
    if job is None:
        logger.warning("[{}] Export job disappeared before processing started", short_id)
        return

    def _set_step(step, message):
        job["step"] = step
        job["message"] = message
        logger.debug("[{}] Step: {} — {}", short_id, step, message)

    def _metadata_path():
        base, _ext = os.path.splitext(output_path)
        return base + ".json"

    try:
        # Import here to avoid circular imports at module load
        from studio.editor.video_processor import VideoProcessor

        logger.info("[{}] Processing started", short_id)
        job["status"] = "processing"
        _set_step("init", "Starting video processing")

        def update_progress(progress, message):
            if job.get("status") == "cancelled":
                raise ExportCancelled("Export cancelled by user")
            job["progress"] = progress
            job["message"] = message
            # Infer step from progress ranges set by VideoProcessor
            if progress < 80:
                job["step"] = "scenes"
            elif progress < 85:
                job["step"] = "concat"
            elif progress < 90:
                job["step"] = "overlay"
            elif progress < 100:
                job["step"] = "captions"
            logger.debug("[{}] Progress: {}% — {}", short_id, progress, message)

        processor = VideoProcessor(
            export_data=export_data,
            progress_callback=update_progress,
        )
        processor.process(output_path)

        if job.get("status") == "cancelled":
            raise ExportCancelled("Export cancelled by user")

        # Verify output was actually created
        if not os.path.exists(output_path):
            raise RuntimeError("Export finished but output file is missing")

        file_size = os.path.getsize(output_path)
        if file_size == 0:
            os.remove(output_path)
            raise RuntimeError("Export produced an empty file")

        logger.success("[{}] Export completed — {} ({:.1f} MB)",
                       short_id, output_path, file_size / (1024 * 1024))

        # Derive aspect ratio from resolution
        _res = (export_data.get("output") or {}).get("resolution") or {}
        _w, _h = _res.get("width", 0), _res.get("height", 0)
        _ratio = f"{_w}:{_h}" if _w and _h else ""

        # Try to read style from the scenes project
        _style = ""
        project_id = export_data.get("project_id", "")
        if project_id:
            _scenes_json = os.path.join(SCENES_DIR, project_id, "scenes.json")
            try:
                if os.path.isfile(_scenes_json):
                    _sdata = safe_json_read(_scenes_json)
                    _style = _sdata.get("style", "")
            except Exception as error:
                logger.debug("Could not read style metadata from {}: {}", _scenes_json, error)

        # Probe exported video for duration and dimensions
        _probe = _ffprobe_video(output_path)
        scene_count = len(export_data.get("scenes", []))

        export_audio_summary = {
            "narration": export_data.get("audio") if isinstance(export_data.get("audio"), dict) else None,
            "bg_music": export_data.get("bgMusic") if isinstance(export_data.get("bgMusic"), dict) else None,
            "sfx": export_data.get("sfx") if isinstance(export_data.get("sfx"), dict) else None,
        }

        safe_json_write(os.path.splitext(output_path)[0] + ".json", {
            "job_id": job_id,
            "project_id": job.get("project_id", ""),
            "output_filename": job.get("output_filename", ""),
            "completed_at": time.time(),
            "scene_count": scene_count,
            "style": _style,
            "ratio": _ratio,
            "duration": _probe.get("duration", 0),
            "width": _probe.get("width", 0),
            "height": _probe.get("height", 0),
            "export_audio": export_audio_summary,
        }, indent=2)

        safe_json_write(_metadata_path(), {
            "job_id": job_id,
            "project_id": job.get("project_id", ""),
            "output_filename": job.get("output_filename", ""),
            "completed_at": time.time(),
        }, indent=2)

        job["status"] = "completed"
        job["progress"] = 100
        job["step"] = "done"
        job["message"] = "Export completed successfully"
        job["completed_at"] = time.time()

        # Auto-sync to folder if enabled
        try:
            _auto_sync_after_export(job.get("output_filename", ""), output_path)
        except Exception as sync_err:
            logger.warning("[{}] Auto-sync failed: {}", short_id, sync_err)

    except ExportCancelled as e:
        logger.info("[{}] Export cancelled", short_id)

        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                logger.debug("[{}] Removed cancelled output: {}", short_id, output_path)
            except OSError as rm_err:
                logger.warning("[{}] Could not remove cancelled output: {}", short_id, rm_err)
        meta_path = _metadata_path()
        if os.path.exists(meta_path):
            try:
                os.remove(meta_path)
            except OSError as error:
                logger.debug("Could not remove cancelled metadata {}: {}", meta_path, error)

        job["status"] = "cancelled"
        job["error"] = None
        job["message"] = str(e)
        job["completed_at"] = time.time()

    except Exception as e:
        logger.error("[{}] Export FAILED at step '{}': {}", short_id, job.get("step"), e)
        logger.debug("[{}] Traceback:\n{}", short_id, traceback.format_exc())

        # Clean up partial output file
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                logger.debug("[{}] Removed partial output: {}", short_id, output_path)
            except OSError as rm_err:
                logger.warning("[{}] Could not remove partial output: {}", short_id, rm_err)
        meta_path = _metadata_path()
        if os.path.exists(meta_path):
            try:
                os.remove(meta_path)
            except OSError as error:
                logger.debug("Could not remove failed metadata {}: {}", meta_path, error)

        failed_step = job.get("step") or "unknown"
        job["status"] = "failed"
        job["error"] = str(e)
        job["step"] = failed_step
        job["message"] = f"Export failed during {failed_step}: {e}"
        job["completed_at"] = time.time()


@editor_bp.route("/api/export/<job_id>/status", methods=["GET"])
def get_export_status(job_id):
    """Get status of an export job."""
    with _export_jobs_lock:
        job = _export_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "step": job.get("step"),
        "error": job["error"],
    })


@editor_bp.route("/api/export/<job_id>/download", methods=["GET"])
def download_export(job_id):
    """Download completed export."""
    with _export_jobs_lock:
        job = _export_jobs.get(job_id)
    if not job:
        logger.warning("Download request for unknown job: {}", job_id[:8])
        return jsonify({"error": "Job not found"}), 404

    if job["status"] != "completed":
        logger.warning("Download attempt on non-completed job: {} (status={})", job_id[:8], job["status"])
        return jsonify({"error": "Export not completed yet"}), 400
    if not os.path.exists(job["output_path"]):
        logger.error("Download file missing: {}", job["output_path"])
        return jsonify({"error": "Output file not found"}), 404

    logger.info("Serving download: {}", job["output_filename"])
    return send_file(
        job["output_path"],
        mimetype="video/mp4",
        as_attachment=True,
        download_name=job["output_filename"],
    )


@editor_bp.route("/api/export/<job_id>/preview", methods=["GET"])
def preview_export(job_id):
    """Preview completed export in browser."""
    with _export_jobs_lock:
        job = _export_jobs.get(job_id)
    if not job:
        logger.warning("Preview request for unknown job: {}", job_id[:8])
        return jsonify({"error": "Job not found"}), 404

    if job["status"] != "completed":
        logger.warning("Preview attempt on non-completed job: {} (status={})", job_id[:8], job["status"])
        return jsonify({"error": "Export not completed yet"}), 400
    if not os.path.exists(job["output_path"]):
        logger.error("Preview file missing: {}", job["output_path"])
        return jsonify({"error": "Output file not found"}), 404

    logger.info("Serving preview: {}", job["output_filename"])
    return send_file(
        job["output_path"],
        mimetype="video/mp4",
        as_attachment=False,
    )


@editor_bp.route("/api/export/library", methods=["GET"])
def export_library_list():
    """List exported videos from output/exports recursively."""
    if not os.path.isdir(EXPORT_DIR):
        return jsonify({"items": []})

    from datetime import datetime, timezone
    from urllib.parse import quote

    video_exts = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
    items = []

    def _normalize_completed_at(value):
        """Normalize export completion stamps to ISO strings."""
        if value in (None, ""):
            return ""
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        if isinstance(value, str):
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
            except (TypeError, ValueError):
                return value
        return ""

    for root, _dirs, files in os.walk(EXPORT_DIR):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in video_exts:
                continue

            abs_video = os.path.join(root, fname)
            rel_video = os.path.relpath(abs_video, EXPORT_DIR).replace("\\", "/")
            rel_folder = os.path.relpath(root, EXPORT_DIR).replace("\\", "/")
            base = os.path.splitext(fname)[0]
            folder_project_id = _safe_project_id(os.path.basename(root))
            meta_path = os.path.splitext(abs_video)[0] + ".json"
            project_id = ""
            meta_style = ""
            meta_ratio = ""
            meta_scene_count = 0
            meta_duration = 0
            meta_width = 0
            meta_height = 0
            meta_completed_at = ""
            meta_dirty = False  # whether sidecar needs update
            if os.path.isfile(meta_path):
                try:
                    meta = safe_json_read(meta_path)
                    project_id = _safe_project_id(meta.get("project_id", ""))
                    meta_style = meta.get("style", "")
                    meta_ratio = meta.get("ratio", "")
                    meta_scene_count = meta.get("scene_count", 0)
                    meta_duration = meta.get("duration", 0)
                    meta_width = meta.get("width", 0)
                    meta_height = meta.get("height", 0)
                    meta_completed_at = _normalize_completed_at(meta.get("completed_at"))
                except Exception as error:
                    logger.debug("Could not read export metadata {}: {}", meta_path, error)
                    project_id = ""

            # Probe video if duration/dimensions are missing
            if not meta_duration or not meta_width:
                probe = _ffprobe_video(abs_video)
                if probe:
                    if not meta_duration and probe.get("duration"):
                        meta_duration = probe["duration"]
                        meta_dirty = True
                    if not meta_width and probe.get("width"):
                        meta_width = probe["width"]
                        meta_height = probe.get("height", 0)
                        meta_dirty = True

            # Build video_ratio from actual dimensions
            video_ratio = ""
            if meta_width and meta_height:
                video_ratio = f"{meta_width}:{meta_height}"

            # Cache probe results into sidecar
            if meta_dirty and meta_path:
                try:
                    existing = safe_json_read(meta_path) if os.path.isfile(meta_path) else {}
                    existing["duration"] = meta_duration
                    existing["width"] = meta_width
                    existing["height"] = meta_height
                    safe_json_write(meta_path, existing, indent=2)
                except Exception as error:
                    logger.debug("Could not update export metadata {}: {}", meta_path, error)
            if not project_id:
                match = re.match(r"^(?P<project>.+)_[0-9a-fA-F]{8}$", base)
                if match:
                    project_id = _safe_project_id(match.group("project"))
            if not project_id:
                project_id = folder_project_id or _safe_project_id(base)

            # Pair ZIP by same filename in the same folder, fallback to generated project ZIP.
            zip_name = f"{base}.zip"
            abs_zip = os.path.join(root, zip_name)
            zip_exists = os.path.isfile(abs_zip)
            zip_rel = os.path.relpath(abs_zip, EXPORT_DIR).replace("\\", "/") if zip_exists else ""

            mtime = os.path.getmtime(abs_video)
            mtime_iso = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            video_q = quote(rel_video, safe="/")
            zip_q = quote(zip_rel, safe="/") if zip_exists else ""

            # Read scenes.json for style, scene count, and pipeline timing
            pid = project_id or base
            pipeline_timing = {}
            source_folder = ""
            if not meta_style or not pipeline_timing:
                try:
                    _sp = os.path.join(SCENES_DIR, pid, "scenes.json")
                    if os.path.isfile(_sp):
                        _sd = safe_json_read(_sp)
                        if not meta_style:
                            meta_style = _sd.get("style", "")
                        if not meta_scene_count:
                            meta_scene_count = len(_sd.get("scenes", []))
                        source_folder = _sd.get("source_folder", "")
                        pipeline_timing = _sd.get("pipeline_timing", {})
                except Exception as error:
                    logger.debug("Could not read scene metadata: {}", error)

            project_name = ""
            project_total_duration = 0
            audio_track_count = 0
            caption_count = 0
            has_captions = False
            media_counts = {"video": 0, "image": 0, "text": 0}
            try:
                _project_json = _initial_path(pid)
                if os.path.isfile(_project_json):
                    _pdata = safe_json_read(_project_json)
                    project_name = _pdata.get("project_name", "")
                    source_folder = source_folder or _pdata.get("source_folder", "")
                    project_total_duration = _pdata.get("total_duration", 0)
                    audio_track_count = len(_pdata.get("audio_tracks") or [])

                    _captions = _pdata.get("captions") or {}
                    _caption_entries = []
                    if isinstance(_captions, dict):
                        _caption_entries = _captions.get("entries")
                        if not isinstance(_caption_entries, list):
                            _caption_entries = _captions.get("captions", [])
                    caption_count = len(_caption_entries or [])
                    has_captions = bool(_pdata.get("captionsEnabled") or caption_count)

                    for scene in _pdata.get("scenes") or []:
                        if not isinstance(scene, dict):
                            continue
                        scene_type = str(scene.get("type", "")).lower()
                        if scene_type in media_counts:
                            media_counts[scene_type] += 1
                            continue
                        if scene.get("isVideo"):
                            media_counts["video"] += 1
                        else:
                            media_counts["image"] += 1
            except Exception as error:
                logger.debug("Could not read project metadata: {}", error)

            completed_at = meta_completed_at or mtime_iso
            resolution_label = f"{meta_width}x{meta_height}" if meta_width and meta_height else ""

            items.append({
                "project_id": pid,
                "project_name": project_name or pid,
                "video_name": fname,
                "video_relpath": rel_video,
                "folder_relpath": rel_folder if rel_folder != "." else "",
                "size_bytes": os.path.getsize(abs_video),
                "modified_at": mtime_iso,
                "completed_at": completed_at,
                "preview_url": f"/api/export/library/preview/{video_q}",
                "video_download_url": f"/api/export/library/download/{video_q}",
                "zip_download_url": (f"/api/export/library/download/{zip_q}" if zip_exists else (f"/api/editor/export-zip/{pid}" if pid else "")),
                "zip_source": ("file" if zip_exists else "generated"),
                "style": meta_style,
                "ratio": meta_ratio,
                "video_ratio": video_ratio,
                "duration": meta_duration,
                "project_total_duration": project_total_duration or meta_duration,
                "scene_count": meta_scene_count,
                "source_folder": source_folder,
                "width": meta_width,
                "height": meta_height,
                "resolution_label": resolution_label,
                "media_counts": media_counts,
                "audio_track_count": audio_track_count,
                "caption_count": caption_count,
                "has_captions": has_captions,
                "pipeline_timing": pipeline_timing,
            })

    items.sort(key=lambda it: it.get("modified_at", ""), reverse=True)
    return jsonify({"items": items, "count": len(items)})


@editor_bp.route("/api/export/library/prompts/<project_id>", methods=["GET"])
def export_library_prompts(project_id):
    """Return scene-level prompt details for analytics / prompt inspection."""
    from studio.security import sanitize_project_id
    pid = sanitize_project_id(project_id)

    result = {"project_id": pid, "style": "", "style_name": "", "style_description": "", "style_prompt": "", "style_color": "", "scenes": []}

    # Read scenes.json
    scenes_path = os.path.join(SCENES_DIR, pid, "scenes.json")
    if os.path.isfile(scenes_path):
        sd = safe_json_read(scenes_path)
        result["style"] = sd.get("style", "")

    # Read initial.json for full scene data
    initial_path = _initial_path(pid)
    if os.path.isfile(initial_path):
        pd = safe_json_read(initial_path)
        result["style"] = result["style"] or pd.get("style", "")
        for i, s in enumerate(pd.get("scenes") or []):
            if not isinstance(s, dict):
                continue
            result["scenes"].append({
                "index": i,
                "script": s.get("script", ""),
                "image_prompt": s.get("image_prompt", s.get("prompt", "")),
                "narrative_role": s.get("narrative_role", ""),
                "duration": s.get("duration", 0),
                "visual_fx": s.get("visual_fx", ""),
                "scene_type": s.get("type", ""),
                "isVideo": s.get("isVideo", False),
            })

    # Resolve style template details
    if result["style"]:
        try:
            from studio.build_scene_blueprints.templates import TEMPLATES_BY_ID
            tmpl = TEMPLATES_BY_ID.get(result["style"])
            if tmpl:
                result["style_name"] = tmpl.get("name", "")
                result["style_description"] = tmpl.get("description", "")
                result["style_color"] = tmpl.get("color", "")
                from studio.build_scene_blueprints.style_compiler import normalize_template, compile_style_prompt
                normalized = normalize_template(tmpl)
                style_spec = normalized.get("style_spec", {})
                result["style_prompt"] = compile_style_prompt(style_spec, "")
        except Exception:
            pass

    # Read storyboard prompts if available
    storyboard_prompts_path = os.path.join(STORYBOARD_DIR, pid, "scene_prompts.json")
    if os.path.isfile(storyboard_prompts_path):
        try:
            sp = safe_json_read(storyboard_prompts_path)
            if isinstance(sp, list):
                for entry in sp:
                    idx = entry.get("scene", -1)
                    if 0 <= idx < len(result["scenes"]):
                        result["scenes"][idx]["storyboard_prompt"] = entry.get("prompt", "")
        except Exception:
            pass

    return jsonify(result)


@editor_bp.route("/api/export/library/trash", methods=["POST"])
def export_library_trash():
    """Move an exported video (and its sidecar .json / .zip) to output/TRASH."""
    data = request.get_json(silent=True) or {}
    rel_path = (data.get("video_relpath") or "").replace("\\", "/").strip("/")
    if not rel_path:
        return jsonify({"error": "Missing video_relpath"}), 400

    try:
        abs_video = _resolve_export_relpath(rel_path)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not os.path.isfile(abs_video):
        return jsonify({"error": "File not found"}), 404

    # Collect related files (sidecar .json and .zip with same base name)
    base_no_ext = os.path.splitext(abs_video)[0]
    files_to_move = [abs_video]
    for ext in (".json", ".zip"):
        sidecar = base_no_ext + ext
        if os.path.isfile(sidecar):
            files_to_move.append(sidecar)

    moved = []
    for fpath in files_to_move:
        fname = os.path.basename(fpath)
        dest = os.path.join(TRASH_DIR, fname)
        # Avoid overwriting: append timestamp if name collision
        if os.path.exists(dest):
            name, ext = os.path.splitext(fname)
            dest = os.path.join(TRASH_DIR, f"{name}_{int(time.time())}{ext}")
        shutil.move(fpath, dest)
        moved.append(os.path.basename(dest))
        logger.info("Trashed export file: {} → {}", fpath, dest)

    return jsonify({"status": "trashed", "moved": moved})


@editor_bp.route("/api/export/library/sync", methods=["GET"])
def export_library_sync():
    """SSE stream: copy exported videos to sync folder with per-file progress."""
    from flask import Response

    VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}

    cfg = _read_app_config()
    defaults = cfg.get("defaults", {})
    user_settings = cfg.get("user", {})
    sync_folder = (user_settings.get("sts-sync-folder") or defaults.get("sts-sync-folder") or "").strip()

    def _sse_error(msg):
        return Response(
            f"data: {json.dumps({'phase': 'error', 'message': msg})}\n\n",
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if not sync_folder:
        return _sse_error("No sync folder configured. Set it in Settings.")

    sync_folder = os.path.normpath(sync_folder)
    dest_dir = os.path.join(sync_folder, "exports")

    if not os.path.isdir(sync_folder):
        return _sse_error(f"Sync folder does not exist: {sync_folder}")

    os.makedirs(dest_dir, exist_ok=True)

    # Collect video files first
    video_files = []
    if os.path.isdir(EXPORT_DIR):
        for root, _dirs, files in os.walk(EXPORT_DIR):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in VIDEO_EXTS:
                    video_files.append((os.path.join(root, fname), fname))

    def _sse():
        total = len(video_files)
        copied = 0
        skipped = 0

        for idx, (src_path, fname) in enumerate(video_files):
            dest_path = os.path.join(dest_dir, fname)
            src_size = os.path.getsize(src_path)

            # Skip duplicate (same name + size)
            if os.path.isfile(dest_path) and os.path.getsize(dest_path) == src_size:
                skipped += 1
                yield f"data: {json.dumps({'phase': 'skip', 'file': fname, 'index': idx + 1, 'total': total})}\n\n"
                continue

            # Emit start event
            yield f"data: {json.dumps({'phase': 'copying', 'file': fname, 'size': src_size, 'index': idx + 1, 'total': total})}\n\n"

            shutil.copy2(src_path, dest_path)
            copied += 1
            logger.info("Synced export: {} → {}", fname, dest_dir)

            yield f"data: {json.dumps({'phase': 'copied', 'file': fname, 'index': idx + 1, 'total': total})}\n\n"

        yield f"data: {json.dumps({'phase': 'done', 'copied': copied, 'skipped': skipped, 'total': total})}\n\n"

    return Response(_sse(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@editor_bp.route("/api/export/library/preview/<path:rel_path>", methods=["GET"])
def export_library_preview(rel_path):
    """Preview an exported video from output/exports."""
    try:
        abs_path = _resolve_export_relpath(rel_path)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not os.path.isfile(abs_path):
        return jsonify({"error": "File not found"}), 404

    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
        return jsonify({"error": "Unsupported preview format"}), 400

    mime = mimetypes.guess_type(abs_path)[0] or "video/mp4"
    return send_file(abs_path, mimetype=mime, as_attachment=False)


@editor_bp.route("/api/export/library/download/<path:rel_path>", methods=["GET"])
def export_library_download(rel_path):
    """Download a file from output/exports."""
    try:
        abs_path = _resolve_export_relpath(rel_path)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not os.path.isfile(abs_path):
        return jsonify({"error": "File not found"}), 404

    mime = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"
    return send_file(abs_path, mimetype=mime, as_attachment=True, download_name=os.path.basename(abs_path))


@editor_bp.route("/api/export/<job_id>", methods=["DELETE"])
def cancel_export(job_id):
    """Cancel/cleanup an export job."""
    with _export_jobs_lock:
        job = _export_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    meta_path = os.path.splitext(job["output_path"])[0] + ".json"
    logger.info("Cancelling export job: {} (status={})", job_id[:8], job["status"])
    if job["status"] in ("queued", "processing"):
        job["status"] = "cancelled"
        job["message"] = "Cancellation requested"
        job["completed_at"] = time.time()
        if os.path.exists(job["output_path"]):
            try:
                os.remove(job["output_path"])
                logger.debug("Removed partial export file: {}", job["output_path"])
            except OSError as e:
                logger.warning("Could not remove partial export file: {}", e)
        if os.path.exists(meta_path):
            try:
                os.remove(meta_path)
            except OSError:
                pass
        return jsonify({"message": "Cancellation requested", "status": "cancelled"}), 202

    if os.path.exists(job["output_path"]):
        try:
            os.remove(job["output_path"])
            logger.debug("Removed export file: {}", job["output_path"])
        except OSError as e:
            logger.warning("Could not remove export file: {}", e)
    if os.path.exists(meta_path):
        try:
            os.remove(meta_path)
        except OSError:
            pass

    with _export_jobs_lock:
        _export_jobs.pop(job_id, None)
    return jsonify({"message": "Job cancelled and cleaned up"})


@editor_bp.route("/api/export/<job_id>/open-folder", methods=["POST"])
def open_export_folder(job_id):
    """Open the folder containing the exported video and select it."""
    with _export_jobs_lock:
        job = _export_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    output_path = os.path.abspath(job.get("output_path", ""))

    if not os.path.exists(output_path):
        output_path = EXPORT_DIR
        if not os.path.isdir(output_path):
            return jsonify({"error": "Output file not found"}), 404

    try:
        if platform.system() == "Windows":
            if os.path.isfile(output_path):
                subprocess.run(["explorer", "/select,", output_path], check=False)
            else:
                subprocess.run(["explorer", output_path], check=False)
        elif platform.system() == "Darwin":
            if os.path.isfile(output_path):
                subprocess.run(["open", "-R", output_path], check=False)
            else:
                subprocess.run(["open", output_path], check=False)
        else:
            folder = os.path.dirname(output_path) if os.path.isfile(output_path) else output_path
            subprocess.run(["xdg-open", folder], check=False)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error("Failed to open export folder: {}", e)
        return jsonify({"error": str(e)}), 500


@editor_bp.route("/api/export/jobs", methods=["GET"])
def list_export_jobs():
    """List all export jobs with their current status."""
    jobs = []
    with _export_jobs_lock:
        for jid, job in _export_jobs.items():
            jobs.append({
                "job_id": jid,
                "status": job["status"],
                "progress": job["progress"],
                "message": job["message"],
                "step": job.get("step"),
                "error": job["error"],
                "project_id": job.get("project_id"),
                "scene_count": job.get("scene_count"),
                "output_filename": job.get("output_filename"),
                "created_at": job.get("created_at"),
                "completed_at": job.get("completed_at"),
            })
    jobs.sort(key=lambda j: j.get("created_at") or 0, reverse=True)
    return jsonify(jobs)
