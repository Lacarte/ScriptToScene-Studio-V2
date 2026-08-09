"""Kie AI Animator Provider Manifest — Phase 7."""

from studio.shared.providers_common import ProviderManifest


def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="kie_ai",
        label="Kie AI",
        domain="animator",
        kind="cloud",
        version="1.0.0",
        requires=["api_key"],
        capabilities={
            "test_connection": True,
            "single_scene": True,
            "batch": True,
        },
        aliases=["kie-ai"],
        description="Image-to-video and image generation through the Kie AI API.",
        environment={"api_key": "KIE_AI_API_KEY", "model": "KIE_AI_MODEL"},
    )