"""Pydantic schemas for Animator grabber routes."""

from typing import Optional

from pydantic import BaseModel, Field


class ScenePrompt(BaseModel):
    prompt: str = Field(min_length=1)
    scene: int

    model_config = {"extra": "allow"}


class GrabberStartRequest(BaseModel):
    scenes: list[ScenePrompt] = Field(min_length=1)
    project_id: str = "default"
    provider: str = "midjourney"
    arguments: str = Field(default="-v 7 -ar 9:16", max_length=200)
    consistency: Optional[dict] = None
    model: Optional[str] = None
    aspect_ratio: Optional[str] = None
    resolution: Optional[str] = None
    output_format: Optional[str] = None

    model_config = {"extra": "allow"}
