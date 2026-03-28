"""Auto-select background music based on story_tone."""
import os
import random

from loguru import logger

from config import APP_ASSETS_DIR

_MUSIC_ROOT = os.path.join(APP_ASSETS_DIR, "sounds", "music")

_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}

# story_tone → ordered list of music sub-folders (primary first, fallbacks after)
TONE_MUSIC_MAP = {
    "suspenseful":   ["dark", "viral-slowed", "cinematic"],
    "dramatic":      ["cinematic", "dark", "viral-slowed"],
    "educational":   ["ambient", "cinematic"],
    "inspirational": ["cinematic", "happy"],
    "comedic":       ["happy", "viral-hiphop"],
    "wholesome":     ["happy", "ambient"],
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


def select_music(story_tone):
    """Pick a random music track matching the story_tone.

    Returns a bgMusic dict ready for the export payload, or None if no
    tracks are available.
    """
    folders = TONE_MUSIC_MAP.get(story_tone)
    if not folders:
        logger.debug("No music mapping for story_tone '{}', skipping auto-music", story_tone)
        return None

    for folder_name in folders:
        tracks = _list_tracks(os.path.join(_MUSIC_ROOT, folder_name))
        if tracks:
            chosen = random.choice(tracks)
            logger.info("Auto-music: tone='{}' → folder='{}' → '{}'",
                        story_tone, folder_name, os.path.basename(chosen))
            return {
                "path": chosen,
                "volume": 0.15,
                "fade_in": 2.0,
                "fade_out": 3.0,
                "loop": True,
                "ducking_enabled": True,
                "ducking_level": 0.2,
            }

    logger.warning("Auto-music: no tracks found for tone '{}' in folders {}", story_tone, folders)
    return None
