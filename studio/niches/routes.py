import os
from urllib.parse import quote

from flask import Blueprint, jsonify

from config import EXPORT_DIR, PIPELINE_DIR, PROJECTS_DIR, STORYBOARD_DIR, TTS_DIR
from studio.io_utils import safe_json_read
from studio.niches.presets import (
    CATEGORIES,
    STORY_TONES,
    delete_preset,
    get_presets,
    get_visual_styles,
    normalize_preset_id,
    save_preset,
)
from studio.niches.schemas import NichePresetSaveRequest
from studio.validation import validate_json

niches_bp = Blueprint("niches", __name__)


@niches_bp.route("/api/niches", methods=["GET"])
def list_niches():
    """Return all niche presets, story tones, categories, and visual styles."""
    return jsonify({
        "presets": get_presets(),
        "story_tones": STORY_TONES,
        "categories": CATEGORIES,
        "visual_styles": get_visual_styles(),
    })


@niches_bp.route("/api/niches", methods=["POST"])
@validate_json(NichePresetSaveRequest)
def create_niche(data: NichePresetSaveRequest):
    """Save a new custom niche preset."""
    payload = data.model_dump()
    preset_id = payload.pop("id")
    try:
        presets = save_preset(preset_id, payload)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"presets": presets, "saved_id": normalize_preset_id(preset_id)})


@niches_bp.route("/api/niches/<preset_id>", methods=["DELETE"])
def remove_niche(preset_id):
    """Delete a niche preset by ID."""
    try:
        presets = delete_preset(preset_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"presets": presets})


def _build_style_category_index():
    """Map (visual_style, category) → preset_id for fallback matching of older
    pipeline runs that didn't persist `niche_preset` in their config."""
    index = {}
    for pid, preset in get_presets().items():
        key = (
            (preset.get("visual_style") or "").strip().lower(),
            (preset.get("category") or "").strip().lower(),
        )
        # First-write wins so we get a stable mapping
        index.setdefault(key, pid)
    return index


def _resolve_preset_for_run(cfg, fallback_index):
    """Return the preset_id used by a pipeline run, falling back to
    (visual_style, category) lookup for legacy runs."""
    direct = normalize_preset_id(cfg.get("niche_preset", ""))
    if direct:
        return direct
    key = (
        (cfg.get("visual_style") or "").strip().lower(),
        (cfg.get("category") or "").strip().lower(),
    )
    return fallback_index.get(key) or None


@niches_bp.route("/api/niches/preview-index", methods=["GET"])
def niche_preview_index():
    """Return the set of preset IDs that have at least one pipeline run.

    Used by the Jobs panel to mark which niche chips are previewable
    without having to click each one.
    """
    available = set()
    fallback_index = _build_style_category_index()
    if os.path.isdir(PIPELINE_DIR):
        for entry in os.listdir(PIPELINE_DIR):
            pj = os.path.join(PIPELINE_DIR, entry, "pipeline.json")
            if not os.path.isfile(pj):
                continue
            try:
                data = safe_json_read(pj)
            except Exception:
                continue
            cfg = data.get("config", {}) or {}
            pid = _resolve_preset_for_run(cfg, fallback_index)
            if pid:
                available.add(pid)
    return jsonify({"preset_ids": sorted(available)})


@niches_bp.route("/api/niches/<preset_id>/preview", methods=["GET"])
def preview_niche(preset_id):
    """Return a 4-tile preview (text/audio/images/video) of the most recent
    pipeline run that used this niche preset.

    Returns 200 with `{ found: false }` if no run for this preset exists yet.
    """
    target = normalize_preset_id(preset_id)
    if not target:
        return jsonify({"found": False, "reason": "invalid preset id"})

    # Walk pipeline.json files, keep only ones tagged with this preset
    fallback_index = _build_style_category_index()
    candidates = []
    if os.path.isdir(PIPELINE_DIR):
        for entry in os.listdir(PIPELINE_DIR):
            pj = os.path.join(PIPELINE_DIR, entry, "pipeline.json")
            if not os.path.isfile(pj):
                continue
            try:
                data = safe_json_read(pj)
            except Exception:
                continue
            cfg = data.get("config", {}) or {}
            if _resolve_preset_for_run(cfg, fallback_index) != target:
                continue
            candidates.append((os.path.getmtime(pj), entry, data, cfg))

    if not candidates:
        return jsonify({"found": False})

    def _has_video(pid):
        if not os.path.isdir(EXPORT_DIR):
            return False
        for root, _d, files in os.walk(EXPORT_DIR):
            for fn in files:
                if fn.startswith(pid) and fn.lower().endswith((".mp4", ".mov", ".webm", ".mkv", ".m4v")):
                    return True
        return False

    def _has_images(pid):
        sb = os.path.join(STORYBOARD_DIR, pid)
        if not os.path.isdir(sb):
            return False
        for e in os.listdir(sb):
            if e.isdigit() and os.path.isdir(os.path.join(sb, e)):
                return True
        return False

    # Rank candidates by (succeeded, has_video, has_images, mtime) so the
    # preview prefers the most recent fully-completed run rather than a
    # partial TTS-only or errored one.
    def _rank(c):
        mtime, pid, data_, _cfg = c
        succeeded = int(data_.get("status") == "done")
        return (succeeded, int(_has_video(pid)), int(_has_images(pid)), mtime)

    candidates.sort(key=_rank, reverse=True)
    _, project_id, data, cfg = candidates[0]

    # ── Text ──
    text = (cfg.get("text") or "").strip()

    # ── Audio (TTS voice.wav) ──
    audio_url = ""
    tts_dir = os.path.join(TTS_DIR, project_id)
    if os.path.isdir(tts_dir):
        for fname in ("voice.wav", "voice.mp3"):
            if os.path.isfile(os.path.join(tts_dir, fname)):
                audio_url = f"/output/tts/{project_id}/{fname}"
                break
        if not audio_url:
            # Fallback: first audio file we find
            for fname in sorted(os.listdir(tts_dir)):
                if fname.lower().endswith((".wav", ".mp3", ".m4a", ".ogg")):
                    audio_url = f"/output/tts/{project_id}/{fname}"
                    break

    # ── Images (storyboard scenes) ──
    images = []
    sb_dir = os.path.join(STORYBOARD_DIR, project_id)
    if os.path.isdir(sb_dir):
        image_exts = (".jpg", ".jpeg", ".png", ".webp")
        try:
            scene_dirs = sorted(
                (e for e in os.listdir(sb_dir) if e.isdigit() and os.path.isdir(os.path.join(sb_dir, e))),
                key=lambda s: int(s),
            )
        except Exception:
            scene_dirs = []
        for scene in scene_dirs:
            scene_path = os.path.join(sb_dir, scene)
            for fname in os.listdir(scene_path):
                if fname.startswith("image") and fname.lower().endswith(image_exts):
                    images.append(f"/output/storyboard/{project_id}/{scene}/{fname}")
                    break
            if len(images) >= 8:
                break

    # ── Video (latest export for this project) ──
    video_url = ""
    if os.path.isdir(EXPORT_DIR):
        best_video = None
        best_mtime = -1.0
        for root, _dirs, files in os.walk(EXPORT_DIR):
            for fname in files:
                if not fname.lower().endswith((".mp4", ".mov", ".webm", ".mkv", ".m4v")):
                    continue
                # Match files starting with the project id (export uses pid_<hash>.mp4)
                if not fname.startswith(project_id):
                    continue
                fpath = os.path.join(root, fname)
                m = os.path.getmtime(fpath)
                if m > best_mtime:
                    best_mtime = m
                    rel = os.path.relpath(fpath, EXPORT_DIR).replace("\\", "/")
                    best_video = rel
        if best_video:
            video_url = f"/api/export/library/preview/{quote(best_video, safe='/')}"

    # Voice name — prefer the explicit TTS voice when set, else fall back to
    # the Kokoro voice. Inworld voices are stored in `tts_voice`/`inworld_voice`.
    voice = (
        cfg.get("tts_voice")
        or cfg.get("inworld_voice")
        or cfg.get("voice")
        or ""
    )
    tts_provider = cfg.get("tts_provider") or ""

    # ── Background music + SFX (read from the editor's working state:
    # prefer work@in@progress.json — which has the user's latest edits
    # like a manual replace/random pick — falling back to the pristine
    # initial.json from the assemble step) ──
    bg_music_name = ""
    bg_music_url = ""
    sfx_name = ""
    sfx_url = ""
    proj_dir = os.path.join(PROJECTS_DIR, project_id)
    audio_source = None
    for fname in ("work@in@progress.json", "initial.json"):
        candidate = os.path.join(proj_dir, fname)
        if os.path.isfile(candidate):
            audio_source = candidate
            break
    if audio_source:
        try:
            data = safe_json_read(audio_source) or {}
            for track in data.get("audio_tracks") or []:
                if not isinstance(track, dict):
                    continue
                if track.get("muted"):
                    continue
                ttype = (track.get("type") or "").lower()
                tpath = track.get("path") or ""
                tfile = track.get("file") or os.path.basename(tpath)
                if ttype == "music" and not bg_music_name:
                    bg_music_name = os.path.splitext(tfile)[0]
                    bg_music_url = tpath
                elif ttype == "sfx" and not sfx_name:
                    sfx_name = os.path.splitext(tfile)[0]
                    sfx_url = tpath
        except Exception:
            pass

    return jsonify({
        "found": True,
        "preset_id": target,
        "project_id": project_id,
        "created": data.get("timestamp", "") or "",
        "stop_after": cfg.get("stop_after") or "",
        "status": data.get("status", ""),
        "error_step": data.get("error_step") or "",
        "voice": voice,
        "tts_provider": tts_provider,
        "bg_music_name": bg_music_name,
        "bg_music_url": bg_music_url,
        "sfx_name": sfx_name,
        "sfx_url": sfx_url,
        "text": text,
        "audio_url": audio_url,
        "images": images,
        "video_url": video_url,
    })
