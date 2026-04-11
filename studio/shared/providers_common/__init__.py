"""Shared provider utilities — Phase 9.

Modules:
  - settings_migrations: version-to-version migrations
  - settings_manager: canonical load/save/validate for settings.json
  - registry: provider discovery and domain-scoped registries
  - runtime: base class for extension provider runtimes
  - http_client: retry/backoff wrapped requests
  - file_download: normalized file download to output dirs
  - progress: status.json writer for job progress
"""

from studio.shared.providers_common.settings_migrations import apply_migrations
from studio.shared.providers_common.settings_manager import (
    load_settings,
    save_settings,
    get_domain_settings,
    get_provider_settings,
    set_provider_settings,
    set_selected_provider,
    get_general_settings,
    set_general_settings,
    redact_settings,
    redacted_provider_settings,
    validate_settings,
)
from studio.shared.providers_common.registry import (
    ProviderRegistry,
    ProviderManifest,
    ProviderInstance,
    HealthResult,
    ValidationIssue,
)
from studio.shared.providers_common.runtime import (
    Runtime,
    call_provider_runtime,
)
from studio.shared.providers_common.http_client import (
    HttpClient,
    get_http_client,
    close_http_client,
)
from studio.shared.providers_common.file_download import (
    download_file,
    download_to_output_dir,
)
from studio.shared.providers_common.progress import (
    ProgressWriter,
    write_status_json,
)

__all__ = [
    "apply_migrations",
    "load_settings",
    "save_settings",
    "get_domain_settings",
    "get_provider_settings",
    "set_provider_settings",
    "set_selected_provider",
    "get_general_settings",
    "set_general_settings",
    "redact_settings",
    "redacted_provider_settings",
    "validate_settings",
    "ProviderRegistry",
    "ProviderManifest",
    "ProviderInstance",
    "HealthResult",
    "ValidationIssue",
    "Runtime",
    "call_provider_runtime",
    "HttpClient",
    "get_http_client",
    "close_http_client",
    "download_file",
    "download_to_output_dir",
    "ProgressWriter",
    "write_status_json",
]
