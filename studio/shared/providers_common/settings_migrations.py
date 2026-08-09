"""Settings migrations — versioned, forward-only upgrades of settings.json.

`MIGRATIONS` maps a **target** version to the function that upgrades data from the
previous version to it. `apply_migrations` runs every registered target greater
than the stored version, in ascending order, and stamps the version after each
step. The pre-11.3 loop skipped every version `>= current_version`, which meant it
could never run an upgrade — contracts.md §24.3 assigns that correction here.

v2 implements §24.3: adopt the three legacy `app-config.json` provider selections
into `settings.json`, which is the single selection authority (§24).
"""

from typing import Callable

from studio.shared.providers_common.domains import DOMAINS


# The version a freshly written settings.json carries.
# v2 = §24.3 five-domain catalog + legacy selection adoption (step 11.3).
# v3 = S6 script selection `builtin` → `gemini` (step 13.3).
# v4 = S7 scene_blueprint selection `builtin` → `n8n` (step 13.4).
SETTINGS_VERSION = 4

MIGRATIONS: dict[int, Callable[[dict, dict], dict]] = {}


def _register(version: int):
    """Register the function that upgrades data *to* `version`."""
    def decorator(func: Callable[[dict, dict], dict]):
        MIGRATIONS[version] = func
        return func
    return decorator


# Legacy wire values in `app-config.json` predate the canonical registry ids
# (§24.3). Kept here rather than in the alias table because these are *selection*
# strings from a retired store, not provider-declared aliases.
LEGACY_SELECTION_ALIASES = {
    "gemini": "gemini_ws",
    "grok": "grok_automa",
    "kie-ai": "kie_ai",
    "webhook": "wavespeed_webhook",
    "direct": "wavespeed_direct",
}


@_register(2)
def migrate_to_v2(data: dict, legacy_user: dict) -> dict:
    """Adopt the legacy per-domain provider selections, then never look again.

    `settings.json` always wins: the legacy key is only read when the domain has
    no explicit `selected_provider`. The missing domain blocks of a settings file
    written before the five-domain catalog are backfilled at the same time, so the
    upgrade is lossless in both directions.
    """
    domains = data.setdefault("domains", {})

    for domain_id, spec in DOMAINS.items():
        block = domains.get(domain_id)
        if not isinstance(block, dict):
            block = {"selected_provider": spec.default_provider, "per_provider": {}}
            domains[domain_id] = block
        block.setdefault("per_provider", {})

        if block.get("selected_provider"):
            continue  # settings.json wins; the legacy key is ignored from now on

        legacy_key = spec.legacy_selection_key
        legacy_value = legacy_user.get(legacy_key) if legacy_key else None
        if isinstance(legacy_value, str) and legacy_value.strip():
            block["selected_provider"] = LEGACY_SELECTION_ALIASES.get(
                legacy_value, legacy_value
            )
        else:
            # An absent or null selection resolves to the catalog default (§24.1
            # rule 4), written down so the store is complete after the upgrade.
            block["selected_provider"] = spec.default_provider

    return data


@_register(3)
def migrate_to_v3(data: dict, legacy_user: dict) -> dict:
    """S6 — rewrite only the transitional script selection `builtin` → `gemini`.

    The 12.3 bridge id was the domain default until 13.2 landed the real
    `gemini` provider. Any explicit selection other than `builtin`
    (`random_template`, a future plugin, …) is left alone (contracts.md §42 S6).
    """
    domains = data.setdefault("domains", {})
    block = domains.get("script")
    if isinstance(block, dict) and block.get("selected_provider") == "builtin":
        block["selected_provider"] = "gemini"
    return data


@_register(4)
def migrate_to_v4(data: dict, legacy_user: dict) -> dict:
    """S7 — rewrite only the transitional scene_blueprint selection `builtin` → `n8n`.

    The 12.3 bridge id was the domain default until 13.4 landed the real
    `n8n` provider. Any explicit selection other than `builtin` is left alone
    (contracts.md §42 S7).
    """
    domains = data.setdefault("domains", {})
    block = domains.get("scene_blueprint")
    if isinstance(block, dict) and block.get("selected_provider") == "builtin":
        block["selected_provider"] = "n8n"
    return data


def apply_migrations(data: dict, legacy_user: dict | None = None) -> tuple[dict, bool]:
    """Upgrade `data` to `SETTINGS_VERSION`.

    Args:
        data: the raw settings document as read from disk.
        legacy_user: `app-config.json["user"]`, injected rather than read here so
            the migration never imports a route's private helper (§24.3).

    Returns `(migrated_data, changed)`. `changed` is `True` only when a migration
    ran, so an already-current document is not rewritten — the migration is
    idempotent and the version stamp is the completion marker.
    """
    current_version = data.get("version")
    if not isinstance(current_version, int) or isinstance(current_version, bool):
        current_version = 1

    legacy_user = legacy_user or {}
    migrated = data
    changed = False

    for version in sorted(MIGRATIONS):
        if version <= current_version:
            continue
        migrated = MIGRATIONS[version](migrated, legacy_user)
        # Stamped per step: an interrupted write leaves the previous version on
        # disk and the next load retries from there.
        migrated["version"] = version
        changed = True

    if migrated.get("version") != SETTINGS_VERSION and changed:
        migrated["version"] = SETTINGS_VERSION

    return migrated, changed


__all__ = [
    "SETTINGS_VERSION",
    "MIGRATIONS",
    "LEGACY_SELECTION_ALIASES",
    "apply_migrations",
    "migrate_to_v2",
    "migrate_to_v3",
    "migrate_to_v4",
]
