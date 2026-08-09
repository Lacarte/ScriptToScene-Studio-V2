"""WaveSpeed Webhook Storyboard Provider Manifest — Phase 6."""

from studio.shared.providers_common import ProviderManifest


def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="wavespeed_webhook",
        label="Webhook / WaveSpeed",
        domain="storyboard",
        kind="cloud",
        version="1.0.0",
        requires=["webhook_url"],
        capabilities={
            "test_connection": True,
            "single_scene": True,
            "batch": True,
        },
        aliases=["webhook"],
        description="Storyboard frames via a user-supplied n8n webhook.",
        environment={"webhook_url": "N8N_STORYBOARD_WEBHOOK_URL"},
    )