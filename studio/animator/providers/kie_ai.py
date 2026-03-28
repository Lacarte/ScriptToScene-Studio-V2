"""Kie AI Image Generation Provider.

API flow:
  1. POST /jobs/createTask  → returns taskId
  2. GET  /jobs/recordInfo?taskId=...  → poll until resultJson populated
  3. Download image from resultJson.resultUrls[0]
"""

import time

import requests as http_requests
from loguru import logger

from config import KIE_AI_API_KEY, KIE_AI_BASE_URL, KIE_AI_MODEL

POLL_INTERVAL = 3  # seconds between status checks
POLL_TIMEOUT = 180  # max wait time per image


def generate_image(
    prompt,
    aspect_ratio="9:16",
    resolution="1",
    output_format="jpg",
    model=None,
    api_key=None,
):
    """Generate an image via Kie AI API.

    Returns dict: {"url": "https://...", "task_id": "..."}
    Raises on timeout or API error.
    """
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
    result = _poll_result(task_id, api_key=key)
    return result


def _create_task(prompt, aspect_ratio, resolution, output_format, model, api_key):
    """POST /jobs/createTask → returns taskId."""
    url = f"{KIE_AI_BASE_URL}/jobs/createTask"

    if model == "google/nano-banana":
        # Original nano-banana uses different param names
        fmt = "jpeg" if output_format in ("jpg", "jpeg") else output_format
        input_params = {
            "prompt": prompt,
            "image_size": aspect_ratio,
            "output_format": fmt,
        }
    else:
        # nano-banana-2, nano-banana-pro
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
    """GET /jobs/recordInfo?taskId=... → poll until result ready."""
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
            # resultJson may be a string or already parsed
            if isinstance(result_json, str):
                import json
                result_json = json.loads(result_json)

            result_urls = result_json.get("resultUrls", [])
            if result_urls:
                logger.success("Kie AI task {} complete: {} image(s)", task_id, len(result_urls))
                return {"url": result_urls[0], "task_id": task_id, "all_urls": result_urls}

        elapsed = int(time.time() - start)
        logger.debug("Kie AI task {} polling... ({}s, status={})", task_id, elapsed, status)
        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Kie AI task {task_id} timed out after {POLL_TIMEOUT}s")
