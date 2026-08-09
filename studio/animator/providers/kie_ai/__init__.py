"""Kie AI provider package.

`generate_image` remains importable for tests and recorded-fixture tooling.
Routes and adapters never import it — they go through the registry (B8).
"""

from studio.animator.providers.kie_ai.provider import (
    KieAIProvider,
    create,
    generate_image,
)

__all__ = ["KieAIProvider", "create", "generate_image"]
