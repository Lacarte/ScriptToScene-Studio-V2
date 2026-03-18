"""Pydantic schemas for Story generation routes."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

SUPPORTED_LANGUAGES = ("english", "french", "spanish")


class StoryGenerateRequest(BaseModel):
    project_name_id: Optional[str] = None
    preset_style: str = "cinematic"
    story_category: str = "motivation"
    duration: int = Field(default=45, ge=15, le=180)
    language: Literal["english", "french", "spanish"] = "english"
    webhook_url: Optional[str] = None

    model_config = {"extra": "allow"}
