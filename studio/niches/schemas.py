"""Pydantic schemas for niche preset routes."""

from pydantic import BaseModel, Field, field_validator


class NichePresetSaveRequest(BaseModel):
    id: str = Field(min_length=3, max_length=80)
    label: str = Field(min_length=3, max_length=60)
    description: str = Field(default="", max_length=240)
    category: str = Field(min_length=2, max_length=40)
    niche: str = Field(min_length=2, max_length=80)
    visual_style: str = Field(min_length=2, max_length=80)
    story_tone: str = Field(min_length=2, max_length=80)
    voice: str = Field(default="af_heart", max_length=40)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    tags: list[str] = Field(default_factory=list)
    thumbnail: str = Field(default="", max_length=120)
    custom: bool = True

    @field_validator("id", "label", "category", "niche", "visual_style", "story_tone", "voice", "description", "thumbnail")
    @classmethod
    def _strip_strings(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return list(value)

    model_config = {"extra": "ignore"}
