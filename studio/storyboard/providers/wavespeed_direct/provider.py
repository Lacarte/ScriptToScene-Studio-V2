"""WaveSpeed Direct Storyboard Provider — Phase 6.

Uses direct WaveSpeed API for image generation.
"""

import os
import time
from loguru import logger

from config import WAVESPEED_API_KEY
from studio.shared.providers_common.jobs import status_from_scenes, unknown_job_status
from studio.storyboard.providers.base import (
    StoryboardProvider,
    JobHandle,
    JobStatus,
    SceneResult,
)
from studio.storyboard import wavespeed


class WaveSpeedDirectProvider(StoryboardProvider):
    """Storyboard provider using direct WaveSpeed API."""

    def submit(
        self,
        project_id: str,
        scenes: list[dict],
        settings: dict,
        on_progress=None,
    ) -> JobHandle:
        from studio.storyboard import routes as sb_routes
        from studio.storyboard.schemas import StoryboardGenerateRequest
        
        api_key = settings.get("api_key") or WAVESPEED_API_KEY
        image_model = settings.get("image_model") or ""
        aspect_ratio = "16:9"
        
        if on_progress:
            on_progress({"status": "starting", "message": "Starting storyboard generation"})
        
        sb_routes._generate_storyboard(
            project_id=project_id,
            scenes=scenes,
            aspect_ratio=aspect_ratio,
            webhook_url=None,
            image_model=image_model,
        )
        
        return JobHandle(
            job_id=project_id,
            domain="storyboard",
            provider_id="wavespeed_direct",
            project_id=project_id,
        )

    def poll(self, job_id: str, settings: dict) -> JobStatus:
        from studio.storyboard import routes as sb_routes

        job = sb_routes._jobs.get(job_id)
        if not job:
            return unknown_job_status(job_id)
        # This body counted `status == "complete"`, a value the storyboard route
        # has never written — it writes ready/error (`routes.py:390`). Found by
        # first-time test in step 11.4.
        return status_from_scenes(job_id, job.get("scene_statuses", {}))

    def shutdown(self) -> None:
        pass


def validate_settings(settings: dict) -> list[dict]:
    issues = []
    api_key = settings.get("api_key", "").strip() or WAVESPEED_API_KEY
    if not api_key:
        issues.append({
            "field": "api_key",
            "severity": "warning",
            "message": "No API key configured — will use environment variable",
        })
    return issues


def health_check(settings: dict) -> dict:
    api_key = settings.get("api_key", "").strip() or WAVESPEED_API_KEY
    if not api_key:
        return {"status": "warn", "message": "No API key (will use env var)"}
    
    return {"status": "ok", "message": "WaveSpeed API configured"}


_provider_instance = None


def get_provider():
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = WaveSpeedDirectProvider()
    return _provider_instance