"""Storyboard Provider Base Contract — Phase 3.

Abstract base class defining the storyboard provider interface.
All storyboard providers must implement these methods.

Step 11.4 deleted this module's copies of `JobHandle`, `JobStatus`, and
`SceneResult`. They were field-for-field duplicates of the animator ones
(contracts.md §14.6) and now have one shared definition in
`providers_common.jobs`; the names are re-exported here so existing
`from studio.storyboard.providers.base import JobHandle` imports keep resolving,
and `SceneResult` is the media-neutral `UnitResult` (§33.1).
"""

from abc import ABC, abstractmethod
from typing import Callable

from studio.shared.providers_common.jobs import (  # noqa: F401  (re-exported)
    JobHandle,
    JobStatus,
    SceneResult,
    UnitResult,
)


class StoryboardProvider(ABC):
    """Base class for all storyboard providers.
    
    Providers must implement:
    - submit(): Submit a generation job
    - poll(): Check job status
    
    Optional:
    - generate_one(): Generate a single scene
    """
    
    @abstractmethod
    def submit(
        self,
        project_id: str,
        scenes: list[dict],
        settings: dict,
        on_progress: Callable[[dict], None] | None = None,
    ) -> JobHandle:
        """Submit a storyboard generation job.
        
        Args:
            project_id: Project identifier
            scenes: List of scene dicts with 'index', 'prompt', 'aspect_ratio', etc.
            settings: Provider settings from settings.json
            on_progress: Optional callback for progress updates
            
        Returns:
            JobHandle with job_id and initial status
        """
        pass
    
    @abstractmethod
    def poll(self, job_id: str, settings: dict) -> JobStatus:
        """Poll status of a storyboard job.
        
        Args:
            job_id: Job identifier from submit()
            settings: Provider settings
            
        Returns:
            JobStatus with current state
        """
        pass
    
    def generate_one(
        self,
        scene: dict,
        settings: dict,
        output_dir: str | None = None,
    ) -> SceneResult:
        """Generate a storyboard image for a single scene. Optional.
        
        Args:
            scene: Scene dict with 'index', 'prompt', 'aspect_ratio'
            settings: Provider settings
            output_dir: Optional output directory
            
        Returns:
            SceneResult with image URL/path
        """
        raise NotImplementedError(f"generate_one not supported by {self.__class__.__name__}")
    
    def shutdown(self) -> None:
        """Clean up resources. Called on app shutdown."""
        pass
