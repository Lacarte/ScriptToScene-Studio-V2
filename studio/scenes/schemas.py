"""Pydantic schemas for Scenes routes."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class SegmentItem(BaseModel):
    index: int
    words: Any  # list of strings or string

    model_config = {"extra": "allow"}


class SceneGenerateRequest(BaseModel):
    segments: list[SegmentItem] = Field(min_length=1)
    script: str = ""
    style: str = "cinematic"
    style_prompt: Optional[str] = None
    full_segments: Optional[list] = None
    webhook_url: Optional[str] = None
    project_id: Optional[str] = None
    parent_id: Optional[str] = None
    source_folder: Optional[str] = None
    aspect_ratio: Optional[str] = None
    model_config = {"extra": "allow"}
