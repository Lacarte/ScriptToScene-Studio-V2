"""Pydantic schemas for Pipeline routes."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

_VALID_STEPS = ("tts", "timing", "alignment", "segment", "scenes", "assets", "assemble", "export")


class PipelineRunRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    voice: str = "af_heart"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    style: str = "cinematic"
    segment_config: Optional[dict] = None
    webhook_url: Optional[str] = None
    style_prompt: Optional[str] = None
    custom_style_notes: Optional[str] = None
    auto_scenes: bool = True
    stop_after: Optional[str] = None
    resume_from: Optional[str] = None
    resume_project_id: Optional[str] = None

    @model_validator(mode="after")
    def _validate_steps(self):
        if self.stop_after and self.stop_after not in _VALID_STEPS:
            raise ValueError(f"stop_after must be one of {_VALID_STEPS}, got '{self.stop_after}'")
        if self.resume_from and self.resume_from not in _VALID_STEPS:
            raise ValueError(f"resume_from must be one of {_VALID_STEPS}, got '{self.resume_from}'")
        if self.resume_from and not self.resume_project_id:
            raise ValueError("resume_project_id is required when resume_from is set")
        return self
    # Asset grabber options (used when pipeline reaches assets step)
    provider: str = "grok"
    aspect_ratio: str = "9:16"
    auto_type: bool = True
    grok_mode: str = "video"
    grok_quality: str = "480p"
    grok_duration: str = "6s"

    model_config = {"extra": "allow"}
