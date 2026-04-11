"""Grok Automa Animator Provider — Phase 7.

Bridges to studio.animator for WebSocket handling.
"""

from loguru import logger

from studio.animator.providers.base import (
    AnimatorProvider,
    JobHandle,
    JobStatus,
    SceneResult,
)


class GrokAutomaProvider(AnimatorProvider):
    """Animator provider using Grok Chrome extension via WebSocket."""

    def __init__(self):
        self._animator = None

    def _get_animator(self):
        if self._animator is None:
            from studio.animator import routes as animator_routes
            self._animator = animator_routes
        return self._animator

    def submit(
        self,
        project_id: str,
        scenes: list[dict],
        settings: dict,
        on_progress=None,
    ) -> JobHandle:
        animator = self._get_animator()
        
        mode = settings.get("mode", "video")
        quality = settings.get("quality", "480p")
        duration = settings.get("duration", "6s")
        
        # Queue the job via animator routes
        animator.add_job(
            project_id=project_id,
            scenes=scenes,
            grok_mode=mode,
            quality=quality,
            duration=duration,
        )
        
        return JobHandle(
            job_id=f"{project_id}",
            status="pending",
        )

    def poll(self, job_id: str, settings: dict) -> JobStatus:
        animator = self._get_animator()
        job = animator._asset_jobs.get(job_id)
        if not job:
            return JobStatus(job_id=job_id, status="unknown")
        
        statuses = job.get("scene_statuses", {})
        done = sum(1 for s in statuses.values() if s.get("status") == "complete")
        total = len(statuses)
        progress = done / total if total > 0 else 0.0
        
        return JobStatus(
            job_id=job_id,
            status="complete" if done == total else "processing",
            progress=progress,
        )

    def shutdown(self) -> None:
        pass


def register_runtime(app, sock=None):
    """Register WebSocket routes for the Grok extension."""
    from studio.animator import routes as animator_routes
    
    # Rename function to match contract
    def _register_wrapper(sock):
        animator_routes.init_animator_ws(sock)
    
    # Call with the sock instance
    _register_wrapper(sock)


def validate_settings(settings: dict) -> list[dict]:
    return []


def health_check(settings: dict) -> dict:
    from studio.animator import routes as animator_routes
    
    has_clients = len(animator_routes._ws_clients) > 0
    return {
        "status": "ok" if has_clients else "warn",
        "message": "Extension connected" if has_clients else "No extension connected",
        "details": {"clients": len(animator_routes._ws_clients)},
    }


_provider_instance = None


def get_provider():
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = GrokAutomaProvider()
    return _provider_instance