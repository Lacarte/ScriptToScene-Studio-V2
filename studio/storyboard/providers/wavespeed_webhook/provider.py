"""WaveSpeed Webhook Storyboard Provider — Phase 6.

Uses n8n webhook for image generation.
"""

import os
import time
from loguru import logger

from config import N8N_STORYBOARD_WEBHOOK_URL, WAVESPEED_API_KEY
from studio.shared.providers_common.jobs import status_from_scenes, unknown_job_status
from studio.storyboard.providers.base import (
    StoryboardProvider,
    JobHandle,
    JobStatus,
    SceneResult,
)
from studio.storyboard import wavespeed


class WaveSpeedWebhookProvider(StoryboardProvider):
    """Storyboard provider using n8n webhook."""

    def submit(
        self,
        project_id: str,
        scenes: list[dict],
        settings: dict,
        on_progress=None,
    ) -> JobHandle:
        from studio.storyboard import routes as sb_routes
        from studio.storyboard.schemas import StoryboardGenerateRequest
        
        webhook_url = settings.get("webhook_url") or N8N_STORYBOARD_WEBHOOK_URL
        image_model = settings.get("image_model") or ""
        aspect_ratio = "16:9"
        
        if on_progress:
            on_progress({"status": "starting", "message": "Starting storyboard generation"})
        
        sb_routes.generate(StoryboardGenerateRequest(
            project_id=project_id,
            scenes=scenes,
            aspect_ratio=aspect_ratio,
            webhook_url=webhook_url,
            image_model=image_model,
        ))
        
        return JobHandle(
            job_id=project_id,
            domain="storyboard",
            provider_id="wavespeed_webhook",
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
    webhook_url = settings.get("webhook_url", "").strip()
    if not webhook_url:
        issues.append({
            "field": "webhook_url",
            "severity": "error",
            "message": "Webhook URL is required",
        })
    return issues


def health_check(settings: dict) -> dict:
    import requests
    webhook_url = settings.get("webhook_url") or N8N_STORYBOARD_WEBHOOK_URL
    if not webhook_url:
        return {"status": "fail", "message": "No webhook URL configured"}
    
    try:
        start = time.perf_counter()
        resp = requests.get(webhook_url, timeout=5)
        elapsed = int((time.perf_counter() - start) * 1000)
        
        if resp.status_code in (200, 405):
            return {"status": "ok", "latency_ms": elapsed, "message": "Webhook reachable"}
        return {"status": "warn", "message": f"Webhook returned {resp.status_code}"}
    except Exception as e:
        return {"status": "fail", "message": str(e)}


_provider_instance = None


def get_provider():
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = WaveSpeedWebhookProvider()
    return _provider_instance