"""Grok Automa Animator Provider Manifest — Phase 7."""

from studio.shared.providers_common import ProviderManifest


def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="grok_automa",
        label="Grok (extension)",
        domain="animator",
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
    )