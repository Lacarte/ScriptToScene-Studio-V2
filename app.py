"""ScriptToScene Studio — Main Entry Point"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser

from flask import Flask, jsonify, redirect, request, send_from_directory
from flask_cors import CORS
from flask_sock import Sock
from loguru import logger

from config import (
    LOG_DIR, STATIC_DIR, ALIGN_DIR, TRASH_DIR, N8N_WEBHOOK_URL,
    N8N_ASSET_WEBHOOK_URL, N8N_STORY_WEBHOOK_URL, OUTPUT_DIR,
    SCENES_DIR, STORIES_DIR, PIPELINE_DIR, ANIMATOR_DIR, STORYBOARD_DIR,
    SEGMENTER_DIR, CAPTIONS_DIR, MUSIC_DIR, TTS_DIR, PROJECTS_DIR,
    EXPORT_DIR, APP_CONFIG_PATH, APP_ASSETS_DIR, TMP_DIR, WORKFLOWS_DIR, BRANDING_DIR,
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


logger.add(sys.stderr, format=_console_format, level="INFO", colorize=True)
logger.add(os.path.join(LOG_DIR, "studio_{time:YYYY-MM-DD}.log"),
           level="INFO", rotation="1 day", retention="7 days", compression="zip",
           format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {name}:{function}:{line} - {message}")

# ---------------------------------------------------------------------------
# Flask app + Blueprints
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB max request body
_cors_env = os.environ.get("STS_CORS_ORIGINS", "http://localhost:5050,http://127.0.0.1:5050,http://localhost:5174,http://localhost:5175")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
CORS(app, origins=_cors_origins or None)
sock = Sock(app)

from studio.tts import tts_bp
from studio.timing import timing_bp
from studio.segmenter import segmenter_bp
from studio.build_scene_blueprints import scenes_bp
from studio.animator import animation_bp
from studio.editor import editor_bp
from studio.pipeline import pipeline_bp
from studio.captions import captions_bp
from studio.music import music_bp
from studio.thumbnails import thumbnails_bp
from studio.story import story_bp
from studio.niches import niches_bp
from studio.storyboard import storyboard_bp
from studio.animator import animator_bp
from studio.workflows import workflows_bp
from studio.providers import providers_bp
app.register_blueprint(tts_bp)
app.register_blueprint(timing_bp)
app.register_blueprint(segmenter_bp)
app.register_blueprint(scenes_bp)
app.register_blueprint(animation_bp)
app.register_blueprint(editor_bp)
app.register_blueprint(pipeline_bp)
app.register_blueprint(captions_bp)
app.register_blueprint(music_bp)
app.register_blueprint(thumbnails_bp)
app.register_blueprint(story_bp)
app.register_blueprint(niches_bp)
app.register_blueprint(storyboard_bp)
app.register_blueprint(animator_bp)
app.register_blueprint(workflows_bp)
app.register_blueprint(providers_bp)
from studio.orchestrator_ws import init_orchestrator_ws
init_orchestrator_ws(sock)

from studio.shared.providers_common import hub, init_providers
init_providers(app=app, sock=sock)
logger.info("[providers] {} domains: {}",
           len(hub.domains()),
           {d: len(hub.registry(d)) for d in hub.domains()})


# ---------------------------------------------------------------------------
# Core routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Redirect root to Vue SPA."""
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
    return send_from_directory(APP_ASSETS_DIR, filename)


@app.route("/api/restart", methods=["POST"])
def restart_server():
    """Restart the Flask server process."""
    if not is_loopback_remote(request.remote_addr):
        return jsonify({"error": "Forbidden"}), 403

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
    from config import APP_VERSION
    from studio.tts.inworld import is_available as _inworld_available
    return jsonify({
        "status": "ok",
        "version": APP_VERSION,
        "alignment": _check_alignment_available(),
        "ffmpeg": find_ffmpeg() is not None,
        "tts_model": _model_files_present(),
        "inworld_tts": _inworld_available(),
    })


def _retry_until(predicate, timeout_s=4.0, interval_s=1.0):
    """Retry a connectivity check until it succeeds or a timeout elapses."""
    import time as _time

    # Extension WS reconnect cycle is roughly 2-3s. Keep checking a bit
    # longer so runs started mid-reconnect do not false-fail preflight.

    deadline = _time.monotonic() + timeout_s
    while True:
        if predicate():
            return True
        remaining = deadline - _time.monotonic()
        if remaining <= 0:
            return False
        _time.sleep(min(interval_s, remaining))


def _extension_target(name: str) -> str | None:
    """Map a legacy or canonical extension id onto the shared hub key.

    Accepts both the wire aliases the pipeline still sends (`gemini` / `grok`)
    and the canonical provider ids resolved through the registry. Owner 14.4;
    concrete provider ids are not listed here so the zero-touch scan stays clean
    (16.1 retires the remaining alias tables).
    """
    key = str(name or "").strip()
    if not key:
        return None
    lowered = key.lower()
    if lowered in {"gemini", "grok"}:
        return lowered
    try:
        from studio.shared.providers_common.hub import hub as provider_hub
    except Exception:
        return None
    for domain, label in (("storyboard", "gemini"), ("animator", "grok")):
        try:
            instance = provider_hub.get(domain, key)
        except Exception:
            instance = None
        if instance is not None and getattr(instance, "kind", None) == "extension":
            return label
    return None


def _extension_activate(target: str):
    if target == "gemini":
        from studio.storyboard.gemini_ws import activate_tab
        return activate_tab
    if target == "grok":
        from studio.animator.routes import activate_tab
        return activate_tab
    return None


def _extension_connected(target: str):
    if target == "gemini":
        from studio.storyboard.gemini_ws import is_extension_connected
        return is_extension_connected
    if target == "grok":
        from studio.animator.routes import is_extension_connected
        return is_extension_connected
    return None


@app.route("/api/chromium/activate-tab", methods=["POST"])
def activate_chromium_tab():
    """Activate a provider tab via WebSocket to the extension."""
    data = request.get_json(silent=True) or {}
    raw_target = data.get("target", "gemini")
    target = _extension_target(raw_target)
    if target is None:
        return jsonify({"ok": False, "error": f"Unknown target: {raw_target}"}), 400

    activate = _extension_activate(target)
    # Retry briefly — extension WS may be mid-reconnect (2s cycle)
    if activate and _retry_until(activate, timeout_s=4.0, interval_s=1.0):
        return jsonify({"ok": True, "target": target})

    return jsonify({"ok": False, "error": f"No {target} extension connected"}), 404


@app.route("/api/chromium/health", methods=["GET"])
def chromium_health():
    """Report connection status of all extension WebSocket clients."""
    gemini_probe = _extension_connected("gemini")
    grok_probe = _extension_connected("grok")
    return jsonify({
        "gemini": {"connected": bool(gemini_probe() if gemini_probe else False)},
        "grok": {"connected": bool(grok_probe() if grok_probe else False)},
    })


@app.route("/api/chromium/focus-studio", methods=["POST"])
def focus_studio_tab_endpoint():
    """Ask any connected extension to focus the ScriptToScene Studio tab."""
    from studio.storyboard.gemini_ws import focus_studio_tab as gemini_focus
    from studio.animator.routes import focus_studio_tab as grok_focus

    sent_gemini = False
    sent_grok = False
    try:
        sent_gemini = bool(gemini_focus())
    except Exception as e:
        logger.warning("focus-studio gemini failed: {}", e)
    try:
        sent_grok = bool(grok_focus())
    except Exception as e:
        logger.warning("focus-studio grok failed: {}", e)

    return jsonify({
        "ok": sent_gemini or sent_grok,
        "gemini": sent_gemini,
        "grok": sent_grok,
    })


@app.route("/api/pipeline/preflight", methods=["POST"])
def pipeline_preflight():
    """Check extension connectivity before starting a pipeline run.

    Accepts legacy wire aliases and canonical registry ids for the two
    extension providers. Only extension providers need a connected client;
    cloud providers skip the probe (step 14.4 / P3 / P4).
    """
    data = request.get_json(silent=True) or {}
    stop_after = data.get("stop_after", "")
    storyboard_provider = data.get("storyboard_provider", "gemini")
    asset_provider = data.get("asset_provider", "grok")

    issues = []
    warnings = []

    # Determine which extensions are needed based on pipeline scope
    needs_storyboard = stop_after in ("", "storyboard", "assets", "assemble", "export")
    needs_assets = stop_after in ("", "assets", "assemble", "export")

    # Extension WS reconnect cycle is ~2s — give it a brief grace window
    # before declaring a provider unavailable. This prevents false negatives
    # between back-to-back jobs when the tab is mid-reconnect.
    sb_target = _extension_target(storyboard_provider)
    if needs_storyboard and sb_target == "gemini":
        probe = _extension_connected("gemini")
        if probe and not _retry_until(probe, timeout_s=4.0, interval_s=1.0):
            warnings.append({
                "target": "gemini",
                "message": "Gemini extension not connected yet",
                "recoverable": True,
                "queued": True,
            })

    asset_target = _extension_target(asset_provider)
    if needs_assets and asset_target == "grok":
        probe = _extension_connected("grok")
        if probe and not _retry_until(probe, timeout_s=4.0, interval_s=1.0):
            warnings.append({
                "target": "grok",
                "message": "Grok extension not connected yet",
                "recoverable": True,
                "queued": True,
            })

    return jsonify({"ok": len(issues) == 0, "issues": issues, "warnings": warnings})


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
    {"page": "Scenes", "module": "Scene Blueprint", "dir": SCENES_DIR},
    {"page": "Animator", "module": "Animation Manager", "dir": ANIMATOR_DIR},
    {"page": "Storyboard", "module": "Storyboard Images", "dir": STORYBOARD_DIR},
    {"page": "Captions", "module": "Captions", "dir": CAPTIONS_DIR},
    {"page": "Editor", "module": "Timeline Editor", "dir": PROJECTS_DIR},
    {"page": "Music", "module": "User-uploaded Music", "dir": MUSIC_DIR},
    {"page": "Exports", "module": "Export Library", "dir": EXPORT_DIR},
    {"page": "Stories", "module": "Story Generator", "dir": STORIES_DIR},
    {"page": "Pipeline", "module": "Pipeline Data", "dir": PIPELINE_DIR},
    {"page": "Workflows", "module": "Workflow Definitions", "dir": WORKFLOWS_DIR},
    {"page": "Branding", "module": "Workflow Branding", "dir": BRANDING_DIR},
]
_PROJECT_DIRS = [
    ALIGN_DIR, SCENES_DIR, STORIES_DIR, PIPELINE_DIR, ANIMATOR_DIR, STORYBOARD_DIR,
    SEGMENTER_DIR, CAPTIONS_DIR, MUSIC_DIR, TTS_DIR, PROJECTS_DIR,
    EXPORT_DIR,
    WORKFLOWS_DIR, BRANDING_DIR,
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
    # Also wipe tmp/ (preview cache, temp files)
    if os.path.isdir(TMP_DIR):
        try:
            shutil.rmtree(TMP_DIR)
            os.makedirs(TMP_DIR, exist_ok=True)
            logger.info("Cleared tmp directory: {}", TMP_DIR)
        except Exception as e:
            errors.append(f"tmp: {e}")
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

    C, G, Y, D, B, X = "\033[36m", "\033[32m", "\033[33m", "\033[90m", "\033[1m", "\033[0m"

    tts_ok = _model_files_present()
    align_ok = _check_alignment_available()

    print()
    print(f"  {C}{B}ScriptToScene Studio{X}")
    print(f"  {D}{'-' * 28}{X}")
    print()
    print(f"  {G}>{X} {B}{url}{X}")
    print()
    print(f"  {G if tts_ok else Y}{'+'if tts_ok else '!'}{X} TTS model    {D}{'cached' if tts_ok else 'not downloaded'}{X}")
    print(f"  {G if align_ok else Y}{'+'if align_ok else '!'}{X} Alignment    {D}{'available' if align_ok else 'unavailable'}{X}")
    print(f"  {D}-{X} Scene hook   {D}{N8N_WEBHOOK_URL}{X}")
    print(f"  {D}-{X} Asset hook   {D}{N8N_ASSET_WEBHOOK_URL}{X}")
    print(f"  {D}-{X} Story hook   {D}{N8N_STORY_WEBHOOK_URL}{X}")
    print(f"  {D}{'-' * 28}{X}")
    print(f"  {D}-{X} Gemini WS    {D}ws://localhost:{port}/ws/storyboard-gemini-image-grabber{X}")
    print(f"  {D}-{X} Grok WS      {D}ws://localhost:{port}/ws/animator-grok-video-grabber{X}")
    print(f"  {D}{'-' * 28}{X}")
    print()

    if not os.environ.get("STS_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    bind_host = os.environ.get("STS_BIND_HOST", "127.0.0.1")
    from studio.workflows.scheduled_runs import schedule_service
    from studio.workflows.watch_folders import watch_folder_service
    from studio.workflows.dev_reload import start_dev_reloader
    schedule_service.start()
    watch_folder_service.start()
    start_dev_reloader()
    app.run(host=bind_host, port=port, debug=False, threaded=True)
