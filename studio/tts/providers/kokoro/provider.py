"""Kokoro TTS Provider — Phase 4.

Local Kokoro ONNX TTS synthesis with voice blending support.
"""

import gc
import os
import re
import soundfile as sf
import time
import threading
from datetime import datetime
from typing import Optional, Callable, Any

import numpy as np
from loguru import logger

from config import MODELS_DIR, TTS_DIR
from studio.io_utils import safe_json_write
from studio.tts.providers.base import TTSProvider, TTSResult, Voice


kokoro_instance = None
kokoro_lock = threading.Lock()

VOICE_LANG_MAP = {
    "af": "en-us", "am": "en-us",
    "bf": "en-gb", "bm": "en-gb",
    "jf": "ja",    "jm": "ja",
    "zf": "cmn",   "zm": "cmn",
    "ef": "es",    "em": "es",
    "ff": "fr-fr",
    "hf": "hi",    "hm": "hi",
    "if": "it",    "im": "it",
    "pf": "pt-br", "pm": "pt-br",
}

VOICES = [
    "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica",
    "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
    "am_michael", "am_onyx", "am_puck",
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxuan", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
    "ef_dora", "em_alex", "em_santa",
    "ff_siwis",
    "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
    "if_sara", "im_nicola",
    "pf_dora", "pm_alex", "pm_santa",
]


MODELS = {
    "kokoro": {
        "name": "Kokoro v1.0",
        "size": "~373MB",
        "onnx_file": "kokoro-v1.0.onnx",
        "voices_file": "voices-v1.0.bin",
        "onnx_url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
        "voices_url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
    },
}


generation_inference_lock = threading.Lock()


def _voice_to_lang(voice_name: str) -> str:
    prefix = voice_name.split("_")[0] if "_" in voice_name else voice_name[:2]
    return VOICE_LANG_MAP.get(prefix, "en-us")


def _slerp(v0: np.ndarray, v1: np.ndarray, t: float) -> np.ndarray:
    v0 = v0.astype(np.float64)
    v1 = v1.astype(np.float64)
    if v0.ndim == 1:
        n0, n1 = np.linalg.norm(v0), np.linalg.norm(v1)
        dot = np.clip(np.dot(v0, v1) / (n0 * n1 + 1e-10), -1.0, 1.0)
        omega = np.arccos(dot)
        if abs(omega) < 1e-6:
            return ((1.0 - t) * v0 + t * v1).astype(np.float32)
        so = np.sin(omega)
        return ((np.sin((1.0 - t) * omega) / so) * v0
                + (np.sin(t * omega) / so) * v1).astype(np.float32)
    result = np.empty_like(v0)
    for i in range(v0.shape[0]):
        result[i] = _slerp(v0[i], v1[i], t)
    return result.astype(np.float32)


def _lerp(v0: np.ndarray, v1: np.ndarray, t: float) -> np.ndarray:
    return ((1.0 - t) * v0 + t * v1).astype(np.float32)


_misaki_g2p = None
_misaki_lock = threading.Lock()


def _get_misaki_g2p(british=False):
    global _misaki_g2p
    with _misaki_lock:
        if _misaki_g2p is None:
            try:
                from misaki import en
                _misaki_g2p = en.G2P(trf=False, british=british)
                logger.success("Misaki G2P loaded (british={})", british)
            except ImportError:
                logger.warning("misaki not installed — Kokoro pronunciation links will not work")
                return None
            except Exception:
                logger.exception("Failed to load misaki G2P")
                return None
        return _misaki_g2p


def _phonemize_with_misaki(text: str, lang: str = "en-us") -> tuple[str | None, bool]:
    if not lang.startswith("en"):
        return text, False

    british = lang == "en-gb"
    g2p = _get_misaki_g2p(british=british)
    if g2p is None:
        return text, False

    try:
        phonemes, _tokens = g2p(text)
        if phonemes and phonemes.strip():
            return phonemes, True
    except Exception:
        logger.exception("Misaki G2P failed, falling back to espeak")
    return text, False


def _model_files_present() -> bool:
    cfg = MODELS["kokoro"]
    onnx_path = os.path.join(MODELS_DIR, cfg["onnx_file"])
    voices_path = os.path.join(MODELS_DIR, cfg["voices_file"])
    return os.path.isfile(onnx_path) and os.path.isfile(voices_path)


def load_model():
    global kokoro_instance
    if kokoro_instance is not None:
        return kokoro_instance

    from kokoro_onnx import Kokoro

    cfg = MODELS["kokoro"]
    onnx_path = os.path.join(MODELS_DIR, cfg["onnx_file"])
    voices_path = os.path.join(MODELS_DIR, cfg["voices_file"])

    with kokoro_lock:
        if kokoro_instance is None:
            logger.info("Loading Kokoro model ...")
            kokoro_instance = Kokoro(onnx_path, voices_path)
            logger.success("Kokoro model ready")
    return kokoro_instance


def _tts_job_dir(basename):
    return os.path.join(TTS_DIR, basename)


class KokoroTTSProvider(TTSProvider):
    """Kokoro TTS provider implementation."""

    def synthesize(
        self,
        text: str,
        settings: dict,
        voice: Optional[str] = None,
        speed: float = 1.0,
        on_progress: Optional[Callable] = None,
    ) -> TTSResult:
        voice = voice or settings.get("voice", "af_bella")
        speed = float(settings.get("speed", 1.0))
        blend = settings.get("blend", False)

        kokoro = load_model()
        lang = _voice_to_lang(voice)

        blend_meta = None
        voice_param = voice

        if blend:
            voice_a = settings.get("blendA", "af_heart")
            voice_b = settings.get("blendB", "am_adam")
            blend_ratio = float(settings.get("blendRatio", 50)) / 100.0
            blend_method = settings.get("blendMethod", "slerp")
            blend_meta = {
                "voiceA": voice_a,
                "voiceB": voice_b,
                "ratio": blend_ratio,
                "method": blend_method,
            }

            embed_a = kokoro.get_voice_style(voice_a)
            embed_b = kokoro.get_voice_style(voice_b)
            if blend_method == "slerp":
                blended_embed = _slerp(embed_a, embed_b, blend_ratio)
            else:
                blended_embed = _lerp(embed_a, embed_b, blend_ratio)

            voice_param = (blended_embed, voice_a, voice_b)

        phonemes, is_ph = _phonemize_with_misaki(text, lang)

        if on_progress:
            on_progress("Synthesizing...")

        start = time.perf_counter()
        with generation_inference_lock:
            audio, _sr = kokoro.create(
                text=phonemes,
                voice=voice_param,
                speed=speed,
                lang=lang,
                is_phonemes=is_ph,
            )
        inference_time = time.perf_counter() - start

        os.makedirs(TTS_DIR, exist_ok=True)
        basename = f"kokoro_{int(time.time() * 1000)}"
        job_dir = _tts_job_dir(basename)
        os.makedirs(job_dir, exist_ok=True)
        wav_path = os.path.join(job_dir, basename + ".wav")

        from studio.tts.audio import pad_audio, run_loudnorm
        audio = pad_audio(audio, sample_rate=24000)
        sf.write(wav_path, audio, 24000)
        run_loudnorm(wav_path)
        del audio
        gc.collect()

        info = sf.info(wav_path)
        duration = info.duration
        rtf = inference_time / duration if duration > 0 else 0

        metadata = {
            "filename": basename + ".wav",
            "folder": basename,
            "prompt": text,
            "model": "kokoro-v1.0",
            "model_id": "kokoro",
            "voice": voice,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "inference_time": round(inference_time, 3),
            "rtf": round(rtf, 4),
            "duration_seconds": round(duration, 2),
            "sample_rate": 24000,
            "speed": speed,
        }
        if blend_meta:
            metadata["blend"] = blend_meta

        safe_json_write(os.path.join(job_dir, basename + ".json"), metadata, indent=2)

        return TTSResult(
            audio_path=wav_path,
            duration_seconds=duration,
            format="wav",
            sample_rate=24000,
            metadata=metadata,
        )

    def list_voices(self, settings: dict) -> list[Voice]:
        return [
            Voice(id=v, name=v, language=_voice_to_lang(v), gender=None)
            for v in VOICES
        ]

    def shutdown(self) -> None:
        global kokoro_instance
        with kokoro_lock:
            kokoro_instance = None


def validate_settings(settings: dict) -> list[dict]:
    issues = []
    voice = settings.get("voice", "af_bella")
    if voice not in VOICES:
        issues.append({
            "field": "voice",
            "severity": "warning",
            "message": f"Voice '{voice}' may not be available. Check model download.",
        })
    return issues


def create() -> KokoroTTSProvider:
    """v2 factory (contracts.md §21.1). Memoized by the registry, never at import."""
    return KokoroTTSProvider()


def health_check(settings: dict) -> dict:
    if not _model_files_present():
        return {"status": "warn", "message": "Model files not downloaded", "details": {"model_present": False}}
    try:
        kokoro = load_model()
        return {"status": "ok", "latency_ms": 0, "message": "Kokoro model loaded"}
    except Exception as e:
        return {"status": "fail", "message": str(e)}
