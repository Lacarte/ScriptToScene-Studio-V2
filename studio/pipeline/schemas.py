"""Pydantic schemas for Pipeline routes."""

from typing import Optional

from pydantic import BaseModel, Field


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
    stop_after: Optional[str] = None  # tts, alignment/timing, segment, scenes, assets, assemble, export, or None (all)
    resume_from: Optional[str] = None  # step to resume from (skips prior steps, reuses saved outputs)
    resume_project_id: Optional[str] = None  # existing project ID to resume
    # Asset grabber options (used when pipeline reaches assets step)
    provider: str = "grok"
    aspect_ratio: str = "9:16"
    auto_type: bool = True
    grok_mode: str = "video"
    grok_quality: str = "480p"
    grok_duration: str = "6s"

    model_config = {"extra": "allow"}
