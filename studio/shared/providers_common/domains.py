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
#
# `exclusive_execution` is added by step 15.1. It is a scheduling property, not a
# feature: a provider owning a heavy in-process singleton (§20.2 `local`) declares
# it, and the platform serializes that provider's invocations on one process-wide
# lock. It belongs in the shared set rather than the `tts` vocabulary because
# nothing about it is TTS-specific — any domain may ship a local provider.
SHARED_CAPABILITIES = frozenset({
    "test_connection",
    "single_scene",
    "batch",
    "async_job",
    "push_callbacks",
    "cancel",
    "progress",
    "exclusive_execution",
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
            # Historical AI path (step 13.2). The 12.3 `builtin` bridge ID remains
            # a permanent *input* alias on the gemini package (contracts.md §40.3).
            default_provider="gemini",
            capability_vocabulary=_caps("structured_sections", "language_select", "offline"),
            request_model="studio.story.providers.contract:ScriptRequest",
            result_model="studio.story.providers.contract:ScriptResultPayload",
        ),
        DomainSpec(
            id="scene_blueprint",
            label="Scene Blueprint",
            package="studio.build_scene_blueprints.providers",
            providers_base=_base("studio", "build_scene_blueprints", "providers"),
            # Historical AI path (step 13.4). The 12.3 `builtin` bridge ID remains
            # a permanent *input* alias on the n8n package (contracts.md §40.3).
            default_provider="n8n",
            capability_vocabulary=_caps("chaptering", "coherence_scoring", "sfx_report"),
            request_model="studio.build_scene_blueprints.providers.contract:SceneBlueprintRequest",
            result_model="studio.build_scene_blueprints.providers.contract:SceneBlueprintResultPayload",
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
            request_model="studio.tts.providers.contract:TTSRequest",
            result_model="studio.tts.providers.contract:TTSResultPayload",
        ),
        DomainSpec(
            id="storyboard",
            label="Storyboard",
            package="studio.storyboard.providers",
            providers_base=_base("studio", "storyboard", "providers"),
            default_provider="gemini_ws",
            # `auto_animate` is the storyboard→animator hand-off the Gemini
            # extension performs on job completion (step 14.2): declared by the
            # provider that does it rather than hardcoded in its transport.
            capability_vocabulary=_caps(
                "image_edit", "watermark_removal", "prompt_prefix", "auto_animate"
            ),
            legacy_selection_key="sts-storyboard-provider",
            request_model="studio.storyboard.providers.contract:StoryboardRequest",
            result_model="studio.storyboard.providers.contract:StoryboardResultPayload",
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
            request_model="studio.animator.providers.contract:AnimatorRequest",
            result_model="studio.animator.providers.contract:AnimatorResultPayload",
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
