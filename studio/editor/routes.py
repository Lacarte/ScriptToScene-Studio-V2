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

from config import TIMELINE_EDITOR_DIR, OUTPUT_DIR, BIN_DIR, APP_ASSETS_DIR, SCENES_DIR, ALIGN_DIR, TTS_DIR, ASSETS_DIR, EXPORT_DIR, CAPTIONS_DIR, PROJECTS_DIR, APP_CONFIG_PATH, TRASH_DIR
from studio.security import sanitize_folder_name, sanitize_project_id, safe_join
from studio.fonts import FONT_REGISTRY, get_font_path, get_font_url
from studio.ffmpeg_utils import find_ffprobe
from studio.io_utils import safe_json_write, safe_json_read
from studio.validation import validate_json
from studio.editor.schemas import EditorSaveRequest, ExportRequest

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
    meta_path = os.path.join(ASSETS_DIR, project_id, "metadata.json")
    try:
        data = safe_json_read(meta_path)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data.get("scenes", {}) if isinstance(data, dict) else {}


def _pick_scene_asset(project_id: str, *scene_keys: str) -> tuple[str, str]:
    """Return the best asset URL and resolved type for the given scene keys."""
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
            media_type = "video" if media_url.lower().endswith(video_exts) else "image"
            return media_url, media_type

    for scene_key in deduped_keys:
        asset_dir = os.path.join(ASSETS_DIR, project_id, scene_key)
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
        media_url = f"/output/assets/{project_id}/{scene_key}/{fname}"
        media_type = "video" if fname.lower().endswith(video_exts) else "image"
        return media_url, media_type

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


# ---------------------------------------------------------------------------
# Editor project save / load
# ---------------------------------------------------------------------------

@editor_bp.route("/api/editor/save", methods=["POST"])
@validate_json(EditorSaveRequest)
def editor_save_project(data: EditorSaveRequest):
    """Save editor project edits to the work-in-progress file."""
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
    save_data["saved_at"] = datetime.now(timezone.utc).isoformat()

    os.makedirs(_project_dir(safe_id), exist_ok=True)

    # Always write to the WIP file — initial state stays untouched
    wip = _wip_path(safe_id)
    try:
        safe_json_write(wip, save_data)
    except OSError as e:
        logger.error("Failed to save WIP for {}: {}", safe_id, e)
        return jsonify({"error": f"Failed to save: {e}"}), 500

    # Ensure the initial file exists (first-time project creation)
    initial = _initial_path(safe_id)
    if not os.path.isfile(initial):
        try:
            safe_json_write(initial, save_data)
            logger.info("Initial state saved for new project: {}", safe_id)
        except OSError:
            pass  # WIP is already written, this is non-critical

    logger.info("Editor WIP saved: {} ({} scenes)", safe_id, save_data.get("scene_count", "?"))
    return jsonify({"ok": True, "saved_at": save_data["saved_at"], "wip": True})


@editor_bp.route("/api/editor/load/<project_id>", methods=["GET"])
def editor_load_project(project_id):
    """Load a saved editor project.

    Prefers the work-in-progress file if it exists, otherwise falls back to
    the initial (pristine) project file.  The response includes a ``source``
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

    # Resolve correct audio from scenes.json source_folder to prevent
    # cross-project audio bleed (saved voice track may belong to another project).
    _resolve_project_audio(data, safe_id)

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
            projects.append({
                "project_id": data.get("project_id", pid),
                "project_name": data.get("project_name", ""),
                "saved_at": data.get("saved_at", ""),
                "scene_count": data.get("scene_count", 0),
                "total_duration": data.get("total_duration", 0),
                "has_wip": has_wip,
            })
        except Exception as error:
            logger.debug("Skipping project manifest {}: {}", json_path, error)

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
                logger.debug("Skipping scenes manifest {}: {}", json_path, error)
                continue

    # 2. Check assets
    if os.path.isdir(ASSETS_DIR):
        for entry in os.listdir(ASSETS_DIR):
            asset_dir = os.path.join(ASSETS_DIR, entry)
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
    for i, s in enumerate(raw_scenes):
        scene_index = s.get("index", i)
        scene_type = s.get("type_of_scene", s.get("type", "image"))
        duration = s.get("duration", 3)
        media_url, media_type = _pick_scene_asset(safe_id, i, scene_index)
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
            "filler_shift": 0,
            "segment_start": s.get("segment_start"),
            "segment_end": s.get("segment_end"),
            "segment_duration": s.get("segment_duration"),
            "asset_files": [media_url] if media_url else [],
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
    if editor_data.get("captions"):
        editor_data["captionsEnabled"] = True
    if not editor_data.get("captions") and source_folder:
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
    """Delete the WIP file and revert the project to its initial state."""
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

        # 3) Assets — all media files under output/assets/{project_id}/
        assets_dir = os.path.join(ASSETS_DIR, safe_id)
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
                        dest = safe_join(os.path.join(ASSETS_DIR, safe_id), sub)
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
    folder = os.path.join(ASSETS_DIR, safe_id)
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
            if not meta_style or not pipeline_timing:
                try:
                    _sp = os.path.join(SCENES_DIR, pid, "scenes.json")
                    if os.path.isfile(_sp):
                        _sd = safe_json_read(_sp)
                        if not meta_style:
                            meta_style = _sd.get("style", "")
                        if not meta_scene_count:
                            meta_scene_count = len(_sd.get("scenes", []))
                        pipeline_timing = _sd.get("pipeline_timing", {})
                except Exception as error:
                    logger.debug("Could not read scene metadata: {}", error)

            items.append({
                "project_id": pid,
                "video_name": fname,
                "video_relpath": rel_video,
                "folder_relpath": rel_folder if rel_folder != "." else "",
                "size_bytes": os.path.getsize(abs_video),
                "modified_at": mtime_iso,
                "preview_url": f"/api/export/library/preview/{video_q}",
                "video_download_url": f"/api/export/library/download/{video_q}",
                "zip_download_url": (f"/api/export/library/download/{zip_q}" if zip_exists else (f"/api/editor/export-zip/{project_id}" if project_id else "")),
                "zip_source": ("file" if zip_exists else "generated"),
                "style": meta_style,
                "ratio": meta_ratio,
                "video_ratio": video_ratio,
                "duration": meta_duration,
                "scene_count": meta_scene_count,
                "pipeline_timing": pipeline_timing,
            })

    items.sort(key=lambda it: it.get("modified_at", ""), reverse=True)
    return jsonify({"items": items, "count": len(items)})


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
