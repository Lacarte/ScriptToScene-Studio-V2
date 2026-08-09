"""Kie AI Animator Provider — Phase 7.

Uses direct Kie AI API for image generation.
API flow:
  1. POST /jobs/createTask  -> returns taskId
  2. GET  /jobs/recordInfo?taskId=...  -> poll until resultJson populated
  3. Download image from resultJson.resultUrls[0]
"""

import time
import os
import threading

import requests as http_requests
from loguru import logger

from config import KIE_AI_API_KEY, KIE_AI_BASE_URL, KIE_AI_MODEL
from studio.animator.providers.base import (
    AnimatorProvider,
    JobHandle,
    JobStatus,
    SceneResult,
)
from studio.shared.providers_common.jobs import status_from_scenes, unknown_job_status
from studio.shared.providers_common.validation import sanitize_message


POLL_INTERVAL = 3
POLL_TIMEOUT = 180


def _create_task(prompt, aspect_ratio, resolution, output_format, model, api_key):
    """POST /jobs/createTask -> returns taskId."""
    url = f"{KIE_AI_BASE_URL}/jobs/createTask"

    if model == "google/nano-banana":
        fmt = "jpeg" if output_format in ("jpg", "jpeg") else output_format
        input_params = {
            "prompt": prompt,
            "image_size": aspect_ratio,
            "output_format": fmt,
        }
    else:
        res_map = {"1": "1K", "2": "2K"}
        input_params = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": res_map.get(resolution, resolution),
            "output_format": output_format,
        }

    payload = {"model": model, "input": input_params}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = http_requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    task_id = data.get("taskId") or (data.get("data") or {}).get("taskId")
    if not task_id:
        raise RuntimeError(f"Kie AI createTask returned no taskId: {data}")
    return task_id


def _poll_result(task_id, api_key):
    """GET /jobs/recordInfo?taskId=... -> poll until result ready."""
    url = f"{KIE_AI_BASE_URL}/jobs/recordInfo"
    headers = {"Authorization": f"Bearer {api_key}"}

    start = time.time()
    while time.time() - start < POLL_TIMEOUT:
        resp = http_requests.get(
            url, params={"taskId": task_id}, headers=headers, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        record = data if "status" in data else data.get("data", {})
        status = record.get("status", "")

        if status in ("failed", "error"):
            raise RuntimeError(f"Kie AI task {task_id} failed: {record}")

        result_json = record.get("resultJson")
        if result_json:
            if isinstance(result_json, str):
                import json
                result_json = json.loads(result_json)
            result_urls = result_json.get("resultUrls", [])
            if result_urls:
                logger.success("Kie AI task {} complete: {} image(s)", task_id, len(result_urls))
                return {"url": result_urls[0], "task_id": task_id, "all_urls": result_urls}

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Kie AI task {task_id} timed out after {POLL_TIMEOUT}s")


def generate_image(prompt, aspect_ratio="9:16", resolution="1", output_format="jpg", model=None, api_key=None):
    """Generate an image via Kie AI API. Returns {"url": ..., "task_id": ...}."""
    key = api_key or KIE_AI_API_KEY
    if not key:
        raise ValueError("KIE_AI_API_KEY not configured")
    task_id = _create_task(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        output_format=output_format,
        model=model or KIE_AI_MODEL,
        api_key=key,
    )
    logger.info("Kie AI task created: {}", task_id)
    return _poll_result(task_id, api_key=key)


class KieAIProvider(AnimatorProvider):
    """Animator provider using direct Kie AI API."""

    def submit(
        self,
        project_id: str,
        scenes: list[dict],
        settings: dict,
        on_progress=None,
    ) -> JobHandle:
        from studio.animator import routes as animator_routes
        
        api_key = settings.get("api_key") or KIE_AI_API_KEY
        model = settings.get("model") or KIE_AI_MODEL
        resolution = settings.get("resolution", "1")
        
        if not api_key:
            raise ValueError("KIE_AI_API_KEY not configured")
        
        job_id = f"{project_id}"

        # Set up job tracking. This wrote to `animator_routes._asset_jobs`,
        # an attribute the module has never defined; the real store is the
        # `_jobs` dict guarded by `_jobs_lock` (`routes.py:38-39`, `:676`).
        # Found by first-time test in step 11.4.
        with animator_routes._jobs_lock:
            animator_routes._jobs[job_id] = {
                "project_id": project_id,
                "status": "running",
                "scenes": {},
            }


        # Start background generation
        t = threading.Thread(
            target=self._generate_images,
            args=(project_id, scenes, api_key, model, resolution),
            daemon=True,
        )
        t.start()
        
        return JobHandle(
            job_id=job_id,
            domain="animator",
            provider_id="kie_ai",
            project_id=project_id,
        )

    def _generate_images(self, project_id, scenes, api_key, model, resolution):
        from studio.animator import routes as animator_routes

        with animator_routes._jobs_lock:
            job = animator_routes._jobs.get(project_id)
        if not job:
            return

        for scene in scenes:
            scene_key = str(scene.get("scene", scene.get("index", 0)))
            with animator_routes._jobs_lock:
                job["scenes"][scene_key] = {
                    "status": "generating", "urls": [], "local_files": []
                }

            try:
                result = generate_image(
                    prompt=scene.get("prompt", ""),
                    resolution=resolution,
                    model=model,
                    api_key=api_key,
                )
                entry = {
                    # `ready` is the vocabulary the animator route persists;
                    # `complete` was written here and read nowhere.
                    "status": "ready",
                    "urls": [result.get("url", "")],
                    "local_files": [],
                }
            except Exception as e:
                logger.error("[{}] Kie AI failed: {}", project_id, e)
                entry = {"status": "error", "error": sanitize_message(e)}

            with animator_routes._jobs_lock:
                job["scenes"][scene_key] = entry

    def poll(self, job_id: str, settings: dict) -> JobStatus:
        from studio.animator import routes as animator_routes

        with animator_routes._jobs_lock:
            job = animator_routes._jobs.get(job_id)
        if not job:
            return unknown_job_status(job_id)
        return status_from_scenes(job_id, job.get("scenes", {}))

    def shutdown(self) -> None:
        pass


def validate_settings(settings: dict) -> list[dict]:
    issues = []
    api_key = settings.get("api_key", "").strip() or KIE_AI_API_KEY
    if not api_key:
        issues.append({
            "field": "api_key",
            "severity": "warning",
            "message": "No API key — will use environment variable",
        })
    return issues


def health_check(settings: dict) -> dict:
    api_key = settings.get("api_key", "").strip() or KIE_AI_API_KEY
    if not api_key:
        return {"status": "warn", "message": "No API key configured"}
    
    import requests as http_requests
    url = f"{KIE_AI_BASE_URL}/jobs/recordInfo?taskId=test"
    try:
        start = time.perf_counter()
        resp = http_requests.get(url, timeout=5)
        elapsed = int((time.perf_counter() - start) * 1000)
        
        if resp.status_code == 404:
            return {"status": "ok", "latency_ms": elapsed, "message": "Kie AI API reachable"}
        return {"status": "warn", "message": f"Unexpected status {resp.status_code}"}
    except Exception as e:
        return {"status": "fail", "message": str(e)}


_provider_instance = None


def get_provider():
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = KieAIProvider()
    return _provider_instance