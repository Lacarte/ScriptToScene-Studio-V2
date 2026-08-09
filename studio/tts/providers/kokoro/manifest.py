"""Kokoro TTS Provider Manifest — Phase 4."""

from studio.shared.providers_common import ProviderManifest


def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="kokoro",
        label="Kokoro",
        domain="tts",
        kind="local",
        version="1.0.0",
        requires=[],
        capabilities={
            "test_connection": True,
            "streaming": False,
            "model_download": True,
            "single_scene": True,
            "batch": True,
            "voice_list": True,
        },
        description="Offline text-to-speech running in-process from a local model.",
    )
