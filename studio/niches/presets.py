"""Niche presets — user-facing combinations of visual style + story tone + defaults.

A niche is a marketable content angle. Selecting a niche auto-fills:
  - category (broad topic)
  - visual_style (template ID for scene rendering)
  - story_tone (narration tone keyword)
  - voice, speed (TTS defaults)
  - editing_style (future: pacing preset)

Presets are stored in _data/niche_presets.json. The Python DEFAULTS below are
used only when the JSON file doesn't exist yet (first run).
"""

import json
import re
from pathlib import Path

from studio.scenes.templates import SCENE_STYLE_TEMPLATES, TEMPLATES_BY_ID

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "_data"
_PRESETS_FILE = _DATA_DIR / "niche_presets.json"
_VALID_TAGS = ("tiktok", "youtube", "shorts", "trending")
_DEFAULT_VOICE = "af_heart"
_DEFAULT_SPEED = 1.0

# ── Hardcoded defaults (used if JSON file is missing) ────────────────────────
_DEFAULTS = {
    "dark_psychology_stickman": {
        "label": "Stickman Dark Psychology",
        "description": "Minimalist stickman visuals with dark psychological narration. Suspenseful tone, fast-paced for TikTok/Shorts.",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "stickman_animation",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.95,
        "tags": ["trending", "tiktok", "shorts"],
    },
    "dark_psychology_cinematic": {
        "label": "Cinematic Dark Psychology",
        "description": "Cinematic visuals with psychological tension. Film-quality lighting and dramatic framing.",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "cinematic",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.95,
        "tags": ["youtube", "shorts"],
    },
}

# ── Story tones — narration style keywords for the LLM ──────────────────────
STORY_TONES = {
    "suspenseful": "Dark, tense, slow-building dread. Use short punchy sentences. Build unease.",
    "dramatic": "Emotional weight, vivid imagery, strong narrative arc. Vary sentence rhythm.",
    "educational": "Clear, authoritative, insightful. Teach through story, not lecture.",
    "inspirational": "Uplifting, empowering, forward-looking. End with a call to action.",
    "comedic": "Witty, unexpected twists, conversational. Subvert expectations.",
    "wholesome": "Warm, gentle, age-appropriate. Simple language, positive resolution.",
}

# ── All valid categories ─────────────────────────────────────────────────────
CATEGORIES = [
    "psychology", "crime", "horror", "motivation", "philosophy",
    "religion", "mystery", "science", "history", "nature",
    "romance", "comedy", "children", "anecdote", "politics",
    "survival", "curiosity", "space",
]


# ── Load / Save ──────────────────────────────────────────────────────────────

def _clean_text(value, *, max_length=120) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text[:max_length].strip()


def _normalize_slug(value) -> str:
    text = _clean_text(value, max_length=80).lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _normalize_speed(value, *, default=_DEFAULT_SPEED) -> float:
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return max(0.5, min(2.0, round(speed, 2)))


def _normalize_tags(tags) -> list[str]:
    if not isinstance(tags, list):
        return []
    seen = set()
    normalized = []
    for raw_tag in tags:
        tag = _normalize_slug(raw_tag)
        if not tag or tag not in _VALID_TAGS or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
    return normalized[:4]


def get_visual_styles() -> list[dict]:
    """Return the list of selectable visual styles for niche presets."""
    return [
        {"id": t["id"], "name": t["name"], "color": t.get("color", "#888")}
        for t in SCENE_STYLE_TEMPLATES
        if t.get("type") in ("visual", "hybrid")
    ]


def is_known_template(style_id: str) -> bool:
    return _normalize_slug(style_id) in TEMPLATES_BY_ID


def is_valid_visual_style(style_id: str) -> bool:
    candidate = _normalize_slug(style_id)
    return any(style["id"] == candidate for style in get_visual_styles())


def is_valid_story_tone(tone_id: str) -> bool:
    return _normalize_slug(tone_id) in STORY_TONES


def is_valid_category(category_id: str) -> bool:
    return _normalize_slug(category_id) in CATEGORIES


def normalize_preset_id(value) -> str:
    return _normalize_slug(value)


def normalize_story_tone(value) -> str:
    return _normalize_slug(value)


def normalize_category(value) -> str:
    return _normalize_slug(value)


def normalize_visual_style(value) -> str:
    return _normalize_slug(value)


def is_builtin_preset(preset_id: str) -> bool:
    return normalize_preset_id(preset_id) in _DEFAULTS


def preset_exists(preset_id: str) -> bool:
    return normalize_preset_id(preset_id) in get_presets()


def normalize_preset_payload(preset_id: str, data: dict) -> tuple[str, dict]:
    """Normalize and validate a niche preset payload."""
    preset_key = normalize_preset_id(preset_id)
    if not preset_key:
        raise ValueError("Preset id is required")

    label = _clean_text((data or {}).get("label"), max_length=60)
    if len(label) < 3:
        raise ValueError("Preset label must be at least 3 characters")

    category = normalize_category((data or {}).get("category"))
    if not is_valid_category(category):
        raise ValueError(f"Unknown category '{data.get('category', '')}'")

    niche = normalize_preset_id((data or {}).get("niche") or category)
    if not niche:
        raise ValueError("Preset niche is required")

    visual_style = normalize_visual_style((data or {}).get("visual_style"))
    if not is_valid_visual_style(visual_style):
        raise ValueError(f"Unknown visual style '{data.get('visual_style', '')}'")

    story_tone = normalize_story_tone((data or {}).get("story_tone"))
    if not is_valid_story_tone(story_tone):
        raise ValueError(f"Unknown story tone '{data.get('story_tone', '')}'")

    normalized = {
        "label": label,
        "description": _clean_text((data or {}).get("description"), max_length=240),
        "category": category,
        "niche": niche,
        "visual_style": visual_style,
        "story_tone": story_tone,
        "voice": _clean_text((data or {}).get("voice"), max_length=40) or _DEFAULT_VOICE,
        "speed": _normalize_speed((data or {}).get("speed"), default=_DEFAULT_SPEED),
        "tags": _normalize_tags((data or {}).get("tags", [])),
        "thumbnail": _clean_text((data or {}).get("thumbnail"), max_length=120),
        "custom": bool((data or {}).get("custom", False)),
    }

    if not normalized["thumbnail"]:
        normalized.pop("thumbnail")
    if not normalized["description"]:
        normalized.pop("description")
    if not normalized["tags"]:
        normalized["tags"] = []

    return preset_key, normalized


def _normalize_presets_map(raw_presets: dict) -> dict:
    if not isinstance(raw_presets, dict):
        return {}

    normalized = {}
    for preset_id, data in raw_presets.items():
        try:
            key, value = normalize_preset_payload(preset_id, data or {})
        except ValueError:
            continue
        normalized[key] = value
    return normalized


def _load_presets() -> dict:
    """Load presets from JSON file, falling back to defaults when needed."""
    raw_presets = None
    if _PRESETS_FILE.exists():
        try:
            with open(_PRESETS_FILE, "r", encoding="utf-8") as f:
                raw_presets = json.load(f)
        except (OSError, json.JSONDecodeError):
            raw_presets = None
    normalized = _normalize_presets_map(raw_presets or _DEFAULTS)
    return normalized or _normalize_presets_map(_DEFAULTS)


def _save_presets(presets: dict) -> None:
    """Write presets to JSON file."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(_normalize_presets_map(presets), f, indent=2, ensure_ascii=False)


def get_presets() -> dict:
    """Get all niche presets (always fresh from disk)."""
    return _load_presets()


def save_preset(preset_id: str, data: dict) -> dict:
    """Save or update a single niche preset. Returns the full presets dict."""
    if is_builtin_preset(preset_id):
        raise ValueError("Built-in presets cannot be overwritten")
    presets = _load_presets()
    key, normalized = normalize_preset_payload(preset_id, data)
    if key in presets:
        raise ValueError(f"Preset '{key}' already exists")
    presets[key] = normalized
    _save_presets(presets)
    return presets


def delete_preset(preset_id: str) -> dict:
    """Delete a niche preset by ID. Returns the full presets dict."""
    key = normalize_preset_id(preset_id)
    if not key:
        raise ValueError("Preset id is required")
    if is_builtin_preset(key):
        raise ValueError("Built-in presets cannot be deleted")
    presets = _load_presets()
    if key not in presets:
        raise ValueError(f"Unknown preset '{key}'")
    presets.pop(key, None)
    _save_presets(presets)
    return presets


# ── Backward-compat module-level export ──────────────────────────────────────
NICHE_PRESETS = _load_presets()


# ── Resolve niche → pipeline dimensions ──────────────────────────────────────

def resolve_niche(config: dict) -> dict:
    """Resolve a niche preset into pipeline dimensions.

    Accepts a config dict with any combination of:
      - niche_preset: preset ID (auto-fills everything)
      - style: legacy template ID (backward compat)
      - visual_style: override visual template
      - story_tone: override narration tone
      - voice, speed: override TTS defaults

    Returns dict with resolved: visual_style, story_tone, category, voice, speed
    """
    presets = get_presets()
    preset_id = normalize_preset_id((config or {}).get("niche_preset"))
    preset = presets.get(preset_id) if preset_id else None

    legacy_style = normalize_visual_style((config or {}).get("style")) or "cinematic"
    requested_visual_style = normalize_visual_style((config or {}).get("visual_style"))
    requested_story_tone = normalize_story_tone((config or {}).get("story_tone"))
    requested_category = normalize_category((config or {}).get("category"))
    voice = _clean_text((config or {}).get("voice"), max_length=40)
    speed = _normalize_speed((config or {}).get("speed"), default=preset.get("speed", _DEFAULT_SPEED) if preset else _DEFAULT_SPEED)

    visual_style = requested_visual_style if is_valid_visual_style(requested_visual_style) else ""
    if not visual_style and preset and is_valid_visual_style(preset.get("visual_style")):
        visual_style = preset["visual_style"]
    if not visual_style and is_known_template(legacy_style):
        visual_style = legacy_style
    if not visual_style:
        visual_style = "cinematic"

    story_tone = requested_story_tone if is_valid_story_tone(requested_story_tone) else ""
    if not story_tone and preset and is_valid_story_tone(preset.get("story_tone")):
        story_tone = preset["story_tone"]

    category = requested_category if is_valid_category(requested_category) else ""
    if not category and preset and is_valid_category(preset.get("category")):
        category = preset["category"]

    return {
        "visual_style": visual_style,
        "story_tone": story_tone or None,
        "category": category or None,
        "niche": preset.get("niche") if preset else None,
        "voice": voice or (preset.get("voice", _DEFAULT_VOICE) if preset else _DEFAULT_VOICE),
        "speed": speed,
    }
