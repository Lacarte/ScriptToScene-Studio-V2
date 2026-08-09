"""Provider hub — one process-wide registry of registries (contracts.md §27).

The hub owns exactly one `ProviderRegistry` per catalog domain and resolves
`(domain, provider_id)` across all of them. The per-module
`studio/<module>/providers/__init__.py` files are thin compatibility facades built
by `bind_domain()` — they no longer own a registry of their own.

Owned by step 11.1. Provider construction, `shutdown()` of constructed provider
instances, and alias resolution land in 11.2.
"""

import threading
from dataclasses import dataclass
from typing import Callable

from loguru import logger

from studio.shared.providers_common.domains import DOMAINS, DomainSpec, get_domain
from studio.shared.providers_common.registry import ProviderInstance, ProviderRegistry
from studio.shared.providers_common.runtime import call_provider_runtime


class ProviderHub:
    """Process-wide hub over the domain catalog."""

    def __init__(self, catalog: dict[str, DomainSpec] | None = None):
        self._catalog = catalog if catalog is not None else DOMAINS
        self._registries: dict[str, ProviderRegistry] = {}
        self._lock = threading.RLock()

    # -- catalog -----------------------------------------------------------

    def domains(self) -> list[str]:
        """Domain ids in catalog declaration order (contracts.md §21.2)."""
        return list(self._catalog)

    def spec(self, domain: str) -> DomainSpec:
        """Return the `DomainSpec` for `domain`, or raise `ValueError`."""
        try:
            return self._catalog[domain]
        except KeyError:
            return get_domain(domain)

    def registry(self, domain: str) -> ProviderRegistry:
        """Return the one registry for `domain`, creating it on first use."""
        with self._lock:
            existing = self._registries.get(domain)
            if existing is not None:
                return existing
            self.spec(domain)  # validates the domain against the catalog
            created = ProviderRegistry(domain=domain, valid_domains=frozenset(self._catalog))
            self._registries[domain] = created
            return created

    # -- discovery ---------------------------------------------------------

    def discover(self, domain: str) -> ProviderRegistry:
        """Scan `domain`'s provider folder once. Idempotent."""
        registry = self.registry(domain)
        if registry._discovered:
            return registry
        registry.discovery_scan(self.spec(domain).providers_base)
        return registry

    def discover_all(self) -> None:
        """Discover every catalog domain, in declaration order."""
        for domain in self.domains():
            self.discover(domain)

    def bind_runtimes(self, app, sock) -> None:
        """Call `register_runtime()` on every discovered `extension` provider.

        Runs after all domains are discovered so a runtime can rely on the full
        catalog being present (contracts.md §21.2 item 4).
        """
        if app is None or sock is None:
            return
        for domain in self.domains():
            registry = self.registry(domain)
            for provider in registry.list_providers():
                if provider.kind != "extension":
                    continue
                runtime_mod = provider.provider_module or provider.module
                call_provider_runtime(provider.id, runtime_mod, app, sock)

    # -- lookup ------------------------------------------------------------

    def get(self, domain: str, provider_id: str) -> ProviderInstance | None:
        """Resolve one provider. Unknown domains return `None` rather than raising.

        Discovery is triggered on first lookup, so a caller that never went through
        application startup still sees the full catalog.

        Alias resolution (id first, then manifest alias) arrives with manifest
        aliases in 11.2; today only canonical ids resolve.
        """
        if domain not in self._catalog:
            return None
        return self.discover(domain).get(provider_id)

    def list(self, domain: str) -> list[ProviderInstance]:
        """List the providers registered for `domain` (empty for unknown domains)."""
        if domain not in self._catalog:
            return []
        return self.discover(domain).list_providers()

    def catalog(self, selected: dict[str, str | None] | None = None) -> dict:
        """Serialize every domain for API responses.

        Args:
            selected: optional `domain -> selected_provider_id` mapping.
        """
        selected = selected or {}
        return {
            domain: self.discover(domain).to_dict(selected_provider=selected.get(domain))
            for domain in self.domains()
        }

    # -- teardown ----------------------------------------------------------

    def shutdown(self) -> None:
        """Clear every registry so the next discovery re-scans from disk.

        Registry objects are kept and cleared in place, because the per-module
        `providers/__init__.py` facades hold references to them. Calling
        `shutdown()` on constructed provider instances is 11.2's work — nothing
        constructs providers yet.
        """
        with self._lock:
            for registry in self._registries.values():
                registry.reset()


hub = ProviderHub()


def init_providers(app=None, sock=None) -> ProviderHub:
    """Application startup entry point: discover all domains, then bind runtimes."""
    hub.discover_all()
    for domain in hub.domains():
        registry = hub.registry(domain)
        logger.info(
            "[providers] {}: {} registered, ids={}", domain, len(registry), registry.list_ids()
        )
    hub.bind_runtimes(app, sock)
    return hub


@dataclass(frozen=True)
class DomainBinding:
    """The public surface of a `studio/<module>/providers/__init__.py`.

    Unpacks in the historical order:
    `registry, discover, get_provider, list_providers, init_registry`.
    """

    registry: ProviderRegistry
    discover: Callable[[], ProviderRegistry]
    get_provider: Callable[[str], ProviderInstance | None]
    list_providers: Callable[[], list[ProviderInstance]]
    init_registry: Callable[..., ProviderRegistry]

    def __iter__(self):
        return iter(
            (
                self.registry,
                self.discover,
                self.get_provider,
                self.list_providers,
                self.init_registry,
            )
        )


def bind_domain(domain: str, discover_now: bool = True) -> DomainBinding:
    """Build the compatibility facade for one domain's provider package.

    Replaces the three structurally identical 57-line `providers/__init__.py`
    copies (contracts.md §14.6, §27).
    """
    registry = hub.registry(domain)

    def discover() -> ProviderRegistry:
        return hub.discover(domain)

    def get_provider(provider_id: str) -> ProviderInstance | None:
        return hub.get(domain, provider_id)

    def list_providers() -> list[ProviderInstance]:
        return hub.list(domain)

    def init_registry(app=None, sock=None) -> ProviderRegistry:
        discover()
        logger.info(
            "[providers] {}: {} registered, ids={}", domain, len(registry), registry.list_ids()
        )
        if app is not None and sock is not None:
            for provider in registry.list_providers():
                if provider.kind == "extension":
                    runtime_mod = provider.provider_module or provider.module
                    call_provider_runtime(provider.id, runtime_mod, app, sock)
        return registry

    if discover_now:
        discover()

    return DomainBinding(registry, discover, get_provider, list_providers, init_registry)


__all__ = ["ProviderHub", "hub", "init_providers", "DomainBinding", "bind_domain"]
