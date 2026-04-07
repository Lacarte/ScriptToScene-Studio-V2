"""Captions Module — Load caption presets and project data."""

import json
import os

from flask import Blueprint, jsonify
from loguru import logger

from config import APP_ASSETS_DIR, CAPTIONS_DIR

captions_bp = Blueprint("captions", __name__)

# ---------------------------------------------------------------------------
# Caption style presets
# ---------------------------------------------------------------------------
CAPTION_PRESETS = {
    "bold_popup": {
        "id": "bold_popup",
        "name": "Bold Pop-up",
        "description": "YouTube Shorts style — big, bold, uppercase",
        "font_family": "Montserrat",
        "font_size": 64,
        "font_weight": "800",
        "color": "#FFFFFF",
        "stroke_color": "none",
        "stroke_width": 0,
        "background": "none",
        "position_y": 75,
        "animation": "pop",
        "text_transform": "uppercase",
        "shadow_color": "#000000",
        "shadow_blur": 8,
        "shadow_offset_x": 2,
        "shadow_offset_y": 2,
    },
    "subtitle_bar": {
        "id": "subtitle_bar",
        "name": "Subtitle Bar",
        "description": "Clean subtitle with dark background bar",
        "font_family": "Inter",
        "font_size": 42,
        "font_weight": "600",
        "color": "#FFFFFF",
        "stroke_color": "none",
        "stroke_width": 0,
        "background": "rgba(0,0,0,0.7)",
        "position_y": 85,
        "animation": "fade",
        "text_transform": "none",
    },
    "karaoke": {
        "id": "karaoke",
        "name": "Karaoke Highlight",
        "description": "Words light up as they're spoken",
        "font_family": "Montserrat",
        "font_size": 72,
        "font_weight": "400",
        "color": "#FFFFFF",
        "highlight_color": "#4ECDC4",
        "stroke_color": "#000000",
        "stroke_width": 3,
        "background": "none",
        "position_y": 70,
        "animation": "highlight",
        "text_transform": "uppercase",
    },
    "minimal": {
        "id": "minimal",
        "name": "Minimal",
        "description": "Small, clean, unobtrusive captions",
        "font_family": "DM Sans",
        "font_size": 36,
        "font_weight": "500",
        "color": "#FFFFFF",
        "stroke_color": "none",
        "stroke_width": 0,
        "background": "none",
        "position_y": 80,
        "animation": "fade",
        "text_transform": "none",
    },
    "single_line": {
        "id": "single_line",
        "name": "Single Line",
        "description": "Negative blend text — viral short-form style",
        "font_family": "Montserrat",
        "font_size": 80,
        "font_weight": "900",
        "color": "#FFFFFF",
        "stroke_color": "none",
        "stroke_width": 0,
        "background": "none",
        "position_y": 81,
        "animation": "hard_cut",
        "text_transform": "uppercase",
        "letter_spacing": -2,
        "blend_mode": "difference",
        "shadow_color": "rgba(0,0,0,1.00)",
        "shadow_blur": 10,
        "shadow_offset_x": 3,
        "shadow_offset_y": 3,
        "diff_strength": 0.59,
        "overlay_strength": 0.37,
        "overlay_color": "#ffffff",
        "edge_fade_ms": 90,
    },
}


def _load_external_presets():
    """Load additional caption presets from assets/caption-presets/*.json."""
    preset_path = os.path.join(APP_ASSETS_DIR, "caption-presets", "pro-caption-presets.json")
    if not os.path.isfile(preset_path):
        return {}

    try:
        with open(preset_path, encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load caption presets from {}: {}", preset_path, exc)
        return {}

    # Support both {"presets":[...]} and plain list formats.
    if isinstance(payload, dict):
        items = payload.get("presets", [])
    elif isinstance(payload, list):
        items = payload
    else:
        logger.warning("Invalid caption preset payload type in {}", preset_path)
        return {}

    loaded = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        preset_id = str(item.get("id", "")).strip()
        if not preset_id:
            continue
        loaded[preset_id] = item

    if loaded:
        logger.info("Loaded {} external caption presets from {}", len(loaded), preset_path)
    return loaded


CAPTION_PRESETS.update(_load_external_presets())


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@captions_bp.route("/api/captions/presets")
def get_presets():
    """Return all available caption style presets."""
    return jsonify(list(CAPTION_PRESETS.values()))


@captions_bp.route("/api/captions/<project_id>")
def get_captions(project_id):
    """Get full caption data for a project."""
    project_id = os.path.basename(project_id)
    json_path = os.path.join(CAPTIONS_DIR, project_id, "captions.json")
    if os.path.isfile(json_path):
        try:
            with open(json_path, encoding="utf-8") as f:
                return jsonify(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            return jsonify({"error": f"Failed to read caption data: {e}"}), 500

    # Fallback: build captions from alignment data
    from config import ALIGN_DIR
    align_path = os.path.join(ALIGN_DIR, project_id, "alignment.json")
    if os.path.isfile(align_path):
        try:
            with open(align_path, encoding="utf-8") as f:
                align = json.load(f)
            words = align.get("alignment", [])
            if words:
                return jsonify({
                    "project_id": project_id,
                    "source_folder": project_id,
                    "words": [
                        {"word": w["word"], "start": w.get("begin", 0), "end": w.get("end", 0)}
                        for w in words
                    ],
                    "transcript": align.get("transcript", ""),
                    "from_alignment": True,
                })
        except Exception:
            pass

    return jsonify({"error": "Not found"}), 404
