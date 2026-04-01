"""Pydantic schemas for Pipeline routes."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from studio.niches.presets import (
    is_known_template,
    is_valid_category,
    is_valid_story_tone,
    is_valid_visual_style,
    normalize_category,
    normalize_preset_id,
    normalize_story_tone,
    normalize_visual_style,
    preset_exists,
)

_VALID_STEPS = ("tts", "timing", "alignment", "segment", "scenes", "storyboard", "assets", "assemble", "export")


class PipelineRunRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    voice: str = "af_heart"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    style: str = "cinematic"
    niche_preset: Optional[str] = None
    visual_style: Optional[str] = None
    story_tone: Optional[str] = None
    category: Optional[str] = None
    segment_config: Optional[dict] = None
    webhook_url: Optional[str] = None
    style_prompt: Optional[str] = None
    custom_style_notes: Optional[str] = None
    auto_scenes: bool = True
    auto_storyboard: bool = True
    stop_after: Optional[str] = None
    tts_provider: str = "kokoro"  # "kokoro" or "inworld"
    tts_voice: Optional[str] = None  # Inworld voice ID (uses voice field for Kokoro)
    resume_from: Optional[str] = None
    resume_project_id: Optional[str] = None

    @model_validator(mode="after")
    def _validate_steps(self):
        self.text = self.text.strip()
        if not self.text:
            raise ValueError("text cannot be blank")
        self.voice = (self.voice or "af_heart").strip() or "af_heart"
        self.style = normalize_visual_style(self.style) or "cinematic"
        self.niche_preset = normalize_preset_id(self.niche_preset) or None
        self.visual_style = normalize_visual_style(self.visual_style) or None
        self.story_tone = normalize_story_tone(self.story_tone) or None
        self.category = normalize_category(self.category) or None
        self.webhook_url = (self.webhook_url or "").strip() or None
        self.style_prompt = (self.style_prompt or "").strip() or None
        self.custom_style_notes = (self.custom_style_notes or "").strip() or None

        if self.style and not is_known_template(self.style):
            # style might be a category name — fall back to cinematic
            self.style = "cinematic"
        if self.niche_preset and not preset_exists(self.niche_preset):
            raise ValueError(f"Unknown niche_preset '{self.niche_preset}'")
        if self.visual_style and not is_valid_visual_style(self.visual_style):
            raise ValueError(f"Unknown visual_style '{self.visual_style}'")
        if self.story_tone and not is_valid_story_tone(self.story_tone):
            raise ValueError(f"Unknown story_tone '{self.story_tone}'")
        if self.category and not is_valid_category(self.category):
            raise ValueError(f"Unknown category '{self.category}'")
        if self.stop_after and self.stop_after not in _VALID_STEPS:
            raise ValueError(f"stop_after must be one of {_VALID_STEPS}, got '{self.stop_after}'")
        if self.resume_from and self.resume_from not in _VALID_STEPS:
            raise ValueError(f"resume_from must be one of {_VALID_STEPS}, got '{self.resume_from}'")
        if self.resume_from and not self.resume_project_id:
            raise ValueError("resume_project_id is required when resume_from is set")
        return self
    # Image model override for storyboard (empty = auto from style config)
    image_model: Optional[str] = None
    # Storyboard provider: "gemini" (Chrome extension) or "webhook" (WaveSpeed via n8n)
    storyboard_provider: str = "webhook"
    # Prompt prefix prepended to each image prompt (e.g. "generate an image ")
    prompt_prefix: str = ""
    # Asset grabber provider (grok videos)
    provider: str = "grok"
    aspect_ratio: str = "9:16"
    auto_type: bool = True
    grok_mode: str = "video"
    grok_quality: str = "480p"
    grok_duration: str = "6s"

    model_config = {"extra": "allow"}
