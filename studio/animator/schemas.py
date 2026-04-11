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
    provider_override: Optional[str] = None  # New: provider ID from registry
    provider_options: dict = Field(default_factory=dict)
    provider: str = "midjourney"  # Legacy: kept for compatibility
    
    arguments: str = Field(default="-v 7 -ar 9:16", max_length=200)
    consistency: Optional[dict] = None
    model: Optional[str] = None
    aspect_ratio: Optional[str] = None
    resolution: Optional[str] = None
    output_format: Optional[str] = None

    @property
    def provider_id(self) -> str:
        """Get provider ID (registry override or legacy)."""
        if self.provider_override:
            return self.provider_override
        # Map legacy provider names to new IDs
        legacy_map = {"midjourney": "grok_automa", "grok": "grok_automa", "kie-ai": "kie_ai"}
        return legacy_map.get(self.provider, "grok_automa")

    model_config = {"extra": "allow"}
