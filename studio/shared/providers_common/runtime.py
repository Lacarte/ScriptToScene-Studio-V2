"""Runtime Base Class — Phase 3.

Base class for extension providers that need to register WebSocket routes.
Extension providers (kind='extension') can register their own WS routes
and own their client pool, handshake, queueing, and reconnect logic.

Usage:
    class MyExtensionRuntime(Runtime):
        def register_routes(self, app, sock):
            # Register WebSocket routes and handlers
            @sock.route('/ws/my-extension')
            def my_handler(ws):
                ...
    
    # In provider's runtime.py:
    def register_runtime(app, sock):
        MyExtensionRuntime().register(app, sock)
"""

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger


class Runtime(ABC):
    """Base class for extension provider runtimes.
    
    Extension providers can override register_routes() to add
    WebSocket routes and initialize their runtime.
    """
    
    @abstractmethod
    def register_routes(self, app, sock) -> None:
        """Register WebSocket routes and initialize runtime.
        
        Called once at app boot if the provider has kind='extension'.
        
        Args:
            app: Flask application instance
            sock: Flask-Sock instance
        """
        pass
    
    def shutdown(self) -> None:
        """Clean up runtime resources. Called on app shutdown."""
        pass


def call_provider_runtime(provider_id: str, provider_module: Any, app, sock) -> None:
    """Call register_runtime() on a provider module if it exists.
    
    Args:
        provider_id: Provider identifier
        provider_module: Loaded provider module
        app: Flask application
        sock: Flask-Sock instance
    """
    if hasattr(provider_module, 'register_runtime'):
        try:
            provider_module.register_runtime(app, sock)
            logger.info("[runtime] Initialized runtime for provider '{}'", provider_id)
        except Exception as e:
            logger.error("[runtime] Failed to initialize runtime for '{}': {}", 
                        provider_id, e)
    else:
        logger.debug("[runtime] Provider '{}' has no register_runtime hook", provider_id)
