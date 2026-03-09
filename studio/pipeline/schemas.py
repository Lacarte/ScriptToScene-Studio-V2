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
    blueprint_path: Optional[str] = None
    style_prompt: Optional[str] = None

    model_config = {"extra": "allow"}
