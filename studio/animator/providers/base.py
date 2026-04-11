"""Animator Provider Base Contract — Phase 3.

Abstract base class defining the animator provider interface.
All animator providers must implement these methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable


@dataclass
class JobHandle:
    """Handle for a submitted animator job."""
    job_id: str
    status: str
    created_at: str | None = None


@dataclass
class JobStatus:
    """Status of an animator job."""
    job_id: str
    status: str
    progress: float = 0.0
    message: str | None = None
    result: dict | None = None
    error: str | None = None


@dataclass
class SceneResult:
    """Result for a single scene's animation."""
    scene_index: int
    video_url: str | None = None
    video_path: str | None = None
    thumbnail_url: str | None = None
    metadata: dict | None = None


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
