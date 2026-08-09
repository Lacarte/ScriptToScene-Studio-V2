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
            # Declared by step 12.4 so the Assets page can offer the
            # storyboard-to-video hand-off without asking *which* provider it is
            # talking to (contracts.md §20.4). The route half stays with 14.3.
            "image_to_video": True,
        },
        # The page the user must have open for the extension to drive. It was a
        # literal in `AssetsPage.vue` and `useAssets.js` until 12.4; a provider's
        # own URL belongs in its manifest (§20.1).
        open_url="https://grok.com/imagine",
        # `midjourney` is the third legacy wire value normalized here today
        # (animator/schemas.py:30-36, contracts.md §14.4).
        aliases=["grok", "midjourney"],
        description="Animator takes driven by the browser extension over a WebSocket.",
    )