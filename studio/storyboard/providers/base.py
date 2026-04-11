"""Storyboard Provider Base Contract — Phase 3.

Abstract base class defining the storyboard provider interface.
All storyboard providers must implement these methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class JobHandle:
    """Handle for a submitted storyboard job."""
    job_id: str
    status: str
    created_at: str | None = None


@dataclass
class JobStatus:
    """Status of a storyboard job."""
    job_id: str
    status: str
    progress: float = 0.0
    message: str | None = None
    result: dict | None = None
    error: str | None = None


@dataclass
class SceneResult:
    """Result for a single scene's storyboard."""
    scene_index: int
    image_url: str | None = None
    image_path: str | None = None
    thumbnail_url: str | None = None
    metadata: dict | None = None


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
