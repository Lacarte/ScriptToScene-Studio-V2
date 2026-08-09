"""WaveSpeed storyboard generation mechanics — step 14.2.

The per-scene loop the two WaveSpeed providers share. It used to live in
`storyboard/routes.py` as `_generate_storyboard`, where it also *chose* the
transport: `use_direct = image_model or (style and not is_default_model(style))`.
That heuristic is why selecting `wavespeed_direct` with no model override
silently ran the n8n webhook instead — the provider selection never reached the
loop at all. The transport is now an explicit argument supplied by the provider
that owns it, and the heuristic survives only for legacy callers that pass
neither.

Failures are recorded through the sanitized message the provider maps them to,
never `str(exc)`: `storyboard.json` is handed to the `images` port verbatim, so
a raw exception here becomes browser-visible provider response text (§36 L2).
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import requests as http_requests
from loguru import logger

from config import N8N_STORYBOARD_WEBHOOK_URL, WAVESPEED_API_KEY
from studio.shared.providers_common.errors import (
    PROVIDER_AUTH_FAILED,
    PROVIDER_RESPONSE_MALFORMED,
    PROVIDER_TIMEOUT,
    PROVIDER_TRANSPORT_FAILED,
    ProviderError,
)
from studio.shared.providers_common.validation import sanitize_message
from studio.storyboard import jobs
from studio.webhooks import call_webhook

MAX_DL_RETRIES = 3
DL_RETRY_DELAY = 2  # seconds
WEBHOOK_TIMEOUT_S = 300

_DL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}

# Substrings that mark a WaveSpeed/n8n rejection as a credential problem rather
# than a transient one, so an invalid key becomes an isolated, non-retryable
# unit failure instead of three download retries and a generic error.
_AUTH_MARKERS = ("401", "403", "unauthorized", "forbidden", "invalid api key")


def download_image(url: str, destination: str) -> bool:
    """Download an image URL to a local file with retries."""
    parsed = urlparse(url)
    headers = {**_DL_HEADERS, "Referer": f"{parsed.scheme}://{parsed.netloc}/"}

    for attempt in range(1, MAX_DL_RETRIES + 1):
        try:
            response = http_requests.get(url, headers=headers, timeout=120, stream=True)
            response.raise_for_status()
            with open(destination, "wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    handle.write(chunk)
            logger.info(
                "[storyboard] downloaded {:.0f} KB → {}",
                os.path.getsize(destination) / 1024, destination,
            )
            return True
        except (OSError, http_requests.RequestException) as exc:
            logger.warning(
                "[storyboard] download attempt {}/{} failed for {}: {}",
                attempt, MAX_DL_RETRIES, destination, exc,
            )
            if os.path.isfile(destination):
                os.remove(destination)
            if attempt < MAX_DL_RETRIES:
                time.sleep(DL_RETRY_DELAY * attempt)
    return False


def classify(exc: BaseException) -> ProviderError:
    """Map a transport failure onto the shared error catalog.

    The original text never reaches the message: `wrap_exception`'s rule (§34.4)
    applies here too, because this message is persisted into `storyboard.json`.
    """
    if isinstance(exc, http_requests.Timeout):
        return ProviderError(PROVIDER_TIMEOUT, "The image request timed out", retryable=True)
    if isinstance(exc, http_requests.ConnectionError):
        return ProviderError(
            PROVIDER_TRANSPORT_FAILED, "Could not reach the image service", retryable=True
        )
    text = str(exc).lower()
    if any(marker in text for marker in _AUTH_MARKERS):
        return ProviderError(
            PROVIDER_AUTH_FAILED, "The image service rejected the credentials"
        )
    if isinstance(exc, ValueError):
        return ProviderError(
            PROVIDER_RESPONSE_MALFORMED, "The image service returned an unusable response"
        )
    return ProviderError(
        PROVIDER_TRANSPORT_FAILED, "The image service failed", retryable=True
    )


def webhook_transport(
    webhook_url: str | None = None, *, api_key: str | None = None
) -> Callable[[Mapping[str, Any], str, str], str]:
    """The n8n webhook transport: one POST per scene, returns the image URL."""
    url = webhook_url or N8N_STORYBOARD_WEBHOOK_URL
    key = api_key or WAVESPEED_API_KEY

    def generate(scene: Mapping[str, Any], aspect_ratio: str, project_id: str) -> str:
        result = call_webhook(
            url,
            {
                "image_prompt": scene["prompt"],
                "aspect_ratio": aspect_ratio,
                "wavespeed_api_key": key,
                "project_id": project_id,
                "scene": scene["scene"],
            },
            timeout=WEBHOOK_TIMEOUT_S,
            label=f"Storyboard scene {scene['scene']}",
        )
        image_url = (result or {}).get("image_url")
        if not image_url:
            raise ValueError("webhook returned no image_url")
        return image_url

    return generate


def direct_transport(
    *, style: str = "", image_model: str = ""
) -> Callable[[Mapping[str, Any], str, str], str]:
    """The direct WaveSpeed API transport, model chosen by style or override."""

    def generate(scene: Mapping[str, Any], aspect_ratio: str, _project_id: str) -> str:
        # Resolved per call, not per transport: the model catalog is read from
        # disk, and binding here would freeze it for the life of the process.
        from studio.storyboard.wavespeed import generate_image

        return generate_image(
            prompt=scene["prompt"],
            style=style or "default",
            aspect_ratio=aspect_ratio,
            model_override=image_model or None,
        )

    return generate


def run_batch(
    project_id: str,
    request,
    transport: Callable[[Mapping[str, Any], str, str], str],
    *,
    remove_watermark: bool = False,
    is_cancelled: Callable[[], bool] | None = None,
) -> None:
    """Generate every requested scene, recording each unit as it settles.

    Runs to completion in the caller's thread; the media-job service polls the
    manifest this writes. A per-scene failure is isolated: the loop records it
    and continues, so one rejected prompt cannot lose the rest of the batch.
    """
    aspect_ratio = request.aspect_ratio
    for scene in request.legacy_scenes():
        if is_cancelled is not None and is_cancelled():
            logger.info("[storyboard] {} cancelled before scene {}", project_id, scene["scene"])
            return
        index = scene["scene"]
        jobs.mark_scene(project_id, index, "generating", image_url=None, local_path=None)
        try:
            image_url = transport(scene, aspect_ratio, project_id)
        except Exception as exc:
            error = classify(exc)
            logger.error("[storyboard] {} scene {} failed: {}", project_id, index, exc)
            jobs.record_error(project_id, index, error.message)
            continue

        jobs.mark_scene(project_id, index, "downloading", image_url=image_url)
        destination = jobs.prepare_scene_file(
            project_id, index, jobs.extension_for(image_url)
        )
        if download_image(image_url, destination):
            jobs.record_ready(
                project_id, index, destination,
                image_url=image_url, remove_watermark=remove_watermark,
            )
            logger.success("[storyboard] {} scene {} ready", project_id, index)
        else:
            jobs.record_error(
                project_id, index,
                sanitize_message("The generated image could not be downloaded"),
                image_url=image_url,
            )


__all__ = [
    "MAX_DL_RETRIES",
    "classify",
    "direct_transport",
    "download_image",
    "run_batch",
    "webhook_transport",
]
