"""Self-improver configuration — paths, thresholds, scoring weights, API URLs."""

import os
from dataclasses import dataclass
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
TTS_DIR = OUTPUT_DIR / "tts"
ALIGN_DIR = OUTPUT_DIR / "alignments"
SEGMENT_DIR = OUTPUT_DIR / "segmenters"
SCENES_DIR = OUTPUT_DIR / "scenes"
STORYBOARD_DIR = OUTPUT_DIR / "storyboard"
PIPELINE_DIR = OUTPUT_DIR / "pipeline"
REPORT_PATH = Path(__file__).resolve().parent / "self-improvement-report.md"

# ── API ──────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("STS_BASE_URL", "http://localhost:5050")
PIPELINE_RUN_URL = f"{BASE_URL}/api/pipeline/run"
PIPELINE_PROGRESS_URL = f"{BASE_URL}/api/pipeline/progress"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "google/gemini-2.5-flash"

# ── Loop defaults ────────────────────────────────────────────────────────

DEFAULT_MAX_ITERATIONS = 5
POLL_INTERVAL_SECONDS = 2
PIPELINE_TIMEOUT_SECONDS = 900  # 15 min

# Step name mapping (CLI names → pipeline API names)
STEP_NAMES = {
    "tts": "tts",
    "alignment": "timing",
    "segments": "segment",
    "scenes": "scenes",
    "storyboard": "storyboard",
}
ALL_STEPS = list(STEP_NAMES.keys())

# Ordered pipeline steps for resume_from logic
PIPELINE_STEP_ORDER = ["tts", "timing", "segment", "scenes", "storyboard"]


# ── Heuristic Thresholds ─────────────────────────────────────────────────

@dataclass
class TTSThresholds:
    min_wps: float = 2.0
    max_wps: float = 4.5
    min_duration: float = 10.0
    max_duration: float = 60.0


@dataclass
class AlignmentThresholds:
    max_word_drift_ms: float = 200
    max_zero_duration_pct: float = 5
    max_gap_ms: float = 1500


@dataclass
class SegmentThresholds:
    ideal_min_duration: float = 1.5
    ideal_max_duration: float = 4.5
    hard_max_break_pct: float = 20
    min_segments: int = 4
    max_segments: int = 25
    cv_threshold: float = 0.6


@dataclass
class SceneThresholds:
    min_prompt_length: int = 80
    max_prompt_length: int = 500
    max_consecutive_same_shot: int = 1
    required_roles: tuple = ("hook", "peak", "cta")
    min_role_variety: int = 4
    min_type_variety: int = 2  # need both video and text scenes


@dataclass
class StoryboardThresholds:
    max_error_rate: float = 10


@dataclass
class ImageThresholds:
    min_style_consistency: int = 75
    min_composition_quality: int = 75
    min_prompt_adherence: int = 70
    min_visual_flow: int = 65


@dataclass
class CrossModuleThresholds:
    max_segment_scene_mismatch: int = 0
    max_timing_drift_ms: float = 500


THRESHOLDS = {
    "tts": TTSThresholds(),
    "alignment": AlignmentThresholds(),
    "segments": SegmentThresholds(),
    "scenes": SceneThresholds(),
    "storyboard": StoryboardThresholds(),
    "images": ImageThresholds(),
    "cross": CrossModuleThresholds(),
}


# ── Scoring Weights ──────────────────────────────────────────────────────

@dataclass
class ScoringWeights:
    style_consistency: float = 0.20
    visual_quality: float = 0.20
    narrative_coherence: float = 0.25
    audio_visual_sync: float = 0.15
    viral_score: float = 0.20


WEIGHTS = ScoringWeights()
