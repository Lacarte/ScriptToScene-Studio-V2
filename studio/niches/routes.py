from flask import Blueprint, jsonify

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
