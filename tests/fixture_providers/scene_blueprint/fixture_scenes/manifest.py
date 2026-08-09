"""Offline fixture scene-blueprint provider — proves no-node-edit extensibility.

Registered only when a test points `DomainSpec.providers_base` at
`tests/fixture_providers/scene_blueprint/`. Never ships in the product catalog.
"""

from studio.shared.providers_common import ProviderManifest


def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="fixture_scenes",
        label="Fixture Scene Blueprint",
        domain="scene_blueprint",
        kind="local",
        version="1.0.0",
        contract_version=2,
        requires=[],
        aliases=["fixture-scenes"],
        capabilities={
            "test_connection": True,
            "chaptering": False,
            "coherence_scoring": True,
            "sfx_report": True,
            "batch": True,
            "offline": True,
        },
        description="Deterministic offline scene-blueprint provider for step 13.4.",
    )
