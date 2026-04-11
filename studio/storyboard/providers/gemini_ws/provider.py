"""Gemini WS Storyboard Provider — Phase 6.

Bridges to studio.storyboard.gemini_ws for WebSocket handling.
"""

from loguru import logger

from studio.storyboard.providers.base import (
    StoryboardProvider,
    JobHandle,
    JobStatus,
    SceneResult,
)


class GeminiWSProvider(StoryboardProvider):
    """Storyboard provider using Gemini Chrome extension via WebSocket."""

    def __init__(self):
        self._gemini_ws = None

    def _get_gemini_ws(self):
        if self._gemini_ws is None:
            from studio.storyboard import gemini_ws
            self._gemini_ws = gemini_ws
        return self._gemini_ws

    def submit(
        self,
        project_id: str,
        scenes: list[dict],
        settings: dict,
        on_progress=None,
    ) -> JobHandle:
        gw = self._get_gemini_ws()
        auto_type = settings.get("auto_type", False)
        
        gw.add_job(project_id, scenes, auto_type=auto_type)
        
        return JobHandle(
            job_id=f"{project_id}",
            status="pending",
        )

    def poll(self, job_id: str, settings: dict) -> JobStatus:
        return JobStatus(
            job_id=job_id,
            status="pending",
            progress=0.0,
        )

    def generate_one(
        self,
        scene: dict,
        settings: dict,
        output_dir=None,
    ) -> SceneResult:
        raise NotImplementedError(
            "gemini_ws uses push callbacks, use submit() instead"
        )

    def shutdown(self) -> None:
        pass


def register_runtime(app, sock=None):
    """Register WebSocket routes for the Gemini extension."""
    from studio.storyboard import gemini_ws
    gemini_ws.register_runtime(app, sock)


def validate_settings(settings: dict) -> list[dict]:
    return []


def health_check(settings: dict) -> dict:
    from studio.storyboard import gemini_ws
    has_clients = len(gemini_ws._ws_clients) > 0
    return {
        "status": "ok" if has_clients else "warn",
        "message": "Extension connected" if has_clients else "No extension connected",
        "details": {"clients": len(gemini_ws._ws_clients)},
    }


_provider_instance = None


def get_provider():
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = GeminiWSProvider()
    return _provider_instance