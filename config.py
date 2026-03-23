"""ScriptToScene Studio — Centralized Configuration

Single source of truth for all directory paths, environment variables,
and shared constants. Import from here instead of computing paths manually.
"""

APP_VERSION = "0.1.0"

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Root directory (where app.py lives)
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Directory paths
# ---------------------------------------------------------------------------
STATIC_DIR = os.path.join(ROOT_DIR, "static")
LOG_DIR = os.path.join(ROOT_DIR, "logs")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
TRASH_DIR = os.path.join(OUTPUT_DIR, "TRASH")
ALIGN_DIR = os.path.join(OUTPUT_DIR, "alignments")
SCENES_DIR = os.path.join(OUTPUT_DIR, "scenes")
STORIES_DIR = os.path.join(OUTPUT_DIR, "stories")
PIPELINE_DIR = os.path.join(OUTPUT_DIR, "pipeline")
ASSETS_DIR = os.path.join(OUTPUT_DIR, "assets")
STORYBOARD_DIR = os.path.join(OUTPUT_DIR, "storyboard")
SEGMENTER_DIR = os.path.join(OUTPUT_DIR, "segmenters")
CAPTIONS_DIR = os.path.join(OUTPUT_DIR, "captions")
MUSIC_DIR = os.path.join(OUTPUT_DIR, "musics")
TTS_DIR = os.path.join(OUTPUT_DIR, "tts")
MODELS_DIR = os.path.join(ROOT_DIR, "models")
# Editor is now inlined in static/ — this path is kept for backward compat only
TIMELINE_EDITOR_DIR = os.path.join(ROOT_DIR, "static")
BIN_DIR = os.path.join(ROOT_DIR, "bin")
FONTS_DIR = os.path.join(ROOT_DIR, "assets", "fonts")
EXPORT_DIR = os.path.join(OUTPUT_DIR, "exports")
PROJECTS_DIR = os.path.join(OUTPUT_DIR, "projects")
THUMBNAILS_DIR = os.path.join(OUTPUT_DIR, "thumbnails")
TMP_DIR = os.path.join(ROOT_DIR, "tmp")
TTS_CACHE_DIR = os.path.join(TMP_DIR, "tts")
APP_ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
APP_CONFIG_PATH = os.path.join(ROOT_DIR, "app-config.json")
# ---------------------------------------------------------------------------
# Ensure output directories exist
# ---------------------------------------------------------------------------
for _d in (LOG_DIR, TRASH_DIR, ALIGN_DIR, SCENES_DIR, STORIES_DIR, PIPELINE_DIR, ASSETS_DIR,
           STORYBOARD_DIR, SEGMENTER_DIR, CAPTIONS_DIR, MUSIC_DIR, TTS_DIR, MODELS_DIR,
           EXPORT_DIR, PROJECTS_DIR, THUMBNAILS_DIR, TTS_CACHE_DIR):
    os.makedirs(_d, exist_ok=True)

# ---------------------------------------------------------------------------
# External service URLs (env-overridable)
# ---------------------------------------------------------------------------
N8N_WEBHOOK_URL = os.environ.get(
    "N8N_WEBHOOK_URL", "http://localhost:5678/webhook/scene-blueprint-generator"
)
N8N_ASSET_WEBHOOK_URL = os.environ.get(
    "N8N_ASSET_WEBHOOK_URL", "http://localhost:5678/webhook/image-generator"
)
N8N_STORY_WEBHOOK_URL = os.environ.get(
    "N8N_STORY_WEBHOOK_URL", "http://localhost:5678/webhook/story-generator"
)
N8N_STORYBOARD_WEBHOOK_URL = os.environ.get(
    "N8N_STORYBOARD_WEBHOOK_URL", "https://n8n-production-6197.up.railway.app/webhook/storyboard-generator"
)
N8N_CLASSIFY_WEBHOOK_URL = os.environ.get(
    "N8N_CLASSIFY_WEBHOOK_URL", "http://localhost:5678/webhook/classify-style"
)

# ---------------------------------------------------------------------------
# Kie AI image generation
# ---------------------------------------------------------------------------
KIE_AI_API_KEY = os.environ.get("KIE_AI_API_KEY", "")
KIE_AI_BASE_URL = os.environ.get("KIE_AI_BASE_URL", "https://api.kie.ai/api/v1")
KIE_AI_MODEL = os.environ.get("KIE_AI_MODEL", "google/nano-banana")

# ---------------------------------------------------------------------------
# WaveSpeed AI (Storyboard image generation)
# ---------------------------------------------------------------------------
WAVESPEED_API_KEY = os.environ.get("WAVESPEED_API_KEY", "")

# ---------------------------------------------------------------------------
# Project ID generator
# ---------------------------------------------------------------------------
import random
import string
from datetime import datetime as _dt


def _collect_existing_project_ids() -> set[str]:
    """Scan project-bearing output locations for identifiers already in use."""
    existing = set()
    dir_only_roots = (
        ALIGN_DIR,
        SCENES_DIR,
        ASSETS_DIR,
        STORYBOARD_DIR,
        SEGMENTER_DIR,
        CAPTIONS_DIR,
        TTS_DIR,
    )
    for search_dir in dir_only_roots:
        if not os.path.isdir(search_dir):
            continue
        for entry in os.listdir(search_dir):
            if os.path.isdir(os.path.join(search_dir, entry)):
                existing.add(entry)

    if os.path.isdir(PROJECTS_DIR):
        for entry in os.listdir(PROJECTS_DIR):
            if os.path.isdir(os.path.join(PROJECTS_DIR, entry)):
                existing.add(entry)

    return existing

def generate_project_id(prefix="pm"):
    """Generate a unique project ID like pm_SLLGTM or pp_A3F82K.

    Prefixes:
      pm  — project created manually (editor / timing)
      pp  — project created via pipeline

    Scans existing output directories to avoid collisions.
    """
    existing = _collect_existing_project_ids()

    charset = string.ascii_uppercase + string.digits
    for _ in range(100):
        candidate = f"{prefix}_" + "".join(random.choices(charset, k=6))
        if candidate not in existing:
            return candidate

    # Fallback: timestamp suffix to guarantee uniqueness
    return f"{prefix}_" + _dt.now().strftime("%H%M%S") + "".join(random.choices(charset, k=3))
