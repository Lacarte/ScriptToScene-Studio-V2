"""Domain catalog — the single declaration of the supported provider domains.

Frozen by contracts.md §19.1: exactly five domains (Music and Captions are out of
scope by owner decision). Adding a sixth domain is one `DomainSpec` entry plus a
provider folder — it must not require editing the registry class, the settings
manager, a route, or a Vue component.

This module is the only place a domain name is written down. `ProviderRegistry.VALID_DOMAINS`,
`settings_manager.validate_settings`, and `settings_manager._default_settings` all derive
from `DOMAINS` so they can never drift.
"""

import os
from dataclasses import dataclass

from config import ROOT_DIR


# Capabilities every domain understands (contracts.md §20.4).
SHARED_CAPABILITIES = frozenset({
    "test_connection",
    "single_scene",
    "batch",
    "async_job",
    "push_callbacks",
    "cancel",
    "progress",
})


@dataclass(frozen=True)
class DomainSpec:
    """Declarative description of one provider domain."""

    id: str
    label: str
    package: str
    providers_base: str
    default_provider: str
    capability_vocabulary: frozenset[str]
    legacy_selection_key: str | None = None
    request_model: str | None = None
    result_model: str | None = None


def _base(*parts: str) -> str:
    return os.path.join(ROOT_DIR, *parts)


def _caps(*extra: str) -> frozenset[str]:
    return SHARED_CAPABILITIES | frozenset(extra)


# Declaration order is the discovery/registration order (contracts.md §21.2).
DOMAINS: dict[str, DomainSpec] = {
    spec.id: spec
    for spec in (
        DomainSpec(
            id="script",
            label="Script / Story",
            package="studio.story.providers",
            providers_base=_base("studio", "story", "providers"),
            default_provider="builtin",
            capability_vocabulary=_caps("structured_sections", "language_select", "offline"),
            request_model="studio.story.providers.contract:ScriptRequest",
            result_model="studio.story.providers.contract:ScriptResultPayload",
        ),
        DomainSpec(
            id="scene_blueprint",
            label="Scene Blueprint",
            package="studio.build_scene_blueprints.providers",
            providers_base=_base("studio", "build_scene_blueprints", "providers"),
            default_provider="builtin",
            capability_vocabulary=_caps("chaptering", "coherence_scoring", "sfx_report"),
        ),
        DomainSpec(
            id="tts",
            label="Text to Speech",
            package="studio.tts.providers",
            providers_base=_base("studio", "tts", "providers"),
            default_provider="kokoro",
            capability_vocabulary=_caps(
                "streaming", "voice_list", "voice_blend", "speed_control", "model_download"
            ),
            legacy_selection_key="sts-tts-provider",
        ),
        DomainSpec(
            id="storyboard",
            label="Storyboard",
            package="studio.storyboard.providers",
            providers_base=_base("studio", "storyboard", "providers"),
            default_provider="gemini_ws",
            capability_vocabulary=_caps("image_edit", "watermark_removal", "prompt_prefix"),
            legacy_selection_key="sts-storyboard-provider",
        ),
        DomainSpec(
            id="animator",
            label="Animator",
            package="studio.animator.providers",
            providers_base=_base("studio", "animator", "providers"),
            default_provider="grok_automa",
            capability_vocabulary=_caps(
                "image_to_video", "duration_control", "resolution_select"
            ),
            legacy_selection_key="sts-asset-provider",
        ),
    )
}

DOMAIN_IDS: frozenset[str] = frozenset(DOMAINS)


def get_domain(domain_id: str) -> DomainSpec:
    """Return the `DomainSpec` for `domain_id`, or raise `ValueError`."""
    try:
        return DOMAINS[domain_id]
    except KeyError:
        raise ValueError(
            f"Unknown provider domain: {domain_id!r}. Known domains: {sorted(DOMAINS)}"
        ) from None


__all__ = ["DomainSpec", "DOMAINS", "DOMAIN_IDS", "SHARED_CAPABILITIES", "get_domain"]
