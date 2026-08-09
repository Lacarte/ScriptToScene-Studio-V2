"""Inworld TTS Provider Manifest — Phase 4."""

from studio.shared.providers_common import ProviderManifest


def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="inworld",
        label="Inworld",
        domain="tts",
        kind="cloud",
        version="1.0.0",
        requires=["api_key"],
        capabilities={
            "test_connection": True,
            "streaming": False,
            "model_download": False,
            "single_scene": True,
            "batch": True,
            "voice_list": True,
        },
        description="Cloud text-to-speech with named voices and selectable models.",
        # Read-time fallback only — a value is never copied into settings.json.
        environment={"api_key": "INWORLD_API_KEY", "model": "INWORLD_TTS_MODEL"},
    )
