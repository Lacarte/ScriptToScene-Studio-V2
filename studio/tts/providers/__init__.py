"""TTS Provider Registry — Phase 2-3.

Performs discovery scan on module import to register all TTS providers.
Providers are discovered by scanning this directory for subfolders containing manifest.py.
"""

import os

from loguru import logger

from config import ROOT_DIR
from studio.shared.providers_common import ProviderRegistry, call_provider_runtime

registry = ProviderRegistry(domain='tts')

_PROVIDERS_BASE = os.path.join(ROOT_DIR, "studio", "tts", "providers")

def discover():
    """Scan for and register all TTS providers (idempotent)."""
    if registry._discovered:
        return registry
    registry.discovery_scan(_PROVIDERS_BASE)
    return registry


def get_provider(provider_id: str):
    """Get a TTS provider by ID."""
    return registry.get(provider_id)


def list_providers():
    """List all registered TTS providers."""
    return registry.list_providers()


def init_tts_registry(app=None, sock=None):
    """Called at app startup to discover and register all TTS providers.
    
    Args:
        app: Flask application instance
        sock: Flask-Sock instance
    """
    discover()
    logger.info("[providers] tts: {} registered, ids={}", 
               len(registry), registry.list_ids())
    
    if app is not None and sock is not None:
        for provider_id in registry.list_ids():
            provider = registry.get(provider_id)
            if provider and provider.kind == 'extension':
                runtime_mod = provider.provider_module or provider.module
                call_provider_runtime(provider_id, runtime_mod, app, sock)


discover()

__all__ = ['registry', 'discover', 'get_provider', 'list_providers', 'init_tts_registry']
