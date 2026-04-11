"""Kie AI provider package.

Re-exports generate_image so legacy callers like animation_routes can keep
using `from .providers.kie_ai import generate_image` after the file→folder
migration in Phase 7.
"""

from studio.animator.providers.kie_ai.provider import (
    KieAIProvider,
    generate_image,
    get_provider,
)

__all__ = ["KieAIProvider", "generate_image", "get_provider"]
