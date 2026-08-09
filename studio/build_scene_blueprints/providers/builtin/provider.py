"""The `builtin` scene-blueprint provider — a passthrough to `_step_scenes`.

Deliberately not a reimplementation. `generate()` forwards the segments and
configuration it is handed and returns whatever `_step_scenes` returns, so the
`scenes.json` this provider writes is byte-identical to the one the
pre-conversion adapter wrote (the Phase 12 bridging rule; asserted in
`tests/test_workflow_provider_nodes.py`).

Step 13.4 replaces this package with the real `n8n` provider behind the same
`generate()` seam.
"""

from typing import Any, Mapping


class BuiltinSceneBlueprintProvider:
    """Passthrough over the importable scene-blueprint pipeline step."""

    def generate(
        self,
        segments: Mapping[str, Any],
        configuration: Mapping[str, Any],
        *,
        project_id: str,
    ) -> dict:
        from studio.pipeline.services import _step_scenes

        return _step_scenes(segments, configuration, project_id)


def create() -> BuiltinSceneBlueprintProvider:
    return BuiltinSceneBlueprintProvider()


def health_check(settings: dict) -> dict:
    """Report whether a scene webhook is configured. No request is made."""
    from config import N8N_WEBHOOK_URL

    configured = bool(settings.get("webhook_url") or N8N_WEBHOOK_URL)
    return {
        "status": "ok" if configured else "warn",
        "message": (
            "Scene blueprint webhook configured"
            if configured
            else "No scene blueprint webhook URL is configured"
        ),
    }
