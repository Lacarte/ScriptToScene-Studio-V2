"""Settings Migrations — Phase 1: v1 identity migration.

MIGRATIONS dict maps version number -> migration function.
Each migration function receives the raw data dict and returns migrated data.
Migrations are applied sequentially starting from the stored version.
"""

from typing import Callable

MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


def _register(version: int):
    """Decorator to register a migration function for a specific version."""
    def decorator(func: Callable[[dict], dict]):
        MIGRATIONS[version] = func
        return func
    return decorator


@_register(1)
def migrate_v1(data: dict) -> dict:
    """Identity migration for v1 — reserves the version slot.
    
    When a new version is added, implement the migration function here
    and register it with @_register(new_version).
    """
    return data


def apply_migrations(data: dict) -> tuple[dict, bool]:
    """Apply all migrations sequentially from stored version to latest.
    
    Returns (migrated_data, changed) where changed is True if any migration
    was applied.
    """
    current_version = data.get("version", 1)
    migrated = data
    changed = False
    
    for version in sorted(MIGRATIONS.keys()):
        if version >= current_version:
            continue
        if version in MIGRATIONS:
            migrated = MIGRATIONS[version](migrated)
            changed = True
    
    return migrated, changed
