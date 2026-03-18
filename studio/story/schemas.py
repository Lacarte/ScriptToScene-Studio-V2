"""Pydantic schemas for Story generation routes."""

from typing import Optional

from pydantic import BaseModel, Field


class StoryGenerateRequest(BaseModel):
    project_name_id: Optional[str] = None
    preset_style: str = "cinematic"
    story_category: str = "motivation"
    duration: int = Field(default=45, ge=15, le=180)
    language: str = "english"
    webhook_url: Optional[str] = None

    model_config = {"extra": "allow"}


class StorySection(BaseModel):
    hook: str = ""
    build: str = ""
    climax: str = ""
    cta: str = ""
