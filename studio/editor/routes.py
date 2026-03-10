"""Editor Module — Timeline Editor Static File Serving + Export API"""

import io
import json
import mimetypes
import os
import platform
import subprocess
import sys
import tempfile
import time
import uuid
import threading
import traceback
import zipfile

from flask import Blueprint, send_from_directory, request, jsonify, send_file
from loguru import logger

from config import TIMELINE_EDITOR_DIR, OUTPUT_DIR, BIN_DIR, APP_ASSETS_DIR, EDITOR_SAVE_DIR, SCENES_DIR, ALIGN_DIR, TTS_DIR, ASSETS_DIR
from studio.security import sanitize_folder_name, sanitize_project_id, safe_join
from studio.fonts import FONT_REGISTRY, get_font_path, get_font_url
from studio.io_utils import safe_json_write, safe_json_read
from studio.validation import validate_json
from studio.editor.schemas import EditorSaveRequest, ExportRequest

editor_bp = Blueprint("editor", __name__)

# ---------------------------------------------------------------------------
# Export job storage & output directory
# ---------------------------------------------------------------------------
_export_jobs = {}
_export_jobs_lock = threading.Lock()
EXPORT_DIR = os.path.join(OUTPUT_DIR, "exports")
EXPORT_DIR_ABS = os.path.abspath(EXPORT_DIR)
EXPORT_MAX_JOB_AGE = 3600  # evict finished jobs after 1 hour
os.makedirs(EXPORT_DIR, exist_ok=True)

logger.info("Export output directory: {}", EXPORT_DIR)
logger.info("Editor save directory: {}", EDITOR_SAVE_DIR)


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
                    import shutil
                    shutil.rmtree(path, ignore_errors=True)
                    cleaned += 1
            except OSError:
                pass
    except OSError:
        pass
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
    if not os.path.isfile(scenes_path):
        return None
    try:
        with open(scenes_path, "r", encoding="utf-8") as f:
            return json.load(f).get("source_folder")
    except (json.JSONDecodeError, OSError):
        return None


def _resolve_audio_url(source_folder: str) -> dict | None:
    """Resolve audio file URL from the alignment folder."""
    folder_path = os.path.join(ALIGN_DIR, source_folder)
    if not os.path.isdir(folder_path):
        return None
    try:
        for f in os.listdir(folder_path):
            if f.endswith((".wav", ".mp3")):
                return {
                    "url": f"/output/alignments/{source_folder}/{f}",
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
    # Fix voice track in audio_tracks if it points to wrong audio
    for track in data.get("audio_tracks", []):
        if track.get("type") == "voice" and track.get("path") != correct_url:
            logger.info("Fixing voice track for {}: {} -> {}", project_id, track.get("path"), correct_url)
            track["path"] = correct_url
            track["file"] = resolved["source_file"]
            break


def _resolve_project_captions(data: dict, project_id: str):
    """Clear captions if their project_id doesn't match the current project."""
    captions = data.get("captions")
    if not captions:
        return
    cap_project_id = captions.get("project_id", "")
    # Captions have their own project_id (cap_XXXXX). Check if source_folder
    # matches to determine if captions belong to this project.
    source_folder = _get_source_folder(project_id)
    if not source_folder:
        return
    cap_source = captions.get("source_folder", "")
    if cap_source and cap_source != source_folder:
        logger.info("Clearing stale captions for {}: cap source={} != project source={}", project_id, cap_source, source_folder)
        data["captions"] = None


# ---------------------------------------------------------------------------
# Editor project save / load
# ---------------------------------------------------------------------------

@editor_bp.route("/api/editor/save", methods=["POST"])
@validate_json(EditorSaveRequest)
def editor_save_project(data: EditorSaveRequest):
    """Save full editor project state to disk."""
    safe_id = data.project_id  # already validated: alphanumeric + _ and -

    from datetime import datetime, timezone
    save_data = data.model_dump(exclude_none=True)
    save_data["saved_at"] = datetime.now(timezone.utc).isoformat()

    path = os.path.join(EDITOR_SAVE_DIR, f"{safe_id}.json")
    try:
        safe_json_write(path, save_data)
    except OSError as e:
        logger.error("Failed to save editor project {}: {}", safe_id, e)
        return jsonify({"error": f"Failed to save: {e}"}), 500

    logger.info("Editor project saved: {} ({} scenes)", safe_id, save_data.get("scene_count", "?"))
    return jsonify({"ok": True, "saved_at": save_data["saved_at"]})


@editor_bp.route("/api/editor/load/<project_id>", methods=["GET"])
def editor_load_project(project_id):
    """Load a saved editor project."""
    safe_id = "".join(c for c in project_id if c.isalnum() or c in ("_", "-"))
    path = os.path.join(EDITOR_SAVE_DIR, f"{safe_id}.json")

    try:
        data = safe_json_read(path)
    except FileNotFoundError:
        return jsonify({"error": "not found"}), 404
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load editor project {}: {}", safe_id, e)
        return jsonify({"error": f"Corrupted project file: {e}"}), 500

    # Inject source_folder so the frontend can scope captions/audio
    source_folder = _get_source_folder(safe_id)
    if source_folder:
        data["source_folder"] = source_folder

    # Resolve correct audio from scenes.json source_folder to prevent
    # cross-project audio bleed (saved voice track may belong to another project).
    _resolve_project_audio(data, safe_id)

    # Resolve correct captions from the alignment folder
    _resolve_project_captions(data, safe_id)

    return jsonify(data)


@editor_bp.route("/api/editor/projects", methods=["GET"])
def editor_list_projects():
    """List all saved editor projects."""
    projects = []
    for fname in os.listdir(EDITOR_SAVE_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(EDITOR_SAVE_DIR, fname)
        try:
            data = safe_json_read(fpath)
            projects.append({
                "project_id": data.get("project_id", fname.replace(".json", "")),
                "project_name": data.get("project_name", ""),
                "saved_at": data.get("saved_at", ""),
                "scene_count": data.get("scene_count", 0),
                "total_duration": data.get("total_duration", 0),
            })
        except Exception:
            continue

    projects.sort(key=lambda p: p.get("saved_at", ""), reverse=True)
    return jsonify(projects)


# ---------------------------------------------------------------------------
# Project ZIP export
# ---------------------------------------------------------------------------

@editor_bp.route("/api/editor/export-zip/<project_id>", methods=["GET"])
def export_project_zip(project_id):
    """Bundle a complete project into a downloadable ZIP file."""
    from datetime import datetime, timezone

    safe_id = "".join(c for c in project_id if c.isalnum() or c in ("_", "-"))

    # Require at least the editor save or scenes.json to exist
    editor_path = os.path.join(EDITOR_SAVE_DIR, f"{safe_id}.json")
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
            editor_file_check = os.path.join(EDITOR_SAVE_DIR, f"{safe_id}.json")
            if os.path.exists(scenes_dir_check) or os.path.exists(editor_file_check):
                suffix = 2
                while True:
                    candidate = f"{original_id}-{suffix}"
                    if not os.path.exists(os.path.join(SCENES_DIR, candidate)) and \
                       not os.path.exists(os.path.join(EDITOR_SAVE_DIR, f"{candidate}.json")):
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
                    dest = os.path.join(EDITOR_SAVE_DIR, f"{safe_id}.json")
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as f:
                        f.write(raw)
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
                        with open(scenes_json_path, "r", encoding="utf-8") as f:
                            sdata = json.load(f)
                        sdata["project_id"] = safe_id
                        with open(scenes_json_path, "w", encoding="utf-8") as f:
                            json.dump(sdata, f, ensure_ascii=False)
                    except Exception:
                        pass
                editor_json_path = os.path.join(EDITOR_SAVE_DIR, f"{safe_id}.json")
                if os.path.exists(editor_json_path):
                    try:
                        with open(editor_json_path, "r", encoding="utf-8") as f:
                            edata = json.load(f)
                        if "id" in edata:
                            edata["id"] = safe_id
                        if "name" in edata:
                            edata["name"] = safe_id
                        with open(editor_json_path, "w", encoding="utf-8") as f:
                            json.dump(edata, f, ensure_ascii=False)
                    except Exception:
                        pass

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

@editor_bp.route("/timeline-editor/<path:filename>")
def serve_timeline_editor(filename):
    """Serve timeline editor static files."""
    resp = send_from_directory(TIMELINE_EDITOR_DIR, filename)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp



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

    try:
        # Import here to avoid circular imports at module load
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "timeline-editor", "backend"))
        from video_processor import VideoProcessor

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
            project_id = _safe_project_id(base) or folder_project_id

            # Pair ZIP by same filename in the same folder, fallback to generated project ZIP.
            zip_name = f"{base}.zip"
            abs_zip = os.path.join(root, zip_name)
            zip_exists = os.path.isfile(abs_zip)
            zip_rel = os.path.relpath(abs_zip, EXPORT_DIR).replace("\\", "/") if zip_exists else ""

            mtime = os.path.getmtime(abs_video)
            mtime_iso = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            video_q = quote(rel_video, safe="/")
            zip_q = quote(zip_rel, safe="/") if zip_exists else ""

            items.append({
                "project_id": project_id or base,
                "video_name": fname,
                "video_relpath": rel_video,
                "folder_relpath": rel_folder if rel_folder != "." else "",
                "size_bytes": os.path.getsize(abs_video),
                "modified_at": mtime_iso,
                "preview_url": f"/api/export/library/preview/{video_q}",
                "video_download_url": f"/api/export/library/download/{video_q}",
                "zip_download_url": (f"/api/export/library/download/{zip_q}" if zip_exists else (f"/api/editor/export-zip/{project_id}" if project_id else "")),
                "zip_source": ("file" if zip_exists else "generated"),
            })

    items.sort(key=lambda it: it.get("modified_at", ""), reverse=True)
    return jsonify({"items": items, "count": len(items)})


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
        return jsonify({"message": "Cancellation requested", "status": "cancelled"}), 202

    if os.path.exists(job["output_path"]):
        try:
            os.remove(job["output_path"])
            logger.debug("Removed export file: {}", job["output_path"])
        except OSError as e:
            logger.warning("Could not remove export file: {}", e)

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
