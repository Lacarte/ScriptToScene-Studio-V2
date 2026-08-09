"""Animator Provider Base Contract — Phase 3.

Abstract base class defining the animator provider interface.
All animator providers must implement these methods.

Step 11.4 deleted this module's copies of `JobHandle`, `JobStatus`, and
`SceneResult` — the storyboard copies were field-for-field identical
(contracts.md §14.6). The one shared definition lives in
`providers_common.jobs`; `SceneResult`'s `video_url`/`video_path` split is
replaced by the media-neutral `UnitResult` that both visual domains now produce
(§33.1).
"""

from abc import ABC, abstractmethod
from typing import Callable

from studio.shared.providers_common.jobs import (  # noqa: F401  (re-exported)
    JobHandle,
    JobStatus,
    SceneResult,
    UnitResult,
)


class AnimatorProvider(ABC):
    """Base class for all animator providers.
    
    Providers must implement:
    - submit(): Submit an animation job
    - poll(): Check job status
    
    Optional:
    - open_url(): Open the provider's UI
    """
    
    @abstractmethod
    def submit(
        self,
        project_id: str,
        scenes: list[dict],
        settings: dict,
        on_progress: Callable[[dict], None] | None = None,
    ) -> JobHandle:
        """Submit an animation job.
        
        Args:
            project_id: Project identifier
            scenes: List of scene dicts with 'index', 'image_url', 'prompt', 'duration'
            settings: Provider settings from settings.json
            on_progress: Optional callback for progress updates
            
        Returns:
            JobHandle with job_id and initial status
        """
        pass
    
    @abstractmethod
    def poll(self, job_id: str, settings: dict) -> JobStatus:
        """Poll status of an animator job.
        
        Args:
            job_id: Job identifier from submit()
            settings: Provider settings
            
        Returns:
            JobStatus with current state
        """
        pass
    
    def open_url(self, settings: dict) -> str | None:
        """Open the provider's UI URL. Optional.
        
        Args:
            settings: Provider settings
            
        Returns:
            URL to open, or None
        """
        return None
    
    def shutdown(self) -> None:
        """Clean up resources. Called on app shutdown."""
        pass
