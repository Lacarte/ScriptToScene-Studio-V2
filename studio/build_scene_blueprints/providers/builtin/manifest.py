"""Manifest for the transitional `builtin` scene-blueprint provider (step 12.3).

The bridge the plan's Phase 12 bridging rule requires: `scenes.blueprint` cannot
select `provider_id` from an empty catalog, and the real scene-blueprint provider
does not exist until 13.4. This registers the service that runs today under a
provider identity so the node can be converted now, and 13.4 replaces it with
`n8n` while keeping `builtin` as an input alias (contracts.md §40.3 rule 4).

There is deliberately no `settings_schema.py`. A bridge carries "exactly the
fields being removed from the node definition", and `scenes.blueprint` loses
none: §41.3 M4 forbids bumping its `type_version`, so every field it has today
stays a node field. An empty schema would only advertise a settings form with
nothing in it.
"""

from studio.shared.providers_common.registry import ProviderManifest


def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="builtin",
        label="Built-in scene blueprint",
        domain="scene_blueprint",
        kind="webhook",
        version="1.0.0",
        requires=[],
        capabilities={
            "chaptering": True,
            "coherence_scoring": True,
            "sfx_report": True,
            "batch": True,
            "single_scene": False,
        },
        description=(
            "The scene-blueprint service shipped with the app: one webhook call "
            "per chapter, planned and validated into scenes and image prompts."
        ),
    )
