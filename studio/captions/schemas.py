"""Pydantic schemas for Captions routes."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class AlignmentWord(BaseModel):
    word: str
    begin: float = Field(ge=0.0)
    end: float = Field(ge=0.0)

    model_config = {"extra": "allow"}


class CaptionGenerateRequest(BaseModel):
    alignment: list[AlignmentWord] = Field(min_length=1)
    words_per_group: int = Field(default=3, ge=2, le=5)
    preset: str = ""
    project_id: Optional[str] = None
    source_folder: Optional[str] = None
    blueprint_caption: Optional[dict] = None

    model_config = {"extra": "allow"}


class CaptionSaveRequest(BaseModel):
    project_id: str = Field(min_length=1)
    captions: list = Field(min_length=1)
    style: Optional[dict] = None

    model_config = {"extra": "allow"}
