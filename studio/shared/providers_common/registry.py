"""Provider Registry — Phase 2.

Base registry class with domain scoping and discovery logic.
Scans provider folders, loads manifests, applies broken-provider isolation.
"""

import importlib
import importlib.util
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger


@dataclass
class ProviderManifest:
    """Required manifest returned by every provider."""
    id: str
    label: str
    domain: str
    kind: str
    version: str
    requires: list[str] = field(default_factory=list)
    capabilities: dict[str, bool] = field(default_factory=dict)
    open_url: str | None = None


@dataclass
class HealthResult:
    """Result of a provider health check."""
    status: str
    latency_ms: float | None = None
    message: str | None = None
    details: dict | None = None


@dataclass
class ValidationIssue:
    """A validation issue with provider settings."""
    field: str
    severity: str
    message: str


class ProviderInstance:
    """Wrapper around a loaded provider module with metadata.

    Holds up to three modules loaded from the provider folder:
      - module: manifest.py (required, holds manifest() function)
      - provider_module: provider.py (optional, holds validate_settings/health_check)
      - schema_module: settings_schema.py (optional, holds settings_schema())
    """

    def __init__(
        self,
        provider_id: str,
        module: Any,
        manifest: ProviderManifest,
        provider_module: Any = None,
        schema_module: Any = None,
    ):
        self.id = provider_id
        self.module = module
        self.provider_module = provider_module
        self.schema_module = schema_module
        self.manifest = manifest
        self._settings_schema = None
        self._cached_validation = None
        self._cached_health = None

    def _resolve(self, attr_name: str) -> Any:
        """Find a callable named `attr_name` across the loaded modules.

        Precedence: provider_module > schema_module > module (manifest).
        """
        for mod in (self.provider_module, self.schema_module, self.module):
            if mod is not None and hasattr(mod, attr_name):
                return getattr(mod, attr_name)
        return None
    
    @property
    def label(self) -> str:
        return self.manifest.label
    
    @property
    def domain(self) -> str:
        return self.manifest.domain
    
    @property
    def kind(self) -> str:
        return self.manifest.kind
    
    @property
    def version(self) -> str:
        return self.manifest.version
    
    @property
    def capabilities(self) -> dict[str, bool]:
        return self.manifest.capabilities
    
    @property
    def requires(self) -> list[str]:
        return self.manifest.requires
    
    def settings_schema(self) -> dict | None:
        """Lazy-load settings schema from provider module."""
        if self._settings_schema is None:
            fn = self._resolve('settings_schema')
            if fn is not None:
                try:
                    self._settings_schema = fn()
                except Exception as e:
                    logger.warning("[registry] Failed to get settings_schema for {}: {}", self.id, e)
                    self._settings_schema = None
        return self._settings_schema

    def validate_settings(self, settings: dict) -> list[ValidationIssue]:
        """Validate provider settings."""
        fn = self._resolve('validate_settings')
        if fn is not None:
            try:
                raw_issues = fn(settings)
                return [
                    ValidationIssue(
                        field=i.get('field', ''),
                        severity=i.get('severity', 'warning'),
                        message=i.get('message', '')
                    ) if isinstance(i, dict) else i
                    for i in raw_issues
                ]
            except Exception as e:
                logger.warning("[registry] validate_settings failed for {}: {}", self.id, e)
                return [ValidationIssue(field='root', severity='error', message=str(e))]
        return []

    def health_check(self, settings: dict) -> HealthResult:
        """Check provider health."""
        fn = self._resolve('health_check')
        if fn is not None:
            try:
                result = fn(settings)
                if isinstance(result, dict):
                    return HealthResult(
                        status=result.get('status', 'unknown'),
                        latency_ms=result.get('latency_ms'),
                        message=result.get('message'),
                        details=result.get('details')
                    )
                elif isinstance(result, str):
                    return HealthResult(status=result)
                return result
            except Exception as e:
                logger.warning("[registry] health_check failed for {}: {}", self.id, e)
                return HealthResult(status='fail', message=str(e))
        return HealthResult(status='ok')
    
    def to_dict(self) -> dict:
        """Serialize to dict for API responses."""
        return {
            'id': self.id,
            'label': self.label,
            'domain': self.domain,
            'kind': self.kind,
            'version': self.version,
            'requires': self.requires,
            'capabilities': self.capabilities,
            'open_url': self.manifest.open_url,
            'has_settings': self.settings_schema() is not None,
        }


class ProviderRegistry:
    """Domain-scoped provider registry with discovery."""
    
    VALID_DOMAINS = {'tts', 'storyboard', 'animator'}
    
    def __init__(self, domain: str):
        if domain not in self.VALID_DOMAINS:
            raise ValueError(f"Invalid domain: {domain}. Must be one of {self.VALID_DOMAINS}")
        self.domain = domain
        self._providers: dict[str, ProviderInstance] = {}
        self._lock = threading.RLock()
        self._discovered = False
    
    def register(
        self,
        provider_id: str,
        module: Any,
        manifest: ProviderManifest,
        provider_module: Any = None,
        schema_module: Any = None,
    ) -> None:
        """Register a provider instance."""
        if manifest.domain != self.domain:
            logger.error("[registry] Cannot register {}: wrong domain (expected {}, got {})",
                        provider_id, self.domain, manifest.domain)
            return

        with self._lock:
            if provider_id in self._providers:
                logger.warning("[registry] Duplicate provider id '{}' in domain '{}', skipping",
                             provider_id, self.domain)
                return
            self._providers[provider_id] = ProviderInstance(
                provider_id, module, manifest,
                provider_module=provider_module,
                schema_module=schema_module,
            )
            logger.info("[registry] Registered provider '{}' ({}) in {}",
                       provider_id, manifest.label, self.domain)
    
    def get(self, provider_id: str) -> ProviderInstance | None:
        """Get a provider by ID."""
        return self._providers.get(provider_id)
    
    def list_providers(self) -> list[ProviderInstance]:
        """List all registered providers."""
        return list(self._providers.values())
    
    def list_ids(self) -> list[str]:
        """List all provider IDs."""
        return list(self._providers.keys())
    
    def __len__(self) -> int:
        return len(self._providers)
    
    def discovery_scan(self, providers_base: str) -> None:
        """Scan provider folders and load manifests.
        
        Args:
            providers_base: Base path like 'studio/tts/providers'
        """
        if not os.path.isdir(providers_base):
            logger.debug("[registry] Provider base not found: {}", providers_base)
            return
        
        for entry in os.listdir(providers_base):
            provider_path = os.path.join(providers_base, entry)
            if not os.path.isdir(provider_path):
                continue
            if entry.startswith('_') or entry.startswith('.'):
                continue
            
            manifest_file = os.path.join(provider_path, 'manifest.py')
            if not os.path.isfile(manifest_file):
                logger.debug("[registry] No manifest.py in {}, skipping", entry)
                continue
            
            self._load_provider(entry, provider_path, manifest_file)
        
        self._discovered = True
    
    def _load_module_from_file(self, file_path: str, module_name: str) -> Any:
        """Load a Python module from a file path. Returns module or None on failure."""
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            logger.warning("[registry] Failed to load {}: {}", file_path, e)
            return None

    def _load_provider(self, provider_id: str, provider_path: str, manifest_file: str) -> None:
        """Load a provider's manifest + optional provider.py + optional settings_schema.py.

        Applies broken-provider isolation: any exclusion logs WARN and returns.
        """
        module_prefix = f"_sts_provider_{self.domain}_{provider_id}"

        try:
            spec = importlib.util.spec_from_file_location(f"{module_prefix}_manifest", manifest_file)
            if spec is None or spec.loader is None:
                logger.warning("[registry] [EXCLUDED] {}: could not load manifest (spec failed)", provider_id)
                return

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except SyntaxError as e:
            logger.warning("[registry] [EXCLUDED] {}: SyntaxError in manifest.py: {}", provider_id, e)
            return
        except ImportError as e:
            logger.warning("[registry] [EXCLUDED] {}: ImportError in manifest.py: {}", provider_id, e)
            return
        except Exception as e:
            logger.warning("[registry] [EXCLUDED] {}: failed to load manifest.py: {}", provider_id, e)
            return

        if not hasattr(module, 'manifest'):
            logger.warning("[registry] [EXCLUDED] {}: manifest() function not found", provider_id)
            return

        try:
            manifest_data = module.manifest()
        except Exception as e:
            logger.warning("[registry] [EXCLUDED] {}: manifest() call raised: {}", provider_id, e)
            return

        if not isinstance(manifest_data, ProviderManifest):
            if isinstance(manifest_data, dict):
                try:
                    manifest_data = ProviderManifest(**manifest_data)
                except Exception as e:
                    logger.warning("[registry] [EXCLUDED] {}: invalid manifest dict: {}", provider_id, e)
                    return
            else:
                logger.warning("[registry] [EXCLUDED] {}: manifest() must return ProviderManifest or dict", provider_id)
                return

        required_fields = ['id', 'label', 'domain', 'kind', 'version', 'capabilities']
        missing = [f for f in required_fields if not getattr(manifest_data, f, None)]
        if missing:
            logger.warning("[registry] [EXCLUDED] {}: missing required fields: {}", provider_id, missing)
            return

        if manifest_data.id != provider_id:
            logger.warning("[registry] [EXCLUDED] {}: manifest.id '{}' != folder name",
                         provider_id, manifest_data.id)
            return

        provider_file = os.path.join(provider_path, 'provider.py')
        schema_file = os.path.join(provider_path, 'settings_schema.py')
        provider_module = None
        schema_module = None

        if os.path.isfile(provider_file):
            provider_module = self._load_module_from_file(
                provider_file, f"{module_prefix}_provider"
            )
            if provider_module is None:
                logger.warning("[registry] {}: provider.py failed to load — functions will fall back to manifest", provider_id)

        if os.path.isfile(schema_file):
            schema_module = self._load_module_from_file(
                schema_file, f"{module_prefix}_schema"
            )
            if schema_module is None:
                logger.warning("[registry] {}: settings_schema.py failed to load", provider_id)

        self.register(
            provider_id, module, manifest_data,
            provider_module=provider_module,
            schema_module=schema_module,
        )
    
    def to_dict(self, selected_provider: str | None = None) -> dict:
        """Serialize registry state for API response."""
        return {
            'domain': self.domain,
            'providers': [p.to_dict() for p in self.list_providers()],
            'selected': selected_provider,
            'count': len(self),
        }
