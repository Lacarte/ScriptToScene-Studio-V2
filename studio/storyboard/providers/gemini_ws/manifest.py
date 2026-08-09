"""Gemini WS Storyboard Provider Manifest — Phase 6."""

from studio.shared.providers_common import ProviderManifest


def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="gemini_ws",
        label="Gemini (extension)",
        domain="storyboard",
        kind="extension",
        version="1.0.0",
        requires=[],
        capabilities={
            "test_connection": True,
            "single_scene": True,
            "batch": True,
            "push_callbacks": True,
        },
        open_url=None,
        aliases=["gemini"],
        description="Storyboard frames driven by the browser extension over a WebSocket.",
    )