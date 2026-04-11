"""WaveSpeed Webhook Storyboard Provider — Phase 6.

Uses n8n webhook for image generation.
"""

import os
import time
from loguru import logger

from config import N8N_STORYBOARD_WEBHOOK_URL, WAVESPEED_API_KEY
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
            status="pending",
        )

    def poll(self, job_id: str, settings: dict) -> JobStatus:
        from studio.storyboard import routes as sb_routes
        
        job = sb_routes._jobs.get(job_id)
        if not job:
            return JobStatus(job_id=job_id, status="unknown")
        
        statuses = job.get("scene_statuses", {})
        done = sum(1 for s in statuses.values() if s.get("status") == "complete")
        total = len(statuses)
        progress = done / total if total > 0 else 0.0
        
        return JobStatus(
            job_id=job_id,
            status="complete" if done == total else "processing",
            progress=progress,
        )

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