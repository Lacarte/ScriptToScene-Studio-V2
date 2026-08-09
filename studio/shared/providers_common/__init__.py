"""Shared provider utilities — Phase 9.

Modules:
  - domains: the domain catalog — the single declaration of supported domains
  - settings_schema: provider settings schema validation, secrets, and visibility
  - settings_migrations: version-to-version migrations
  - settings_manager: canonical load/save/validate for settings.json
  - validation: manifest validation, exclusion reason codes, message sanitization
  - registry: provider discovery and domain-scoped registries
  - hub: process-wide hub resolving (domain, provider_id) across all domains
  - runtime: base class for extension provider runtimes
  - errors: ProviderError, the stable code catalog, and retryability
  - invocation: ProviderInvocation, cancellation, progress, redacted logging
  - results: the ProviderResult envelope, units, provenance, egress validation
  - jobs: the one asynchronous job contract shared by both visual domains
  - boundary: the single exception boundary and the deadline helpers
  - legacy: adapters from today's dict payloads onto the v2 envelope
  - http_client: retry/backoff wrapped requests
  - file_download: normalized file download to output dirs
  - progress: status.json writer for job progress
"""

from studio.shared.providers_common.domains import (
    DOMAINS,
    DOMAIN_IDS,
    DomainSpec,
    get_domain,
)
from studio.shared.providers_common.settings_schema import (
    REDACTION_SENTINEL,
    SENSITIVE_KEYS_RE,
    WIDGET_TYPES,
    apply_settings_patch,
    invocation_config,
    is_secret_field,
    secret_keys,
    split_settings,
    validate_against_schema,
    visible_fields,
)
from studio.shared.providers_common.settings_migrations import (
    SETTINGS_VERSION,
    apply_migrations,
)
from studio.shared.providers_common.settings_manager import (
    load_settings,
    save_settings,
    get_domain_settings,
    get_provider_settings,
    set_provider_settings,
    set_selected_provider,
    get_general_settings,
    set_general_settings,
    merge_provider_settings,
    portable_provider_settings,
    redact_settings,
    redacted_provider_settings,
    restore_redacted_secrets,
    validate_settings,
)
from studio.shared.providers_common.validation import (
    EXCLUSION_REASON_CODES,
    ManifestValidation,
    sanitize_message,
    validate_manifest,
)
from studio.shared.providers_common.registry import (
    CatalogSnapshot,
    ProviderConstructionError,
    ProviderExclusion,
    ProviderRegistry,
    ProviderManifest,
    ProviderInstance,
    HealthResult,
    ValidationIssue,
)
from studio.shared.providers_common.runtime import (
    Runtime,
    RuntimeBinding,
    call_provider_runtime,
)
from studio.shared.providers_common.errors import (
    PROVIDER_CODES,
    ProviderCancelled,
    ProviderError,
    ProviderErrorPayload,
    is_retryable,
    workflow_code,
)
from studio.shared.providers_common.invocation import (
    CancellationToken,
    ProgressReporter,
    ProviderInvocation,
    ProviderLogger,
    build_invocation,
    domain_deadline,
)
from studio.shared.providers_common.results import (
    Provenance,
    ProviderResult,
    UnitResult,
    coerce_result,
    derive_status,
    normalize_ref,
    resolve_ref,
    validate_egress,
)
from studio.shared.providers_common.jobs import (
    JobHandle,
    JobRecord,
    JobStatus,
    poll_interval,
    terminal_outcome,
    unknown_job_status,
)
from studio.shared.providers_common.boundary import (
    Deadline,
    invoke,
    wait_until,
    wrap_exception,
)
from studio.shared.providers_common.hub import (
    ProviderHub,
    DomainBinding,
    ReloadReport,
    bind_domain,
    hub,
    init_providers,
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
    "DOMAINS",
    "DOMAIN_IDS",
    "DomainSpec",
    "get_domain",
    "REDACTION_SENTINEL",
    "SENSITIVE_KEYS_RE",
    "WIDGET_TYPES",
    "apply_settings_patch",
    "invocation_config",
    "is_secret_field",
    "secret_keys",
    "split_settings",
    "validate_against_schema",
    "visible_fields",
    "SETTINGS_VERSION",
    "apply_migrations",
    "load_settings",
    "save_settings",
    "get_domain_settings",
    "get_provider_settings",
    "set_provider_settings",
    "set_selected_provider",
    "get_general_settings",
    "set_general_settings",
    "merge_provider_settings",
    "portable_provider_settings",
    "redact_settings",
    "redacted_provider_settings",
    "restore_redacted_secrets",
    "validate_settings",
    "EXCLUSION_REASON_CODES",
    "ManifestValidation",
    "sanitize_message",
    "validate_manifest",
    "CatalogSnapshot",
    "ProviderConstructionError",
    "ProviderExclusion",
    "ProviderRegistry",
    "ProviderManifest",
    "ProviderInstance",
    "HealthResult",
    "ValidationIssue",
    "Runtime",
    "RuntimeBinding",
    "call_provider_runtime",
    "PROVIDER_CODES",
    "ProviderCancelled",
    "ProviderError",
    "ProviderErrorPayload",
    "is_retryable",
    "workflow_code",
    "CancellationToken",
    "ProgressReporter",
    "ProviderInvocation",
    "ProviderLogger",
    "build_invocation",
    "domain_deadline",
    "Provenance",
    "ProviderResult",
    "UnitResult",
    "coerce_result",
    "derive_status",
    "normalize_ref",
    "resolve_ref",
    "validate_egress",
    "JobHandle",
    "JobRecord",
    "JobStatus",
    "poll_interval",
    "terminal_outcome",
    "unknown_job_status",
    "Deadline",
    "invoke",
    "wait_until",
    "wrap_exception",
    "ProviderHub",
    "DomainBinding",
    "ReloadReport",
    "bind_domain",
    "hub",
    "init_providers",
    "HttpClient",
    "get_http_client",
    "close_http_client",
    "download_file",
    "download_to_output_dir",
    "ProgressWriter",
    "write_status_json",
]
