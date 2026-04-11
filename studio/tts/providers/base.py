"""TTS Provider Base Contract — Phase 3.

Abstract base class defining the TTS provider interface.
All TTS providers must implement these methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional


@dataclass
class Voice:
    """A voice available for synthesis."""
    id: str
    name: str
    language: str
    gender: Optional[str] = None
    preview_url: Optional[str] = None


@dataclass
class TTSResult:
    """Result of a synthesize() call."""
    audio_path: str
    duration_seconds: float
    format: str = "wav"
    sample_rate: int = 24000
    metadata: Optional[dict] = None


@dataclass
class TTSStreamChunk:
    """A chunk of streamed audio."""
    data: bytes
    is_final: bool = False


class TTSProvider(ABC):
    """Base class for all TTS providers.
    
    Providers must implement:
    - synthesize(): Generate audio from text
    - list_voices(): Return available voices
    
    Optional:
    - list_models(): Return available models
    - download_model(): Download a model locally
    - stream(): Stream audio chunks
    """
    
    @abstractmethod
    def synthesize(
        self,
        text: str,
        settings: dict,
        voice: Optional[str] = None,
        speed: float = 1.0,
        on_progress: Optional[Callable] = None,
    ) -> TTSResult:
        """Synthesize speech from text.
        
        Args:
            text: Text to synthesize
            settings: Provider settings from settings.json
            voice: Voice ID to use (overrides settings)
            speed: Playback speed multiplier
            on_progress: Optional callback for progress updates
            
        Returns:
            TTSResult with audio path and metadata
        """
        pass
    
    @abstractmethod
    def list_voices(self, settings: dict) -> list[Voice]:
        """Return list of available voices.
        
        Args:
            settings: Provider settings
            
        Returns:
            List of Voice objects
        """
        pass
    
    def list_models(self, settings: dict) -> list[dict]:
        """Return list of available models. Optional.
        
        Args:
            settings: Provider settings
            
        Returns:
            List of model info dicts
        """
        return []
    
    def download_model(self, model_id: str, settings: dict) -> str:
        """Download a model locally. Optional.
        
        Args:
            model_id: Model identifier
            settings: Provider settings
            
        Returns:
            Path to downloaded model
        """
        raise NotImplementedError(f"download_model not supported by {self.__class__.__name__}")
    
    def stream(
        self,
        text: str,
        settings: dict,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> Iterator[TTSStreamChunk]:
        """Stream audio chunks. Optional.
        
        Args:
            text: Text to synthesize
            settings: Provider settings
            voice: Voice ID
            speed: Playback speed
            
        Yields:
            TTSStreamChunk objects
        """
        raise NotImplementedError(f"stream not supported by {self.__class__.__name__}")
    
    def shutdown(self) -> None:
        """Clean up resources. Called on app shutdown."""
        pass
