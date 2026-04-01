"""Inworld TTS provider — cloud text-to-speech via Inworld Voice API.

Endpoint: POST https://api.inworld.ai/tts/v1/voice
Ref:  https://github.com/inworld-ai/inworld-api-examples/tree/main/tts/python
"""

import base64
import io
import threading
import time

import numpy as np
import requests
import soundfile as sf
from loguru import logger

from config import INWORLD_API_KEY, INWORLD_TTS_BASE_URL, INWORLD_TTS_MODEL

_voices_cache = None
_voices_cache_lock = threading.Lock()
_voices_cache_ts = 0
_VOICES_TTL = 600  # refresh every 10 minutes


def _auth_header() -> dict:
    """Return Authorization header for Inworld API."""
    return {"Authorization": f"Basic {INWORLD_API_KEY}"}


def is_available() -> bool:
    """Return True if an Inworld API key is configured."""
    return bool(INWORLD_API_KEY)


def list_voices(language: str = None) -> list[dict]:
    """Fetch available voices from Inworld API.

    Returns list of {voiceId, displayName, description, tags, languages}.
    Cached for 10 minutes.
    """
    global _voices_cache, _voices_cache_ts

    with _voices_cache_lock:
        if _voices_cache is not None and (time.time() - _voices_cache_ts) < _VOICES_TTL:
            voices = _voices_cache
            if language:
                voices = [v for v in voices if language in v.get("languages", [])]
            return voices

    params = {}
    if language:
        params["filter"] = f"language={language}"

    try:
        resp = requests.get(
            f"{INWORLD_TTS_BASE_URL}/voices",
            headers={**_auth_header(), "Content-Type": "application/json"},
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        voices = data.get("voices", [])
    except Exception as e:
        logger.error("Inworld list_voices failed: {}", e)
        return _voices_cache or []

    with _voices_cache_lock:
        _voices_cache = voices
        _voices_cache_ts = time.time()

    if language:
        voices = [v for v in voices if language in v.get("languages", [])]
    return voices


def synthesize(
    text: str,
    voice_id: str = "Dennis",
    speed: float = 1.0,
    model_id: str = None,
) -> dict:
    """Synthesize speech via Inworld REST API.

    Returns dict with keys:
      - audio_bytes: raw MP3 bytes
      - model_id: str
      - characters: int (billed characters)
      - inference_time: float
    """
    model_id = model_id or INWORLD_TTS_MODEL

    # Inworld voices sound best at natural pace — always use 1.0
    speaking_rate = 1.0

    payload = {
        "text": text,
        "voiceId": voice_id,
        "modelId": model_id,
        "audioConfig": {
            "speakingRate": speaking_rate,
        },
        "temperature": 1,
    }

    url = f"{INWORLD_TTS_BASE_URL}/voice"
    headers = {**_auth_header(), "Content-Type": "application/json"}

    start = time.perf_counter()
    last_exc = None
    for attempt in range(1, 4):
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            break
        last_exc = requests.HTTPError(
            f"{resp.status_code} for url: {url} — {resp.text[:200]}",
            response=resp,
        )
        if resp.status_code == 404:
            raise RuntimeError(
                f"Inworld TTS 404 — voice '{voice_id}' may not exist. "
                f"Check that the voice ID is a valid Inworld voice (e.g. Carter, Dennis), "
                f"not a Kokoro voice ID. Response: {resp.text[:200]}"
            )
        if resp.status_code in (429, 502, 503, 504):
            delay = 2 * (2 ** (attempt - 1))
            logger.warning("Inworld TTS {} (attempt {}/3), retrying in {}s", resp.status_code, attempt, delay)
            time.sleep(delay)
            continue
        # Non-retryable error — fail immediately
        resp.raise_for_status()
    else:
        raise last_exc
    elapsed = time.perf_counter() - start

    data = resp.json()
    audio_b64 = data.get("audioContent", "")
    audio_bytes = base64.b64decode(audio_b64)

    usage = data.get("usage", {})
    characters = usage.get("processedCharactersCount", len(text))

    return {
        "audio_bytes": audio_bytes,
        "model_id": model_id,
        "characters": characters,
        "inference_time": round(elapsed, 3),
    }


def synthesize_to_wav(
    text: str,
    wav_path: str,
    voice_id: str = "Dennis",
    speed: float = 1.0,
    model_id: str = None,
) -> dict:
    """Synthesize and write as a WAV file.

    The API returns MP3 by default. We decode it to PCM and write as WAV
    so downstream pipeline steps (alignment, segmenter) get a consistent format.
    """
    result = synthesize(
        text=text,
        voice_id=voice_id,
        speed=speed,
        model_id=model_id,
    )

    # Decode MP3 → numpy via soundfile (reads from bytes buffer)
    audio, sr = sf.read(io.BytesIO(result["audio_bytes"]))
    sf.write(wav_path, audio, sr)

    info = sf.info(wav_path)
    duration = round(info.duration, 2)

    logger.success(
        "Inworld TTS: {:.1f}s audio in {:.2f}s | voice={} model={}",
        duration,
        result["inference_time"],
        voice_id,
        result["model_id"],
    )

    return {
        "duration_seconds": duration,
        "sample_rate": info.samplerate,
        "model_id": result["model_id"],
        "characters": result["characters"],
        "inference_time": result["inference_time"],
    }
