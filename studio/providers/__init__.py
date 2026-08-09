"""Provider API blueprint — the one HTTP surface over the provider hub.

Step 11.5 moved the five provider handlers and the two `/api/settings/v2`
handlers out of the editor blueprint (`studio/editor/routes.py`), where each one
re-imported the domain registries, and onto the process-wide hub
(contracts.md §27). The URLs are unchanged; only the owning module moved.
"""

from studio.providers.routes import providers_bp

__all__ = ["providers_bp"]
