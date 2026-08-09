"""Kokoro TTS provider manifest — Provider Contract v2 (step 15.1)."""

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
            "voice_blend": True,
            "speed_control": True,
            # One ONNX session and one G2P engine serve the whole process, so
            # invocations must not overlap. Declaring it is what makes the
            # platform serialize them — no caller holds a lock by hand (B5 / K1).
            "exclusive_execution": True,
        },
        contract_version=2,
        description="Offline text-to-speech running in-process from a local model.",
    )
