"""Manifest for the transitional `builtin` script provider (step 12.3).

The bridge the plan's Phase 12 bridging rule requires: `story.generate` cannot
select `provider_id` from an empty catalog, and the real script providers do not
exist until Phase 13. This registers the service that runs today under a
provider identity so the node can be converted now, and 13.2 replaces it with
`gemini` while keeping `builtin` as an input alias (contracts.md §40.3 rule 4).

There is deliberately no `settings_schema.py`. A bridge carries "exactly the
fields being removed from the node definition", and `story.generate` loses none:
§41.3 M4 forbids bumping its `type_version`, so every field it has today stays a
node field. An empty schema would only advertise a settings form with nothing
in it.
"""

from studio.shared.providers_common.registry import ProviderManifest


def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="builtin",
        label="Built-in story generator",
        domain="script",
        kind="webhook",
        version="1.0.0",
        requires=[],
        capabilities={
            "structured_sections": True,
            "language_select": True,
            "offline": False,
            "single_scene": False,
            "batch": False,
        },
        description=(
            "The story service shipped with the app: one webhook call, parsed "
            "into the hook/build/climax/CTA sections used downstream."
        ),
    )
