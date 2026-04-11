"""Inworld TTS Provider — Phase 4.

Cloud TTS via Inworld Voice API.
"""

import base64
import io
import os
import soundfile as sf
import time
import threading
from datetime import datetime
from typing import Optional, Callable

from loguru import logger

from config import INWORLD_API_KEY, INWORLD_TTS_BASE_URL, INWORLD_TTS_MODEL, TTS_DIR
from studio.io_utils import safe_json_write
from studio.tts.providers.base import TTSProvider, TTSResult, Voice


_voices_cache = None
_voices_cache_lock = threading.Lock()
_voices_cache_ts = 0
_VOICES_TTL = 600


def _auth_header(api_key: str) -> dict:
    return {"Authorization": f"Basic {api_key}"}


class InworldTTSProvider(TTSProvider):
    """Inworld TTS provider implementation."""

    def synthesize(
        self,
        text: str,
        settings: dict,
        voice: Optional[str] = None,
        speed: float = 1.0,
        on_progress: Optional[Callable] = None,
    ) -> TTSResult:
        api_key = settings.get("api_key") or INWORLD_API_KEY
        voice = voice or settings.get("voice", "Ashley")
        model_id = settings.get("model", INWORLD_TTS_MODEL)

        if not api_key:
            raise ValueError("Inworld API key not configured")

        if on_progress:
            on_progress("Synthesizing via Inworld API...")

        is_bella = "bella" in voice.lower()
        temperature = 1.11 if is_bella else 1.1
        speaking_rate = 1.0 if is_bella else 1.15

        payload = {
            "text": text,
            "voiceId": voice,
            "modelId": model_id,
            "audioConfig": {
                "speakingRate": speaking_rate,
            },
            "temperature": temperature,
        }

        url = f"{INWORLD_TTS_BASE_URL}/voice"
        headers = {**_auth_header(api_key), "Content-Type": "application/json"}

        start = time.perf_counter()
        import requests
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
                    f"Inworld TTS 404 — voice '{voice}' may not exist. "
                    f"Response: {resp.text[:200]}"
                )
            if resp.status_code in (429, 502, 503, 504):
                delay = 2 * (2 ** (attempt - 1))
                logger.warning("Inworld TTS {} (attempt {}/3), retrying in {}s", resp.status_code, attempt, delay)
                time.sleep(delay)
                continue
            resp.raise_for_status()
        else:
            raise last_exc

        elapsed = time.perf_counter() - start
        data = resp.json()
        audio_b64 = data.get("audioContent", "")
        audio_bytes = base64.b64decode(audio_b64)

        usage = data.get("usage", {})
        characters = usage.get("processedCharactersCount", len(text))

        os.makedirs(TTS_DIR, exist_ok=True)
        basename = f"inworld_{int(time.time() * 1000)}"
        job_dir = os.path.join(TTS_DIR, basename)
        os.makedirs(job_dir, exist_ok=True)
        wav_path = os.path.join(job_dir, basename + ".wav")

        audio, sr = sf.read(io.BytesIO(audio_bytes))
        sf.write(wav_path, audio, sr)

        info = sf.info(wav_path)
        duration = round(info.duration, 2)

        metadata = {
            "filename": basename + ".wav",
            "folder": basename,
            "prompt": text,
            "model": model_id,
            "model_id": "inworld",
            "voice": voice,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "inference_time": round(elapsed, 3),
            "duration_seconds": duration,
            "sample_rate": info.samplerate,
            "characters_billed": characters,
        }

        safe_json_write(os.path.join(job_dir, basename + ".json"), metadata, indent=2)

        return TTSResult(
            audio_path=wav_path,
            duration_seconds=duration,
            format="wav",
            sample_rate=info.samplerate,
            metadata=metadata,
        )

    def list_voices(self, settings: dict) -> list[Voice]:
        global _voices_cache, _voices_cache_ts

        api_key = settings.get("api_key") or INWORLD_API_KEY
        if not api_key:
            return []

        with _voices_cache_lock:
            if _voices_cache is not None and (time.time() - _voices_cache_ts) < _VOICES_TTL:
                return [
                    Voice(id=v.get("voiceId", ""), name=v.get("displayName", ""), language="")
                    for v in _voices_cache
                ]

        import requests
        try:
            resp = requests.get(
                f"{INWORLD_TTS_BASE_URL}/voices",
                headers={**_auth_header(api_key), "Content-Type": "application/json"},
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

        return [
            Voice(id=v.get("voiceId", ""), name=v.get("displayName", ""), language="")
            for v in voices
        ]

    def shutdown(self) -> None:
        pass


def validate_settings(settings: dict) -> list[dict]:
    issues = []
    api_key = settings.get("api_key") or INWORLD_API_KEY
    if not api_key:
        issues.append({
            "field": "api_key",
            "severity": "error",
            "message": "Inworld API key is required",
        })
    return issues


def health_check(settings: dict) -> dict:
    api_key = settings.get("api_key") or INWORLD_API_KEY
    if not api_key:
        return {"status": "warn", "message": "API key not configured"}

    import requests
    start = time.perf_counter()
    try:
        resp = requests.get(
            f"{INWORLD_TTS_BASE_URL}/voices",
            headers={**_auth_header(api_key), "Content-Type": "application/json"},
            timeout=10,
        )
        latency = (time.perf_counter() - start) * 1000
        if resp.status_code == 200:
            return {"status": "ok", "latency_ms": round(latency, 2), "message": "Connected"}
        return {"status": "fail", "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "fail", "message": str(e)}
