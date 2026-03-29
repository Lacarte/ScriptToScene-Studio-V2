"""Music Module — Browse and manage background music tracks."""
import json
import os
import subprocess

from flask import Blueprint, jsonify, request, send_from_directory
from loguru import logger
from werkzeug.utils import secure_filename

from config import MUSIC_DIR
from studio.ffmpeg_utils import find_ffprobe

music_bp = Blueprint("music", __name__)

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}


def _get_duration(filepath):
    """Try to get audio duration using ffprobe (optional)."""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_format", filepath],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return round(float(data.get("format", {}).get("duration", 0)), 2)
    except Exception:
        pass
    return None


@music_bp.route("/api/music/library")
def list_music():
    """List all music files in the library."""
    files = []
    if not os.path.isdir(MUSIC_DIR):
        return jsonify(files)

    for fname in sorted(os.listdir(MUSIC_DIR)):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        fpath = os.path.join(MUSIC_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        size_mb = round(os.path.getsize(fpath) / (1024 * 1024), 1)
        duration = _get_duration(fpath)
        files.append({
            "filename": fname,
            "path": f"/output/musics/{fname}",
            "size_mb": size_mb,
            "duration": duration,
        })
    return jsonify(files)


@music_bp.route("/api/music/upload", methods=["POST"])
def upload_music():
    """Upload a music file to the library."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No filename"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported format: {ext}"}), 400

    fname = secure_filename(f.filename)
    dest = os.path.join(MUSIC_DIR, fname)
    f.save(dest)
    logger.info(f"Music uploaded: {fname}")

    size_mb = round(os.path.getsize(dest) / (1024 * 1024), 1)
    duration = _get_duration(dest)
    return jsonify({
        "filename": fname,
        "path": f"/output/musics/{fname}",
        "size_mb": size_mb,
        "duration": duration,
    })


@music_bp.route("/api/music/auto-select")
def auto_select_music():
    """Pick a random music track based on story_tone query param."""
    story_tone = request.args.get("tone", "").strip()
    if not story_tone:
        return jsonify({"error": "Missing 'tone' query parameter"}), 400

    from studio.music.selector import select_music
    result = select_music(story_tone)
    if not result:
        return jsonify({"error": f"No music for tone '{story_tone}'"}), 404

    # Convert absolute path to a servable URL
    abs_path = result["path"]
    from config import APP_ASSETS_DIR
    if abs_path.startswith(APP_ASSETS_DIR):
        rel = abs_path[len(APP_ASSETS_DIR):].replace("\\", "/").lstrip("/")
        result["path"] = f"/assets/{rel}"
    result["filename"] = os.path.basename(abs_path)
    return jsonify(result)


@music_bp.route("/output/musics/<path:filename>")
def serve_music(filename):
    """Serve music files for playback."""
    return send_from_directory(MUSIC_DIR, filename)
