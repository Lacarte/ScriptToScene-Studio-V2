"""The `builtin` script provider — a thin passthrough to `studio.story.service`.

Deliberately not a reimplementation. `generate()` forwards the configuration it
is handed and returns whatever `generate_story` returns, so the artifact this
provider writes is byte-identical to the one the pre-conversion adapter wrote
(the Phase 12 bridging rule; asserted in `tests/test_workflow_provider_nodes.py`).

Phase 13 replaces this package with the real `gemini` provider behind the same
`generate()` seam. Step 13.1 subclasses `ScriptProvider` so the bridge already
sits on the domain interface.
"""

from typing import Any, Mapping

from studio.story.providers.base import ScriptProvider


class BuiltinScriptProvider(ScriptProvider):
    """Passthrough over the importable story service."""

    def generate(self, configuration: Mapping[str, Any], *, project_id: str) -> dict:
        from studio.story.service import generate_story

        return generate_story(configuration, project_id=project_id)


def create() -> BuiltinScriptProvider:
    return BuiltinScriptProvider()


def health_check(settings: dict) -> dict:
    """Report whether a story webhook is configured. No request is made."""
    from config import N8N_STORY_WEBHOOK_URL

    configured = bool(settings.get("webhook_url") or N8N_STORY_WEBHOOK_URL)
    return {
        "status": "ok" if configured else "warn",
        "message": (
            "Story webhook configured"
            if configured
            else "No story webhook URL is configured"
        ),
    }
