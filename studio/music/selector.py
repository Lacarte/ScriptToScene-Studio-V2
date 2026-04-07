"""Auto-select background music based on story_tone."""
import json
import os
import random
from collections import deque

from loguru import logger

from config import APP_ASSETS_DIR, OUTPUT_DIR

_MUSIC_ROOT = os.path.join(APP_ASSETS_DIR, "sounds", "music")
_HISTORY_FILE = os.path.join(OUTPUT_DIR, "music_history.json")
_HISTORY_LIMIT = 10  # remember last 10 picks across all projects

_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}

# story_tone → ordered list of music sub-folders (primary first, fallbacks after)
#
# Available folders:
#   ambient   — universal, fits any story (chill background presence)
#   chill     — smooth ambient-like with hip-hop kick, modern relaxed
#   dark      — terror, sad, scary, dread, suspense
#   romantic  — chill lofi for love/wholesome/feel-good
#   historic  — period/historical narration
#   religion  — sacred, reverent
TONE_MUSIC_MAP = {
    "suspenseful":   ["dark", "ambient", "chill"],
    "dramatic":      ["dark", "ambient", "chill", "historic"],
    "religious":     ["religion", "ambient", "dark"],
    "educational":   ["ambient", "chill", "historic"],
    "inspirational": ["chill", "ambient", "romantic"],
    "comedic":       ["chill", "ambient", "romantic"],
    "wholesome":     ["romantic", "chill", "ambient"],
}


def _list_tracks(folder):
    """Return list of audio file paths in a folder."""
    if not os.path.isdir(folder):
        return []
    return [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in _AUDIO_EXTS
        and os.path.isfile(os.path.join(folder, f))
    ]


def _load_history():
    """Load recently-used music tracks from disk."""
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            return list(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_history(history):
    """Persist recently-used music tracks."""
    try:
        os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history[-_HISTORY_LIMIT:], f)
    except OSError as e:
        logger.debug("Could not save music history: {}", e)


def _pick_with_history(tracks, history):
    """Pick a random track preferring those NOT in recent history.

    Falls back to fully random if all tracks are in history (small library).
    """
    if not tracks:
        return None
    fresh = [t for t in tracks if t not in history]
    if fresh:
        return random.choice(fresh)
    return random.choice(tracks)


def select_music(story_tone):
    """Pick a random music track matching the story_tone.

    Uses a no-repeat history so the same track isn't picked twice in a row
    across recent projects.  Returns a bgMusic dict ready for the export
    payload, or None if no tracks are available.
    """
    folders = TONE_MUSIC_MAP.get(story_tone)
    if not folders:
        logger.debug("No music mapping for story_tone '{}', skipping auto-music", story_tone)
        return None

    history = _load_history()

    for folder_name in folders:
        tracks = _list_tracks(os.path.join(_MUSIC_ROOT, folder_name))
        if tracks:
            chosen = _pick_with_history(tracks, history)
            if not chosen:
                continue
            # Update history
            history.append(chosen)
            _save_history(history)
            logger.info("Auto-music: tone='{}' → folder='{}' → '{}'",
                        story_tone, folder_name, os.path.basename(chosen))
            return {
                "path": chosen,
                "volume": 0.15,
                "fade_in": 2.0,
                "fade_out": 3.0,
                "loop": True,
                "ducking_enabled": True,
                "ducking_level": 0.45,
            }

    logger.warning("Auto-music: no tracks found for tone '{}' in folders {}", story_tone, folders)
    return None
