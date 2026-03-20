"""ScriptToScene Studio — Main Entry Point"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from loguru import logger

from config import (
    LOG_DIR, STATIC_DIR, ALIGN_DIR, TRASH_DIR, N8N_WEBHOOK_URL,
    N8N_ASSET_WEBHOOK_URL, N8N_STORY_WEBHOOK_URL, OUTPUT_DIR,
    SCENES_DIR, STORIES_DIR, PIPELINE_DIR, ASSETS_DIR,
    SEGMENTER_DIR, CAPTIONS_DIR, MUSIC_DIR, TTS_DIR, PROJECTS_DIR,
    EXPORT_DIR, APP_CONFIG_PATH,
)
from studio.security import is_loopback_remote

# ---------------------------------------------------------------------------
# Loguru configuration
# ---------------------------------------------------------------------------
logger.remove()

LEVEL_ICONS = {"DEBUG": "\u2502", "INFO": "\u2502", "SUCCESS": "+", "WARNING": "!", "ERROR": "\u2716", "CRITICAL": "\u2716"}


def _console_format(record):
    icon = LEVEL_ICONS.get(record["level"].name, "\u2502")
    colors = {"DEBUG": "dim", "INFO": "white", "SUCCESS": "green", "WARNING": "yellow", "ERROR": "red", "CRITICAL": "red,bold"}
    c = colors.get(record["level"].name, "white")
    ts = record["time"].strftime("%H:%M:%S")
    return f"<dim>{ts}</dim> <{c}>{icon}</{c}> {{message}}\n"


logger.add(sys.stderr, format=_console_format, level="DEBUG", colorize=True)
logger.add(os.path.join(LOG_DIR, "studio_{time:YYYY-MM-DD}.log"),
           level="DEBUG", rotation="1 day", retention="7 days", compression="zip",
           format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {name}:{function}:{line} - {message}")

# ---------------------------------------------------------------------------
# Flask app + Blueprints
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB max request body
_cors_env = os.environ.get("STS_CORS_ORIGINS", "http://localhost:5050,http://127.0.0.1:5050,http://localhost:5174,http://localhost:5175")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
CORS(app, origins=_cors_origins or None)

from studio.tts import tts_bp
from studio.timing import timing_bp
from studio.segmenter import segmenter_bp
from studio.scenes import scenes_bp
from studio.assets import assets_bp
from studio.editor import editor_bp
from studio.pipeline import pipeline_bp
from studio.captions import captions_bp
from studio.music import music_bp
from studio.thumbnails import thumbnails_bp
from studio.story import story_bp
from studio.niches import niches_bp
app.register_blueprint(tts_bp)
app.register_blueprint(timing_bp)
app.register_blueprint(segmenter_bp)
app.register_blueprint(scenes_bp)
app.register_blueprint(assets_bp)
app.register_blueprint(editor_bp)
app.register_blueprint(pipeline_bp)
app.register_blueprint(captions_bp)
app.register_blueprint(music_bp)
app.register_blueprint(thumbnails_bp)
app.register_blueprint(story_bp)
app.register_blueprint(niches_bp)


# ---------------------------------------------------------------------------
# Core routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Redirect root to Vue SPA."""
    from flask import redirect
    return redirect("/vue/")


@app.route("/vue")
@app.route("/vue/")
@app.route("/vue/<path:path>")
def serve_vue(path="index.html"):
    """Serve the Vue SPA build from static/dist/."""
    dist_dir = os.path.join(STATIC_DIR, "dist")
    full_path = os.path.join(dist_dir, path)
    if os.path.isfile(full_path):
        return send_from_directory(dist_dir, path)
    # For SPA client-side routes, serve index.html
    return send_from_directory(dist_dir, "index.html")


@app.route("/app-config.json")
def serve_app_config():
    """Serve app-config.json with no-cache to ensure fresh user settings."""
    return send_from_directory(
        os.path.dirname(os.path.abspath(__file__)), "app-config.json",
        max_age=0,
    )


@app.route("/assets/<path:filename>")
def serve_app_assets(filename):
    from config import APP_ASSETS_DIR
    return send_from_directory(APP_ASSETS_DIR, filename)


@app.route("/api/restart", methods=["POST"])
def restart_server():
    """Restart the Flask server process."""
    import sys
    import subprocess
    import threading
    def _restart():
        import time as _t
        _t.sleep(0.5)
        env = os.environ.copy()
        env["STS_NO_BROWSER"] = "1"  # Prevent auto-open on restart
        subprocess.Popen(
            [sys.executable] + sys.argv,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
        )
        os._exit(0)
    threading.Thread(target=_restart, daemon=True).start()
    return jsonify({"status": "restarting"})


@app.route("/api/health")
def health():
    from studio.ffmpeg_utils import find_ffmpeg
    from studio.timing.routes import _check_alignment_available
    from studio.tts.routes import _model_files_present
    return jsonify({
        "status": "ok",
        "alignment": _check_alignment_available(),
        "ffmpeg": find_ffmpeg() is not None,
        "tts_model": _model_files_present(),
    })


@app.route("/api/open-folder", methods=["POST"])
def open_folder():
    if not is_loopback_remote(request.remote_addr):
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json(silent=True) or {}
    folder = os.path.basename(data.get("folder", ""))
    target = os.path.join(ALIGN_DIR, folder)
    if not os.path.isdir(target):
        return jsonify({"error": "Folder not found"}), 404
    if sys.platform == "win32":
        os.startfile(target)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Settings — Clear all projects
# ---------------------------------------------------------------------------

# Directories whose contents get moved to output/TRASH/<dir_name>/
_CLEAR_MODULES = [
    {"page": "TTS", "module": "Text to Speech", "dir": TTS_DIR},
    {"page": "Alignment", "module": "Force Alignment", "dir": ALIGN_DIR},
    {"page": "Segmenter", "module": "Scene Segmenter", "dir": SEGMENTER_DIR},
    {"page": "Scenes", "module": "Scene Generator", "dir": SCENES_DIR},
    {"page": "Assets", "module": "Asset Manager", "dir": ASSETS_DIR},
    {"page": "Captions", "module": "Captions", "dir": CAPTIONS_DIR},
    {"page": "Editor", "module": "Timeline Editor", "dir": PROJECTS_DIR},
    {"page": "Music", "module": "Music Library", "dir": MUSIC_DIR},
    {"page": "Exports", "module": "Export Library", "dir": EXPORT_DIR},
    {"page": "Stories", "module": "Story Generator", "dir": STORIES_DIR},
    {"page": "Pipeline", "module": "Pipeline Data", "dir": PIPELINE_DIR},
]
_PROJECT_DIRS = [
    ALIGN_DIR, SCENES_DIR, STORIES_DIR, PIPELINE_DIR, ASSETS_DIR, SEGMENTER_DIR,
    CAPTIONS_DIR, MUSIC_DIR, TTS_DIR, PROJECTS_DIR,
    EXPORT_DIR,
]


@app.route("/api/settings/clear-all-projects/preview", methods=["GET"])
def clear_all_projects_preview():
    """Preview what clear-all-projects will move to TRASH."""
    if not is_loopback_remote(request.remote_addr):
        return jsonify({"error": "Forbidden"}), 403

    modules = []
    total_items = 0
    for mod in _CLEAR_MODULES:
        path = mod["dir"]
        entries = []
        if os.path.isdir(path):
            try:
                entries = sorted(
                    [
                        name for name in os.listdir(path)
                        if os.path.isdir(os.path.join(path, name)) or os.path.isfile(os.path.join(path, name))
                    ],
                    key=lambda s: s.lower(),
                )
            except OSError:
                entries = []
        count = len(entries)
        total_items += count
        modules.append({
            "page": mod["page"],
            "module": mod["module"],
            "dir_name": os.path.basename(path),
            "items": count,
            "entries": entries,
        })

    return jsonify({"modules": modules, "total_items": total_items})


@app.route("/api/settings/clear-all-projects", methods=["DELETE"])
def clear_all_projects():
    """Move all project folders and files to output/TRASH/."""
    if not is_loopback_remote(request.remote_addr):
        return jsonify({"error": "Forbidden"}), 403
    total = 0
    exports_deleted = 0
    errors = []
    for src_dir in _PROJECT_DIRS:
        if not os.path.isdir(src_dir):
            continue
        dir_name = os.path.basename(src_dir)
        trash_dir = os.path.join(TRASH_DIR, dir_name)
        os.makedirs(trash_dir, exist_ok=True)
        for entry in os.listdir(src_dir):
            entry_path = os.path.join(src_dir, entry)
            if os.path.isdir(entry_path) or os.path.isfile(entry_path):
                try:
                    dest = os.path.join(trash_dir, entry)
                    if os.path.exists(dest):
                        if os.path.isdir(dest):
                            shutil.rmtree(dest)
                        else:
                            os.remove(dest)
                    shutil.move(entry_path, dest)
                    total += 1
                    if src_dir == EXPORT_DIR:
                        exports_deleted += 1
                except Exception as e:
                    errors.append(f"{entry}: {e}")
    logger.info("Cleared {} project folders to {}", total, TRASH_DIR)
    result = {"status": "cleared", "count": total, "exports_deleted": exports_deleted}
    if errors:
        result["errors"] = errors
    return jsonify(result)


# ---------------------------------------------------------------------------
# Port detection & startup
# ---------------------------------------------------------------------------

def find_available_port(start=5050):
    for p in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", p))
                return p
            except OSError:
                continue
    return start


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ScriptToScene Studio")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    port = args.port if args.port else find_available_port(5050)

    from studio.timing.routes import _check_alignment_available
    from studio.tts.routes import _model_files_present

    url = f"http://localhost:{port}"

    print()
    print(f"  \033[1mScriptToScene Studio\033[0m")
    print(f"  \033[92m>\033[0m {url}")
    print(f"  \033[90m-\033[0m TTS model: {'cached' if _model_files_present() else 'not downloaded'}")
    print(f"  \033[90m-\033[0m Alignment: {'available' if _check_alignment_available() else 'unavailable'}")
    print(f"  \033[90m-\033[0m Scene webhook: {N8N_WEBHOOK_URL}")
    print(f"  \033[90m-\033[0m Asset webhook: {N8N_ASSET_WEBHOOK_URL}")
    print(f"  \033[90m-\033[0m Story webhook: {N8N_STORY_WEBHOOK_URL}")
    print()

    if not os.environ.get("STS_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    bind_host = os.environ.get("STS_BIND_HOST", "127.0.0.1")
    app.run(host=bind_host, port=port, debug=False, threaded=True)
