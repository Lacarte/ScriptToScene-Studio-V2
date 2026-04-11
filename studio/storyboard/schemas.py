"""Pydantic schemas for Storyboard routes."""

from typing import Optional

from pydantic import BaseModel, Field


class StoryboardScene(BaseModel):
    scene: int
    prompt: str = Field(min_length=1)

    model_config = {"extra": "allow"}


class StoryboardGenerateRequest(BaseModel):
    project_id: str
    scenes: list[StoryboardScene] = Field(min_length=1)
    aspect_ratio: str = "9:16"
    webhook_url: Optional[str] = None
    provider_override: Optional[str] = None  # Provider ID from registry (e.g., "gemini_ws", "wavespeed_webhook", "wavespeed_direct")
    provider_options: dict = Field(default_factory=dict)  # Optional per-run settings
    style: Optional[str] = None
    image_model: Optional[str] = None
    auto_type: bool = True

    @property
    def provider(self) -> str:
        """Legacy accessor for backward compatibility."""
        return self.provider_override or "webhook"

    model_config = {"extra": "allow"}


class StoryboardGrabOneRequest(BaseModel):
    project_id: str
    scene: int
    prompt: str = Field(min_length=1)
    aspect_ratio: str = "9:16"
    webhook_url: Optional[str] = None
    provider: str = "webhook"
    auto_type: bool = True

    model_config = {"extra": "allow"}
